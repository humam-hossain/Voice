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
- ✓ Arch Linux Python environment setup via `uv` with Python 3.12 — Phase 1
- ✓ Wayland keystroke injection support via `wtype` without root daemon — Phase 2
- ✓ Kokoro model assets download, verification, and headless playback — Phase 3
- ✓ Hyprland native Lua keybindings (`SUPER + SHIFT + M`, `SUPER + T`) with Stow symlink preservation — Phase 4
- ✓ Daemon lifecycle hardening, double-tap race mitigation, signal differentiation, and focus-safe notifications — Phase 4
- ✓ End-to-end verification of STT dictation and TTS playback under Hyprland — Phase 5

### Active

- [ ] Automatic audio level normalization and noise suppression before transcription (ADV-01)
- [ ] Multi-language transcription hotkey switching or dynamic language detection (ADV-02)
- [ ] Custom voice cloning support for Kokoro TTS (ADV-03)

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
- **Shipped State**: Shipped v1.0 with 4,406 LOC Python, 103 passing automated tests, `voice --doctor` diagnostics, and `voice --verify` integration suite.

## Constraints

- **Python Version**: Python 3.12 virtual environment via `uv` (binary wheel compatibility for AI inference runtimes).
- **Wayland Protocol**: Hyprland requires virtual keyboard protocols (`wtype`) or uinput (`ydotool`) for simulated keystrokes.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use `uv` with Python 3.12 | Arch Linux system Python is 3.14, which lacks prebuilt binary wheels for `faster-whisper` / `ctranslate2` / `onnxruntime` | ✓ Validated in Phase 1 |
| Add `wtype` support for Wayland typing | Native Wayland tool already installed on system; does not require root permissions or `ydotoold` daemon | ✓ Validated in Phase 2 |
| Kokoro ONNX offline TTS with atomic download and size guards | Prevent corruption from interrupted downloads and strictly enforce offline privacy without cloud fallback | ✓ Validated in Phase 3 |
| Wayland primary selection read with 1.0s timeout | Prevent hangs if client deadlocks and read non-destructively without clobbering regular clipboard | ✓ Validated in Phase 3 |
| Hyprland Lua keybindings with Stow symlink preservation | User runs dots-hyprland; canonical path resolution writes to stow repo target without breaking symlinks | ✓ Validated in Phase 4 |
| Atomic multi-token PID state tracking | Prevent double-tap race conditions and differentiate clean stop/transcribe (`SIGUSR1`) from abort (`SIGTERM`) | ✓ Validated in Phase 4 |
| Focus-safe notification policy | Suppress routine STT toasts to prevent Wayland active window focus stealing before `wtype` typing | ✓ Validated in Phase 4 |
| Default to CPU int8 for STT | Intel UHD Graphics 770; CPU int8 provides fast, stable inference without complex driver setup | ✓ Validated in Phase 1 |
| System diagnostics engine and 3-tier verification | Built-in `voice --doctor` and `voice --verify` provide self-diagnostics and live compositor validation | ✓ Validated in Phase 5 |

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
*Last updated: 2026-09-19 after v1.0 milestone*
