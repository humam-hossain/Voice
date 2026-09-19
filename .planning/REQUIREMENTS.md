# Requirements: voicemode (Arch Linux / Hyprland)

**Defined:** 2026-09-18
**Core Value:** Seamless, low-latency push-to-talk speech dictation and text-to-speech on Arch Linux + Hyprland using local models and native Wayland utilities.

## v1 Requirements

Requirements for initial release on Arch Linux + Hyprland. Each maps to roadmap phases.

### Environment & Audio Subsystem

- [x] **ENV-01**: Setup Python 3.12 virtual environment via `uv` with all STT (`faster-whisper`, `sounddevice`, `numpy`) and TTS (`kokoro-onnx`, `soundfile`, `edge-tts`) dependencies.
- [x] **ENV-02**: Verify PortAudio microphone capture and audio cue playback over PipeWire without latency or sample rate mismatch issues.

### Wayland Typing & Input Injection

- [x] **INPUT-01**: Implement `wtype` as a primary Wayland typing backend in `voice.py` alongside `ydotool` and `xdotool`.
- [x] **INPUT-02**: Configure reliable key-delay and special character handling for `wtype` when injecting transcribed text into focused windows.

### Text-to-Speech & Model Assets

- [x] **TTS-01**: Download and verify Kokoro ONNX model weights (`kokoro-v1.0.onnx`) and voice vectors (`voices-v1.0.bin`) in `models/kokoro/`.
- [x] **TTS-02**: Verify Wayland primary selection text capture (`wl-paste --primary`) and audio output playback via `ffplay`.

### Hyprland Integration & Daemon Lifecycle

- [x] **HYPR-01**: Configure and document Hyprland shortcuts (`$mainMod+B` for STT toggle and `$mainMod+T` for TTS speak-selection) in `hyprland.conf`.
- [x] **HYPR-02**: Verify background daemon process management, PID file tracking, and signal handling (`SIGUSR1`) invoked from Hyprland keybindings.

### End-to-End Verification

- [x] **VERIF-01**: Successfully perform end-to-end voice dictation into active terminal and text editor windows under Hyprland.
- [x] **VERIF-02**: Successfully perform end-to-end text-to-speech reading and stop-playback of highlighted screen text under Hyprland.

## v2 Requirements

Deferred to future releases.

### Advanced Features

- **ADV-01**: Automatic audio level normalization and noise suppression before transcription.
- **ADV-02**: Multi-language transcription hotkey switching or dynamic language detection.
- **ADV-03**: Custom voice cloning support for Kokoro TTS.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Non-Linux platforms (macOS, Windows) | Linux desktop focus; Wayland/X11 specific architecture |
| GUI configuration panel | Preference for lean CLI, environment variables, and config files |
| Root uinput daemon requirement | Native `wtype` eliminates the need to run `ydotoold` as root |
| Cloud STT backends | Offline local transcription with `faster-whisper` is the primary design goal |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENV-01 | Phase 1 | Complete |
| ENV-02 | Phase 1 | Complete |
| INPUT-01 | Phase 2 | Complete |
| INPUT-02 | Phase 2 | Complete |
| TTS-01 | Phase 3 | Complete |
| TTS-02 | Phase 3 | Complete |
| HYPR-01 | Phase 4 | Complete |
| HYPR-02 | Phase 4 | Complete |
| VERIF-01 | Phase 5 | Complete |
| VERIF-02 | Phase 5 | Complete |

**Coverage:**

- v1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-09-18*
*Last updated: 2026-09-18 after initial definition*
