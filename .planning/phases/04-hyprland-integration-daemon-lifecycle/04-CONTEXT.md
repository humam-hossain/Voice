# Phase 4: Hyprland Integration & Daemon Lifecycle - Context

**Gathered:** 2026-09-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 configures global Hyprland keybindings for push-to-talk speech-to-text (STT) and selection text-to-speech (TTS), establishes hardened background daemon lifecycle management via POSIX signals (`SIGUSR1`, `SIGTERM`), integrates idempotent dotfiles installation for the user's `dots-hyprland` Lua environment (`~/.config/hypr/custom/keybinds.lua`), and ensures focus-safe, distraction-free desktop feedback under Wayland.

</domain>

<decisions>
## Implementation Decisions

### Hyprland Keybinding Chords & Upstream Conflict Resolution
- **D-01:** Assign **`SUPER + SHIFT + M`** for STT push-to-talk toggle (`voice --toggle`). This chord is already unbound upstream in `custom/keybinds.lua` (reclaimed from volume mute) and pairs naturally with the audio/mic modifier family.
- **D-02:** Assign **`SUPER + T`** for TTS speak-selection (`voice --speak-selection`), explicitly unbinding the upstream terminal bind in `custom/keybinds.lua` (`hl.unbind("SUPER + T")`).
- **D-03:** Terminal access remains fully functional via the existing chords `SUPER + Return` and `CTRL + ALT + T`; no secondary rebind for the terminal is required.
- **D-04:** Enforce unlocked-only execution (`locked = false` / standard `bind`). Prevent accidental microphone activation or transcription keystroke injection when the desktop session screen is locked (`hyprlock`).

### Configuration Target & Installation Tooling
- **D-05:** Provide desktop auto-detection in `voice.py --install-hotkey` (and `--install-hyprland`): Detect active Hyprland sessions (`HYPRLAND_INSTANCE_SIGNATURE` or `hyprctl`), locate `~/.config/hypr/custom/keybinds.lua`, and safely install the keybinding block. Provide `--print-hyprland` to preview the block without writing.
- **D-06:** Format the configuration inside an idempotent delimited block:
  ```lua
  -- voicemode start
  hl.unbind("SUPER + T")
  hl.bind("SUPER + SHIFT + M", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --toggle"), { description = "Voice STT: Push-to-talk toggle" })
  hl.bind("SUPER + T", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --speak-selection"), { description = "Voice TTS: Speak selection" })
  -- voicemode end
  ```
- **D-07:** Preserve dotfiles symlinks: `~/.config/hypr/custom/keybinds.lua` is symlinked to `~/.dotfiles/stow/hypr/.config/hypr/custom/keybinds.lua`. The installer must resolve the real path (`keybinds_path.resolve()`) and update in-place, never replacing the symlink with a regular file.
- **D-08:** Tailor installer strictly to the system's `dots-hyprland` Lua configuration structure (`custom/keybinds.lua`).
- **D-09:** Automatically reload Hyprland after keybinding installation by invoking `hyprctl reload` so shortcuts become active immediately without restarting the session.

### Daemon Invocation, Binary Paths & Signal Handling
- **D-10:** Use expanded full path `$HOME/.local/bin/voice` (or `HOME .. "/.local/bin/voice"`) in `hl.dsp.exec_cmd` to guarantee executable discovery regardless of Hyprland's session environment PATH.
- **D-11:** **Eliminate Double-Tap Startup Race:** To prevent sending `SIGUSR1` to a newly spawned child before Python registers its signal handler (which would crash the child via default signal termination), track lifecycle states in `recorder.pid` (`starting` -> `recording` -> `transcribing` -> `idle`). If toggled while in `starting`, wait up to 300ms for child readiness before signaling.
- **D-12:** **Transcribing / Busy State Protection:** The recorder process retains its PID lock throughout transcription and text injection until `insert_text` finishes. If the hotkey is pressed while `transcribing`, immediately emit a double-low busy cue (`play_cue(args, "error")`) without interrupting the active typing sequence.
- **D-13:** **Clean Signal Differentiation:**
  - `SIGUSR1`: Sole trigger for graceful stop, transcription, and text typing.
  - `SIGTERM` / `SIGINT`: Immediate clean cancellation (unlinks audio buffer and PID without injecting partial text into the focused window).
- **D-14:** **Symmetric Mutex:**
  - Starting STT recording immediately calls `stop_tts(args, quiet=True)` to silence speaker audio and prevent bleed into the microphone.
  - Starting TTS (`speak_selection`) stops any active STT recording to avoid concurrent audio operations.
- **D-15:** **Stale PID Process Verification:** Hardened `process_alive(pid)` checks both `os.kill(pid, 0)` and inspects `/proc/<pid>/cmdline` to ensure the PID belongs to voicemode/python before signaling, preventing misdirected signals if Linux recycled a PID.
- **D-16:** **Safety Watchdogs:**
  - Max recording duration ceiling of 300s (5 minutes) default, overrideable via `VOICE_MAX_RECORDING_SECONDS`.
  - Watchdog timeout of 60s during transcription/typing to prevent an unkillable daemon state in case of unexpected backend deadlock.

### Desktop UX & Feedback Behavior
- **D-17:** **Focus-Safe STT Feedback:** Rely on audio sine chimes (880 Hz start chime, dual-tone stop chime, error chime) for the normal STT push-to-talk loop. Suppress routine "Recording...", "Transcribing...", and "Transcript inserted" desktop notifications to prevent Wayland notification daemons (SwayNC/Mako/Quickshell) from stealing keyboard focus during `wtype` keystroke simulation.
- **D-18:** Desktop notification toasts for STT are reserved strictly for exceptional states: errors, no-speech detected, or safety recording duration ceilings.
- **D-19:** **Periodic Audio Cue:** Play a quiet audio tick (8% volume, 55ms) every 5 seconds while recording is active to provide ongoing auditory confirmation that the microphone is hot (`VOICE_RECORDING_BEEP_INTERVAL=5`).
- **D-20:** **TTS Notification Feedback:** Maintain informational toasts for TTS (`Speaking selection: "..."` preview and `Speech stopped` confirmation) configured with low urgency and quick auto-dismiss (`-u low -t 2000`).

### The Agent's Discretion
- Internal timeout calibration for readiness polling (300ms limit).
- Exact regex pattern matching for finding existing `-- voicemode start` blocks in `custom/keybinds.lua`.
- Signal mask setup order during daemon initialization.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core Implementation & Daemon Architecture
- `voice.py` — Complete standalone application containing `toggle_background_recording`, `run_background_recording`, `read_pid`, `write_pid`, `type_text`, and `install_gnome_hotkey`.
- `/home/pera/.local/bin/voicemode` — Launcher bash wrapper setting `PIPEWIRE_PROPS` and invoking the Python 3.12 virtualenv.

### Hyprland Configuration & Keybinds
- `/home/pera/.config/hypr/custom/keybinds.lua` (resolves to `/home/pera/github_repo/.dotfiles/stow/hypr/.config/hypr/custom/keybinds.lua`) — User keybinding definitions and upstream unbind location.
- `/home/pera/.config/hypr/hyprland/keybinds.lua` — Upstream `dots-hyprland` base keybinding rules.

### Prior Phase Context
- `.planning/phases/01-environment-audio-subsystem/01-CONTEXT.md` — Audio subsystem, virtualenv setup, PipeWire conventions, and sine tone synthesis.
- `.planning/phases/02-wayland-keystroke-injection/02-CONTEXT.md` — `wtype` typing backend, settling delays, dual clipboard mirroring.
- `.planning/phases/03-text-to-speech-model-asset-pipeline/03-CONTEXT.md` — Kokoro ONNX offline TTS, primary selection capture, TTS background player lifecycle.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `toggle_background_recording(args)` (`voice.py:1251`): Main entry point for `--toggle`, reads PID and branches to `os.kill(pid, SIGUSR1)` or `subprocess.Popen`.
- `run_background_recording(args)` (`voice.py:1277`): Worker process event loop capturing audio until `SIGUSR1`, then calling `recorder.stop_to_wav()`, `load_model()`, `transcribe()`, and `insert_text()`.
- `read_pid()`, `write_pid()`, `remove_pid()`, `process_alive()` (`voice.py:567-615`): Filesystem PID tracking helpers in `$XDG_RUNTIME_DIR/voice-stt/`.
- `stop_tts(args)` (`voice.py:932`): Silences active TTS background playback.
- `play_cue(args, cue)` & `play_cue_async(args, cue)` (`voice.py:487-509`): Sine tone synthesis for start, stop, recording tick, and error cues.

### Established Patterns
- **Detached Worker Pattern:** Background recording and synthesis workers spawned with `subprocess.Popen(..., start_new_session=True, close_fds=True)` and redirected stdout/stderr to `$STATE_DIR/voice.log` / `tts.log`.
- **Atomic State Directory:** `$XDG_RUNTIME_DIR/voice-stt/` contains ephemeral lock and PID files.
- **PipeWire Audio Tagging:** `PULSE_PROP_application.name=voicemode` ensures streams appear with proper application names in system mixers.

### Integration Points
- `install_hotkey` CLI flag: Expand detection to support Hyprland via `custom/keybinds.lua` alongside existing GNOME gsettings support.
- `hyprctl reload`: Invoked via subprocess to reload Hyprland configuration dynamically.
- `SIGUSR1` and `SIGTERM` handlers: Register early in `run_background_recording` to handle signals cleanly.

</code_context>

<specifics>
## Specific Ideas

- **STT Push-to-Talk Shortcut:** `SUPER + SHIFT + M`
- **TTS Speak Selection Shortcut:** `SUPER + T` (with `hl.unbind("SUPER + T")`)
- **Block Format in `custom/keybinds.lua`:**
  ```lua
  -- voicemode start
  hl.unbind("SUPER + T")
  hl.bind("SUPER + SHIFT + M", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --toggle"), { description = "Voice STT: Push-to-talk toggle" })
  hl.bind("SUPER + T", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --speak-selection"), { description = "Voice TTS: Speak selection" })
  -- voicemode end
  ```
- **Auditory Feedback:** 880 Hz on start, 5s quiet tick while recording, descending chime on stop, double-low chime on error or busy.
- **No Focus-Stealing Toasts:** Routine toasts are suppressed during dictation so `wtype` keystrokes never get dropped into notification surfaces.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed strictly within Phase 4 scope.

</deferred>

---

*Phase: 04-Hyprland Integration & Daemon Lifecycle*
*Context gathered: 2026-09-19*
