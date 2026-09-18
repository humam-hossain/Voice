# voicemode (Arch Linux / Hyprland)

## What This Is

A lightweight, desktop-global speech-to-text dictation and text-to-speech utility for Linux. It provides push-to-talk transcription that types directly into the active focused window and on-demand neural text-to-speech reading of highlighted text, tailored specifically for Arch Linux running Hyprland on Wayland.

## Core Value

Seamless, low-latency push-to-talk speech dictation and text-to-speech on Arch Linux + Hyprland using local models and native Wayland utilities.

## Requirements

### Validated

- ✓ Local push-to-talk speech recording via PortAudio/SoundDevice — existing
- ✓ Local speech-to-text transcription via `faster-whisper` (CTranslate2) — existing
- ✓ In-memory synthesized auditory cues (start, stop, reminder chime) — existing
- ✓ Local neural text-to-speech via `kokoro-onnx` — existing
- ✓ Cloud-based text-to-speech fallback via Microsoft Edge TTS — existing
- ✓ X11 & Wayland selection reading via `xclip` / `wl-clipboard` — existing
- ✓ Background process coordination via PID files and Unix signals (`SIGUSR1`) — existing

### Active

- [ ] Arch Linux Python environment setup via `uv` with Python 3.12 (ensuring C-extension compatibility for CTranslate2 and ONNX Runtime)
- [ ] Wayland keystroke injection support via `wtype` for native Hyprland text typing without requiring root `ydotoold` daemon
- [ ] Hyprland shortcut configuration documentation and setup for `$mainMod+B` (STT toggle) and `$mainMod+T` (TTS selection)
- [ ] Kokoro model assets download and verification on Arch Linux
- [ ] End-to-end verification of STT dictation and TTS playback under Hyprland

### Out of Scope

- Non-Linux platforms (Windows, macOS) — Linux desktop utility
- GUI configuration application — maintain lean CLI and environment-variable/config file architecture
- GNOME-specific dependencies on Hyprland — avoid hard dependency on `gsettings`

## Context

- **Operating System**: Arch Linux (rolling, kernel 7.2+, system Python 3.14).
- **Desktop Environment**: Hyprland on Wayland (`XDG_SESSION_TYPE=wayland`).
- **Hardware**: Intel Alder Lake-S GT1 [UHD Graphics 770], Intel HD Audio; CPU int8 Whisper inference.
- **Audio Subsystem**: PipeWire with PipeWire-Pulse / ALSA emulation.
- **Wayland Utilities**: `wl-clipboard` (`wl-copy`, `wl-paste`), `wtype` (virtual keyboard typing), `ffmpeg` (`ffplay`).
- **Python Management**: Managed via `uv` using Python 3.12, since Python 3.14 lacks precompiled wheels for `ctranslate2` and `onnxruntime`.

## Constraints

- **Python Version**: Python 3.12 virtual environment via `uv` (binary wheel compatibility for AI inference runtimes).
- **Wayland Protocol**: Hyprland requires virtual keyboard protocols (`wtype`) or uinput (`ydotool`) for simulated keystrokes.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use `uv` with Python 3.12 | Arch Linux system Python is 3.14, which lacks prebuilt binary wheels for `faster-whisper` / `ctranslate2` / `onnxruntime` | — Pending |
| Add `wtype` support for Wayland typing | Native Wayland tool already installed on system; does not require root permissions or `ydotoold` daemon | — Pending |
| Hyprland keybindings via `hyprland.conf` | User runs Hyprland; GNOME `gsettings` does not apply | — Pending |
| Default to CPU int8 for STT | Intel UHD Graphics 770; CPU int8 provides fast, stable inference without complex driver setup | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-18 after initialization*
