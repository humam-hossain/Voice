<!-- refreshed: 2026-09-18 -->
# Architecture

**Analysis Date:** 2026-09-18

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             GNOME Desktop / User                            │
├───────────────────────────────┬─────────────────────────────────────────────┤
│         Super+B (STT)         │                Super+T (TTS)                │
│    `voicemode --toggle`       │        `voicemode --speak-selection`        │
└───────────────┬───────────────┴──────────────────────┬──────────────────────┘
                │                                      │
                ▼                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLI Dispatcher & IPC                              │
│                      `voice.py:main`, `voice.py:parse_args`                 │
│         Inter-process signal coordination via PID files in `$STATE_DIR`     │
├──────────────────────────────────────┬──────────────────────────────────────┤
│         STT Recorder Lifecycle       │         TTS Worker Lifecycle         │
│  `toggle_background_recording()`     │  `speak_selection()`,                │
│  `run_background_recording()`        │  `start_tts_background()`,           │
│                                      │  `run_tts_background()`              │
└───────────────┬──────────────────────┴───────────────┬──────────────────────┘
                │                                      │
                ▼                                      ▼
┌──────────────────────────────────────┐┌─────────────────────────────────────┐
│         Audio Input Engine           ││        Audio Synthesis Engine       │
│  `Recorder` (sounddevice / numpy)    ││  Kokoro (`kokoro_onnx`, `soundfile`)│
│  Tone generator (`play_cue`)         ││  Edge (`edge_tts`, async client)    │
└───────────────┬──────────────────────┘└──────────────┬──────────────────────┘
                │                                      │
                ▼                                      ▼
┌──────────────────────────────────────┐┌─────────────────────────────────────┐
│        Speech-to-Text Model          ││        Audio Player & Output        │
│  `load_model()`, `transcribe()`      ││  `play_tts_audio()` (`ffplay`)      │
│  Faster-Whisper (CTranslate2)        ││                                     │
└───────────────┬──────────────────────┘└─────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Display Server & Clipboard Bridge                        │
│   Selection: `xclip` (X11) / `wl-paste` (Wayland)                           │
│   Injection: `xdotool` (X11) / `ydotool` (Wayland)                          │
│   Notification: `notify-send`                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| CLI Parser & Dispatcher | Parses command-line flags, sets defaults from env/config, routes command mode | `voice.py:parse_args`, `voice.py:main` |
| Audio Capture (`Recorder`) | Captures mono microphone input asynchronously using SoundDevice streams | `voice.py:Recorder` |
| Audio Cue Synthesizer | Generates sine wave chimes with windowed fades for auditory state feedback | `voice.py:play_tone`, `voice.py:play_cue` |
| Whisper STT Transcriber | Manages Faster-Whisper model loading, compute precision fallback, and decoding | `voice.py:load_model`, `voice.py:transcribe` |
| Text Injector | Dispatches recognized transcripts to focused applications via typing or clipboard paste | `voice.py:insert_text`, `voice.py:type_text`, `voice.py:paste_clipboard` |
| Selection Reader | Extracts text currently highlighted in the GUI or from the system clipboard | `voice.py:read_x_selection`, `voice.py:selected_or_clipboard_text` |
| Kokoro TTS Synthesizer | Runs offline ONNX neural TTS and exports PCM audio to temporary WAV files | `voice.py:synthesize_kokoro_tts` |
| Edge TTS Synthesizer | Streams text to Microsoft Edge TTS online API and outputs temporary MP3 files | `voice.py:synthesize_edge_tts` |
| Audio Player | Spawns `ffplay` in headless mode to output synthesized audio to sound hardware | `voice.py:play_tts_audio` |
| Hotkey Installer | Writes GNOME Settings Daemon keybinding configurations via `gsettings` | `voice.py:install_gnome_hotkey`, `voice.py:set_gnome_custom_binding` |
| Activity Monitor | Continuously reads and displays appended lines from STT and TTS log files | `voice.py:watch_log` |

## Pattern Overview

**Overall:** Monolithic Multi-Mode CLI with Daemon/Worker Forking and File-Based IPC.

**Key Characteristics:**
- **Single-file Architecture:** All modules and logic reside in `voice.py` to maintain a standalone, single-command utility.
- **Detached Worker Pattern:** Background processes are spawned via `subprocess.Popen(start_new_session=True)` with redirected file logs and PID tracking in `$XDG_RUNTIME_DIR`.
- **POSIX Signal Coordination:** Uses `SIGUSR1` to trigger state transitions (recording -> stop & transcribe; speaking -> interrupt playback).
- **Graceful Hardware/Backend Fallbacks:** If GPU execution fails during Whisper transcription, automatically catches the exception and retries on CPU with `int8` quantization.

## Layers

**CLI & Dispatch Layer:**
- Purpose: Command routing, argument resolution, and environment parsing
- Location: `voice.py:1074-1232`
- Contains: `parse_args()`, `main()`, command branching
- Depends on: Standard library `argparse`, `os`, `sys`
- Used by: Desktop hotkeys, user terminal commands, background subprocesses

**Domain Services (STT & TTS Pipelines):**
- Purpose: Audio capture, transcription, text extraction, speech synthesis, text injection
- Location: `voice.py:92-209`, `voice.py:275-317`, `voice.py:372-564`, `voice.py:616-720`, `voice.py:838-912`
- Contains: `Recorder`, `transcribe()`, `synthesize_tts()`, `run_background_recording()`, `run_tts_background()`
- Depends on: `faster-whisper`, `kokoro-onnx`, `edge-tts`, `sounddevice`, `numpy`, `soundfile`
- Used by: CLI and background workers

**OS & Desktop Integration Layer:**
- Purpose: Interacting with display servers, desktop notifications, and keybindings
- Location: `voice.py:319-370`, `voice.py:372-502`, `voice.py:914-960`
- Contains: `display_server()`, `copy_to_clipboard()`, `type_text()`, `read_x_selection()`, `install_gnome_hotkey()`, `notify()`
- Depends on: External Linux binaries (`xclip`, `xdotool`, `ydotool`, `wl-paste`, `wl-copy`, `notify-send`, `gsettings`)
- Used by: Domain services to read GUI context and inject output

## Data Flow

### Primary STT Request Path (Dictation)

1. User presses `Super+B` triggering `voice.py --toggle` (`voice.py:1184`).
2. `toggle_background_recording()` checks `PID_FILE`:
   - If no active process, spawns `voice.py --record-background` detached with `start_new_session=True` (`voice.py:825`).
   - Writes `recorder.pid`.
3. Background recorder plays "start" chime (`voice.py:856`) and opens `sounddevice.InputStream` (`voice.py:113`).
4. While active, periodically plays reminder chimes every 5 seconds (`voice.py:868`).
5. User presses `Super+B` a second time:
   - `toggle_background_recording()` finds active PID and sends `signal.SIGUSR1` (`voice.py:816`).
6. Background recorder receives `SIGUSR1`, sets `stop_requested = True`, stops stream, and writes uncompressed PCM to temporary WAV (`voice.py:874`).
7. Plays "stop" chime (`voice.py:875`), notifies desktop ("Transcribing...").
8. Loads `WhisperModel` (`voice.py:879`), executes `model.transcribe(wav_path)` (`voice.py:306`).
9. Injects resulting string into focused window via `insert_text()` (`voice.py:440` -> `xdotool` or `ydotool`).
10. Cleans up temporary WAV file and unlinks `recorder.pid` (`voice.py:908-911`).

### Secondary TTS Flow Path (Read Selection)

1. User presses `Super+T` triggering `voice.py --speak-selection` (`voice.py:1195`).
2. Checks `TTS_PID_FILE`: if active TTS process is running, terminates it and returns (toggle stop behavior) (`voice.py:649-652`).
3. Reads text from X11 primary selection via `xclip -selection primary -o` (or `wl-paste --primary`) (`voice.py:494`).
4. If primary selection is empty, falls back to reading clipboard (`voice.py:498`).
5. Spawns detached worker `voice.py --tts-background --tts-text-file <tmp>` (`voice.py:635`).
6. Worker reads text file, writes `tts.pid`, and calls `synthesize_tts()` (`voice.py:540`).
7. Synthesizer generates audio file (`.wav` via Kokoro or `.mp3` via Edge TTS).
8. Worker executes `ffplay -nodisp -autoexit <audio>` to play sound (`voice.py:558`).
9. Removes audio file, text file, and unlinks `tts.pid` in `finally` block (`voice.py:709-718`).

**State Management:**
- Stateless process execution coordinated entirely through filesystem artifacts in `$STATE_DIR` (`$XDG_RUNTIME_DIR/voice-stt/`):
  - `recorder.pid` (tracks STT state)
  - `tts.pid` (tracks TTS state)
  - `voice.log` / `tts.log` (monitored via file size and offset tracking in `watch_log()`)

## Key Abstractions

**`Recorder` (`voice.py:92-159`):**
- Purpose: State machine and callback handler for continuous microphone input
- Pattern: Object-oriented wrapper around `sounddevice.InputStream` with frame buffering and WAV persistence

**`ModelState` (`voice.py:60-65`):**
- Purpose: Encapsulates loaded Faster-Whisper model alongside runtime device and quantization metadata
- Pattern: Immutable dataclass

**`TerminalKeys` (`voice.py:73-90`):**
- Purpose: Interactive terminal raw key reader for local Ctrl+B mode
- Pattern: Python Context Manager altering POSIX terminal attributes with `termios` and restoring in `__exit__`

## Entry Points

**Console Scripts:**
- `voicemode = voice:main` (`pyproject.toml:49`)
- `voice = voice:main` (`pyproject.toml:50`)
- Invocation:
  - Default: Starts log watcher / activity monitor (`watch_log()`)
  - `--toggle`: Toggles background recording for STT
  - `--speak-selection`: Reads active desktop selection and speaks via TTS
  - `--terminal`: Interactive terminal dictation testing mode

## Architectural Constraints

- **Single-Threaded Subprocess Decoupling:** Core long-running operations (recording, synthesis) run in isolated detached Python processes rather than background threads in a daemon to avoid Python GIL audio contention and crash propagation.
- **Operating System Dependency:** Hard dependency on Linux desktop environment features (POSIX signals, X11/Wayland display sockets, GNOME D-Bus).
- **Concurrency Limitation:** Single STT recorder and single TTS player at any given time, enforced by PID lockfiles.
- **Audio Device Locking:** Concurrent recording and tone cue playback require soundcard support for shared mixing (ALSA/PulseAudio/PipeWire).

## Anti-Patterns

### Heavy CLI Binary Forking for Standard Tasks
**What happens:** System operations like clipboard reading, desktop notifications, key pressing, and audio playback spawn short-lived external CLI processes (`xclip`, `xdotool`, `notify-send`, `ffplay`).
**Why it's wrong:** Spawning processes introduces shell execution overhead, subprocess error handling brittleness, and dependency on external binaries being on the PATH.
**Do this instead:** Use native Python bindings where feasible (e.g. Python D-Bus for notifications/settings, `sounddevice.play()` instead of `ffplay`).

### Post-Recording Cold-Start Model Loading
**What happens:** In `run_background_recording()`, `load_model(args)` is called *after* audio recording has completed (`voice.py:879`).
**Why it's wrong:** Loading large neural network weights into memory introduces several seconds of latency before transcription begins on each dictation event.
**Do this instead:** Pre-warm and keep the Whisper model loaded in a persistent background daemon service.

### Monolithic Single-File Module
**What happens:** All models, CLI logic, platform abstraction, configuration, and helpers exist in a single 1200+ line `voice.py`.
**Why it's wrong:** Violates single responsibility principle, inhibits modular unit testing, and mixes optional dependencies (Kokoro, Edge) with core execution.
**Do this instead:** Decompose into modular packages (e.g., `voicemode.stt`, `voicemode.tts`, `voicemode.platform`).

## Error Handling

**Strategy:** Defensive CLI execution with fallback recovery and desktop notification alerts.

**Patterns:**
- **Inference Hardware Fallback:** If GPU/auto execution crashes in `transcribe()`, automatically catches `Exception`, reloads model on CPU with `int8` quantization, and retries transcription (`voice.py:312-316`).
- **Graceful Tool Detection:** Before running system tools (`wl-copy`, `xclip`, `ydotool`, `xdotool`, `ffplay`), checks `shutil.which()` and active display variables, returning empty strings or `False` rather than raising uncaught exceptions.
- **Cleanup Guarantee:** Background scripts wrap active resources, PID files, and temporary WAV files in `try ... finally` blocks to ensure unlinking on process termination or `KeyboardInterrupt`.

## Cross-Cutting Concerns

**Logging:** Standardized appended text logging to `$STATE_DIR/voice.log` and `tts.log` formatted with timestamps.
**Validation:** CLI input normalization and boundary checks (`re.sub` for whitespace in TTS, `volume` clamped between 0.0 and 1.0).
**Security:** External cloud warning for Edge TTS; local-only inference enforced for Kokoro and Whisper.

---

*Architecture analysis: 2026-09-18*
