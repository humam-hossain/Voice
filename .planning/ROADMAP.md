# Roadmap: voicemode (Arch Linux / Hyprland)

## Overview

Set up and optimize `voicemode` on Arch Linux under Hyprland (Wayland), delivering a complete push-to-talk STT dictation and TTS selection-reading workflow with native Wayland input injection (`wtype`) and isolated Python 3.12 runtime management (`uv`).

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Environment & Audio Subsystem** - Setup Python 3.12 via `uv` and verify PortAudio/PipeWire audio capture (completed 2026-09-18)
- [x] **Phase 2: Wayland Keystroke Injection** - Implement native `wtype` typing backend in `voice.py` (completed 2026-09-19)
- [ ] **Phase 3: Text-to-Speech & Model Asset Pipeline** - Download Kokoro ONNX assets and verify Wayland selection TTS
- [ ] **Phase 4: Hyprland Integration & Daemon Lifecycle** - Configure Hyprland shortcuts and verify background daemon toggle
- [ ] **Phase 5: End-to-End System Verification** - Perform end-to-end validation across multiple application windows

## Phase Details

### Phase 1: Environment & Audio Subsystem

**Goal**: Establish a functional Python 3.12 virtual environment with `uv` and verify PortAudio/PipeWire audio capture and playback.
**Mode**: mvp
**Depends on**: Nothing (first phase)
**Requirements**: [ENV-01, ENV-02]
**Success Criteria** (what must be TRUE):

  1. Python 3.12 virtual environment created via `uv` with all STT and TTS dependencies installed cleanly.
  2. Microphone audio captures correctly via PortAudio over PipeWire and audio cue chimes play without distortion.
  3. `voice.py --check` successfully loads Faster-Whisper model on CPU int8.

**Plans**: TBD

Plans:

- [x] 01-01-PLAN.md
- [x] 01-02-PLAN.md

**Wave 1**

- [x] 01-01: Create Python 3.12 virtual environment using `uv` and install core dependencies

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02: Test and verify PortAudio audio capture and playback over PipeWire

### Phase 2: Wayland Keystroke Injection

**Goal**: Integrate `wtype` into `voice.py` for direct, rootless keystroke typing into active Wayland/Hyprland windows.
**Mode**: mvp
**Depends on**: Phase 1
**Requirements**: [INPUT-01, INPUT-02]
**Success Criteria** (what must be TRUE):

  1. `voice.py` detects and prioritizes `wtype` on Wayland when inserting transcribed text.
  2. Typing delay and special characters are handled smoothly without dropped characters.
  3. Graceful fallback occurs if `wtype` is unavailable.

**Plans**: TBD

Plans:
**Wave 1**

- [x] 02-01: Implement `wtype` backend in `voice.py:type_text`

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02: Test transcript typing into active focused windows

### Phase 3: Text-to-Speech & Model Asset Pipeline

**Goal**: Download and verify local Kokoro ONNX models and test primary selection reading with `ffplay` audio output.
**Mode**: mvp
**Depends on**: Phase 2
**Requirements**: [TTS-01, TTS-02]
**Success Criteria** (what must be TRUE):

  1. Kokoro model weights and voices are downloaded and verified via `voice.py --tts-check`.
  2. Highlighted text captured with `wl-paste --primary` synthesizes to audio and plays back via `ffplay`.
  3. `--stop-tts` immediately halts active TTS playback.

**Plans**: TBD

Plans:
**Wave 1**

- [ ] 03-01: Download and verify Kokoro ONNX model weights and voice assets

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 03-02: Verify Wayland primary selection text capture and audio playback

### Phase 4: Hyprland Integration & Daemon Lifecycle

**Goal**: Configure Hyprland global keybindings and verify background STT daemon toggling via signals.
**Mode**: mvp
**Depends on**: Phase 3
**Requirements**: [HYPR-01, HYPR-02]
**Success Criteria** (what must be TRUE):

  1. Hyprland configuration snippet is provided and verified with `$mainMod+B` (STT) and `$mainMod+T` (TTS).
  2. Pressing `$mainMod+B` starts background recording daemon, updates PID file, and plays start chime.
  3. Pressing `$mainMod+B` again stops recording, triggers transcription, and types text into active window.

**Plans**: TBD

Plans:

- [ ] 04-01: Document and configure Hyprland keybindings in `hyprland.conf`
- [ ] 04-02: Verify background recording daemon lifecycle and signal handling

### Phase 5: End-to-End System Verification

**Goal**: Validate full desktop voice dictation and speech synthesis across different applications under Hyprland.
**Mode**: mvp
**Depends on**: Phase 4
**Requirements**: [VERIF-01, VERIF-02]
**Success Criteria** (what must be TRUE):

  1. Push-to-talk dictation successfully types spoken sentences into terminal and GUI editor windows.
  2. Selection-to-speech speaks highlighted text from web browser or document reader.
  3. Setup guide and troubleshooting notes for Arch Linux + Hyprland are documented.

**Plans**: TBD

Plans:

- [ ] 05-01: Conduct comprehensive end-to-end tests across Wayland applications
- [ ] 05-02: Finalize documentation and setup guide for Arch Linux

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Environment & Audio Subsystem | 2/2 | Complete    | 2026-09-18 |
| 2. Wayland Keystroke Injection | 2/2 | Complete    | 2026-09-19 |
| 3. Text-to-Speech & Model Asset Pipeline | 0/2 | Not started | - |
| 4. Hyprland Integration & Daemon Lifecycle | 0/2 | Not started | - |
| 5. End-to-End System Verification | 0/2 | Not started | - |
