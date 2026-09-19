# Milestones

## v1.0 voicemode (Arch Linux / Hyprland) (Shipped: 2026-09-19)

**Phases completed:** 5 phases, 10 plans, 11 tasks

**Key accomplishments:**

- Isolated Python 3.12 virtual environment via uv with full STT/TTS dependencies and desktop launcher wrappers (Phase 1)
- Direct 16 kHz PortAudio/PipeWire audio capture, async auditory cue engine, and low-latency Faster-Whisper CPU defaults (Phase 1)
- Rootless Wayland keystroke injection via wtype over zwp_virtual_keyboard_v1 with stdin piping, -d 0 mitigation, settling pause, and simulated paste shortcuts (Phase 2)
- Dual-action clipboard persistence, desktop failure alerts, pure Wayland notifications, CLI configuration with daemon serialization, and Wayland dependency documentation (Phase 2)
- Offline-first Kokoro ONNX neural TTS pipeline with atomic download, size verification, and Wayland primary selection reading via ffplay (Phase 3)
- Native Hyprland keybindings (SUPER + SHIFT + M, SUPER + T), GNU Stow symlink preservation, and atomic PID state tracking (Phase 4)
- End-to-end system diagnostics engine (voice --doctor), 3-tier verification suite (voice --verify), and Arch Linux / Hyprland documentation overhaul (Phase 5)

**Milestone Stats:**
- Git range: `1b8ad0e` (feat(01-01)) → `3142192` (docs audit reconciliation) [77 commits]
- Codebase: 4,406 LOC Python (voice.py: 2,728 LOC, test suite: 1,678 LOC across 4 test modules)
- Automated Test Coverage: 103/103 tests passing (100%)
- Requirements: 10/10 v1 requirements satisfied (100%)
- Timeline: 5 days (2026-09-15 to 2026-09-19)

---
