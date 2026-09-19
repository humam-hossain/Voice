# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — voicemode (Arch Linux / Hyprland)

**Shipped:** 2026-09-19
**Phases:** 5 | **Plans:** 10 | **Tasks:** 11

### What Was Built
- Python 3.12 virtual environment management via `uv` with low-latency Faster-Whisper CPU int8 inference and PipeWire 16 kHz streaming capture.
- Native Wayland keystroke injection engine using `wtype` over `zwp_virtual_keyboard_v1` with delay tuning, special character handling, and clipboard fallback.
- Offline-first Kokoro ONNX neural text-to-speech asset pipeline and Wayland primary selection reader (`ffplay`).
- Native Hyprland shortcut integration (`SUPER + SHIFT + M`, `SUPER + T`), GNU Stow symlink preservation, and atomic multi-token PID daemon management (`recorder.pid`).
- System diagnostics suite (`voice --doctor`), 3-tier compositor verification engine (`voice --verify`), and comprehensive Arch Linux + Hyprland documentation overhaul.

### What Worked
- **Strict TDD & automated test harnesses**: 103 unit and integration tests across 4 modules ensured rock-solid reliability across refactors.
- **Rootless Wayland injection**: Integrating `wtype` eliminated external root daemon dependencies (`ydotoold`), simplifying deployment.
- **In-memory synthesized auditory cues**: Cosine-windowed sine waves generated in numpy provided non-blocking auditory state feedback.
- **Atomic PID lifecycle state machine**: Multi-token state tracking (`starting`, `recording`, `transcribing`, `idle`) fully eliminated double-tap race conditions.

### What Was Inefficient
- **Covered-input digest invalidation**: Editing `voice.py` in later phases invalidated previous phase covered-digest fingerprints, requiring cross-phase audit reconciliation.
- **Symlink detection across dotfile managers**: Required explicit canonical path resolution to avoid replacing GNU Stow symlinks with regular files.

### Patterns Established
- `download_file_with_progress`: Atomic chunked downloads with minimum size validation guards against corrupted neural model files.
- **Focus-safe notification policy**: Suppress routine STT dictation notifications to prevent Wayland active window focus stealing before keystroke simulation.
- `resolve_canonical_path`: Traverse symlinks to target files when modifying configuration managed by dotfile utilities.

### Key Lessons
1. On Wayland desktops, desktop notification popups can steal active window focus; STT typing tools must suppress routine notifications or defer them until keystroke injection is complete.
2. Rolling-release distributions like Arch Linux often ship bleeding-edge system Python (3.14) lacking prebuilt wheels; pinning Python 3.12 via `uv` guarantees binary wheel stability for CTranslate2 and ONNX Runtime.
3. Pre-flight self-diagnostics (`voice --doctor`) drastically improve user experience by pinpointing missing Wayland tools or audio device issues before runtime.

### Cost Observations
- Sessions: 5 phases across 5 days
- Automated verification: 103/103 tests passing, 33/33 observable truths verified, 36/36 exports wired

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Plans | Key Change |
|-----------|----------|--------|-------|------------|
| v1.0 | 5 | 5 | 10 | Initial release: Arch Linux + Hyprland support with wtype and Kokoro TTS |

### Cumulative Quality

| Milestone | Tests | Passing | Requirements Satisfied | Zero-Dep Additions |
|-----------|-------|---------|------------------------|-------------------|
| v1.0 | 103 | 100% | 10/10 (100%) | 0 |

### Top Lessons (Verified Across Milestones)

1. Avoid desktop notification focus-stealing during simulated keystroke insertion under Wayland.
2. Pin runtime Python versions with `uv` on rolling distributions for AI inference wheel compatibility.
