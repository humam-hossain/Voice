# Codebase Concerns

**Analysis Date:** 2026-09-18

## Tech Debt

**Monolithic Single-File Design:**
- Issue: All application domains (STT, TTS, CLI dispatch, platform bridges, hardware audio I/O, IPC signaling) are tightly coupled in a single 1230-line file `voice.py`.
- Files: `voice.py`
- Impact: Difficult to unit-test individual modules, high risk of unintended regressions during edits, inability to conditionally package subcomponents.
- Fix approach: Modularize into a proper package structure (e.g., `voicemode/` with `stt/`, `tts/`, `platform/`, `audio/`, and `cli.py`).

**Subprocess Shell Spawning for Native Desktop Services:**
- Issue: Interacting with display server selection, input typing, desktop notifications, and keybinding management relies heavily on external CLI binaries (`xclip`, `xdotool`, `ydotool`, `wl-paste`, `wl-copy`, `notify-send`, `gsettings`, `ffplay`).
- Files: `voice.py:319-438`, `voice.py:461-492`, `voice.py:554-563`, `voice.py:925-958`
- Impact: Inefficient process spawning overhead, brittle error recovery, and failure when users lack specific external tools installed in their host environment.
- Fix approach: Transition to direct Python bindings or D-Bus APIs for notifications, keybindings, and playback (e.g. `pydbus` or native `sounddevice` playback).

**Hardcoded Installation Paths in Hotkey Installer:**
- Issue: `install_gnome_hotkey()` assumes the binary is installed at `Path.home() / ".local" / "bin" / "voice"`.
- Files: `voice.py:932`
- Impact: Keybindings break silently if installed in a virtual environment (`.venv`), installed via pipx, or executed under the primary package name `voicemode`.
- Fix approach: Dynamically resolve executable path using `shutil.which("voicemode") or shutil.which("voice") or sys.executable`.

## Known Bugs

**Race Conditions in Detached Background Process Management:**
- Symptoms: Stale PID files or failure to stop recording/speaking when user rapidly double-taps shortcut keys.
- Files: `voice.py:812-835`, `voice.py:648-662`
- Trigger: Rapid consecutive presses of `Super+B` or `Super+T` before the spawned background process has written its PID file or registered signal handlers.
- Workaround: Wait at least 500ms between key presses, or manually delete `$XDG_RUNTIME_DIR/voice-stt/*.pid`.

**Process Group Termination in TTS Stop:**
- Symptoms: `os.killpg(pid, signal.SIGTERM)` can raise `ProcessLookupError` or potentially affect broader process groups if session IDs are mismatched.
- Files: `voice.py:569-577`
- Trigger: Stopping TTS while the child process or its spawned `ffplay` process is already terminating.
- Workaround: Handled by broad exception catch, but can leave zombie player processes in edge cases.

## Security Considerations

**Data Exfiltration Risk via Edge TTS Backend:**
- Risk: Text highlighted in any application (which may include passwords, secrets, private emails, or proprietary code) is transmitted in cleartext/HTTPS to Microsoft cloud endpoints when `--tts-backend edge` is active.
- Files: `voice.py:505-516`, `docs/DEPENDENCIES.md:26`
- Current mitigation: Kokoro (local offline ONNX) is set as the default backend. Edge TTS is optional.
- Recommendations: Add an explicit user confirmation prompt or prominent banner before enabling Edge TTS, or require an explicit environment flag like `VOICE_ALLOW_CLOUD_TTS=true`.

**Insecure Fallback Runtime Directory Permissions:**
- Risk: If `$XDG_RUNTIME_DIR` is unset, `STATE_DIR` falls back to `/tmp/voice-stt-{uid}`. If created with default umask, other local users on a multi-user system could read transcribed text logs (`voice.log`) or injected text files (`voice-tts-*.txt`).
- Files: `voice.py:37`
- Current mitigation: Directory is scoped by UID.
- Recommendations: Explicitly set `os.chmod(STATE_DIR, 0o700)` upon creation.

## Performance Bottlenecks

**Cold-Start Transcription Latency:**
- Problem: Dictation exhibits 2–5+ seconds of latency between releasing the hotkey and seeing text typed on screen.
- Files: `voice.py:879` (`model_state = load_model(args)`)
- Cause: `load_model(args)` is called *after* recording finishes inside the short-lived background worker process. The Whisper model weights are reloaded from disk into RAM/VRAM on every single dictation toggle.
- Improvement path: Implement a persistent resident background daemon that keeps the Whisper model pre-warmed in memory, interacting via Unix domain socket or D-Bus.

**Disk I/O for Ephemeral Audio Buffers:**
- Problem: Audio is written to disk as uncompressed WAV (`voice.py:152-157`) and read back from disk by `faster-whisper` (`voice.py:306`), adding file system latency and SSD wear.
- Cause: `WhisperModel.transcribe` accepts file paths directly, but also supports in-memory NumPy float32 arrays.
- Improvement path: Pass in-memory `audio` NumPy float32 array directly to `model.transcribe(audio)` without intermediate WAV serialization.

## Fragile Areas

**Wayland vs X11 Input Simulation:**
- Files: `voice.py:361-438`
- Why fragile: Wayland's security model deliberately restricts global keystroke synthesis and selection sniffing. `ydotool` requires a background `ydotoold` daemon running with access to `/dev/uinput`, which is frequently unconfigured on modern desktop Linux installations.
- Safe modification: Check `ydotoold` daemon responsiveness before attempting `ydotool` commands, and provide clear diagnostic instructions when input synthesis fails.
- Test coverage: Zero automated test coverage.

**GNOME D-Bus Schema Manipulation:**
- Files: `voice.py:914-960`
- Why fragile: Relies on `gsettings` CLI parsing and string evaluation (`ast.literal_eval` on `@as [...]`). Any schema variation across GNOME versions (e.g. GNOME 42 vs 46+) can corrupt custom keybinding lists.
- Safe modification: Test against clean GNOME setups; backup existing custom keybindings before mutating list.
- Test coverage: Untested in CI.

## Scaling Limits

**Audio Capture Memory Usage:**
- Current capacity: In-memory `list[np.ndarray]` buffer appending 100ms frames.
- Limit: Long recording sessions (e.g. >30 minutes) consume substantial uncompressed float32 RAM (~230 MB for 30 mins at 16kHz mono).
- Scaling path: Stream directly to a temporary audio file chunk-by-chunk if recording duration exceeds a threshold.

## Dependencies at Risk

**`kokoro-onnx` and `phonemizer-fork` Licensing Contamination:**
- Risk: `kokoro-onnx==0.5.0` depends on `phonemizer-fork`, which is licensed under GPLv3+. The repository itself is MIT licensed.
- Impact: Distributing pre-built binaries or wheel packages containing this dependency chain creates a GPLv3 license propagation issue.
- Migration plan: Isolate Kokoro into an optional standalone plugin or replace `phonemizer-fork` with a permissively licensed phonemization runtime (such as `misaki` or ONNX-embedded phonemizer).

**`edge-tts` Protocol Stability:**
- Risk: `edge-tts` relies on reverse-engineered endpoints from Microsoft Edge.
- Impact: Microsoft can change or deprecate endpoints at any time without warning.
- Migration plan: Keep Kokoro as the primary default and treat Edge TTS strictly as a non-essential alternative.

## Missing Critical Features

**Persistent Daemon Mode:**
- Problem: No persistent background daemon option; all state is managed via ad-hoc spawned background processes.
- Blocks: Pre-warmed model inference, fast dictation turnaround, centralized queueing of audio requests.

**Visual Status Indicator / System Tray:**
- Problem: User only has audible beeps and transient desktop notifications; no persistent tray icon or overlay indicating active recording.
- Blocks: User awareness of microphone status if headphones are off or audio cue is missed.

## Test Coverage Gaps

**Untested Platform Abstractions:**
- What's not tested: `display_server()`, `copy_to_clipboard()`, `type_text()`, `read_x_selection()`.
- Files: `voice.py:361-503`
- Risk: Desktop environment changes or missing system utilities break core STT/TTS injection without early detection.

**Untested CLI Argument Parsing & Fallbacks:**
- What's not tested: Parsing of environment variables, default speed calculation, Hermes config fallbacks.
- Files: `voice.py:1074-1181`
- Risk: Regression in CLI arguments or environment variable parsing breaks hotkey commands.

---

*Concerns analysis: 2026-09-18*
