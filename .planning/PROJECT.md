# voicemode (Arch Linux / Hyprland)

## What This Is

A lightweight, desktop-global speech-to-text dictation and text-to-speech utility for Linux. It provides push-to-talk transcription that types directly into the active focused window and on-demand neural text-to-speech reading of highlighted text, tailored specifically for Arch Linux running Hyprland on Wayland.

## Core Value

Seamless, low-latency push-to-talk speech dictation and text-to-speech on Arch Linux + Hyprland using local models and native Wayland utilities.

## Current Milestone: v1.1 Latency Prediction & Telemetry

**Goal:** Show a trustworthy single-number ETA during transcription, and record prediction-vs-actual telemetry so the estimator improves over time and stays portable across CPU/CUDA hardware and model configurations.

**Target features:**
- Lazy imports and lifecycle-integrity fixes so telemetry and status are truthful (Phase 6)
- Per-run JSONL ledger with stage timings, decoder evidence, and privacy allowlist (Phase 6)
- Atomic `status.json` contract; PID file remains state authority (Phase 6)
- Calibrated predictor with mid-run correction and `Finishing…` overrun handling (Phase 7)
- Offline terminal/CSV/HTML accuracy report (Phase 8)
- Quickshell pill ETA with distinct color and click-through to the report (Phase 9)
- Outlier lab, convergence/drift views, portability matrix, and docs (Phase 10)

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

### Active — v1.1 Latency Prediction & Telemetry

Full list with acceptance criteria: `.planning/REQUIREMENTS.md` (48 requirements).

- [ ] Non-transcription commands stay import-light and lifecycle paths stop producing stale state (FND, 5)
- [ ] Privacy-safe per-run telemetry ledger with honest stage timings (LED/DEC, 11)
- [ ] Atomic advisory `status.json` contract alongside the authoritative PID file (STS, 5)
- [ ] Calibrated single-number ETA with mid-run correction and graceful overrun (ETA, 9)
- [ ] Offline terminal/CSV/HTML accuracy report (RPT, 6)
- [ ] Quickshell pill shows the ETA and opens the report on click (UI, 5)
- [ ] Outlier loop, cross-hardware portability, and hardening (ACC, 7)

### Deferred (carried from v1.0)

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
- **Measured Latency (v1.1 baseline)**: medium.en CPU int8 beam=1, VAD on — 30 s audio → 9.0 s, 60 s → 16.4 s, 115 s → 30.8 s, 180 s → 45.9 s; cold model load 2.2–3.0 s; peak RSS 2129 MB; CPU ≈430%. Clean fit ≈ `1.7 + 0.247 × audio_s`. A pathological 15 s clip took 47–65 s due to Whisper temperature-fallback retries, so calibration must be outlier-robust.
- **Status Bar**: Quickshell (`qs -c ii`); live QML files are symlinks into `/home/pera/github_repo/.dotfiles` (`restow/quickshell/.config/quickshell`), which is authoritative.

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
| ETA is one integer, no range; `~` while uncalibrated, `Finishing…` on overrun | A glanceable number in a two-word-wide pill; confidence and ranges belong in the report | → v1.1 Phase 7 |
| PID file stays state authority; `status.json` is advisory | Keeps the existing bar consumer safe; deleting status never changes state; stale snapshots expire | → v1.1 Phase 6 |
| Report ships before the clickable pill; click opens pre-rendered report via `xdg-open` | A click must never open a missing or cold-generated page | → v1.1 Phases 8-9 |
| Zero new Python dependencies; stdlib + inline SVG | Ledger, robust stats, atomic I/O, and charts are all achievable in stdlib; avoids matplotlib's 40 MB and slow import | → v1.1 |
| No transcript text; character counts only | Privacy baseline enforced by an allowlist serializer and a no-text test | → v1.1 Phase 6 |
| Live Quickshell QML commits in `~/.dotfiles`; vendored copies in `integrations/quickshell/` | Live files are symlinks into the dotfiles repo, which is authoritative for this machine | → v1.1 Phase 9 |

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
*Last updated: 2026-10-26 after v1.1 milestone start*
