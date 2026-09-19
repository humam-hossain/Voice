---
phase: "01-environment-audio-subsystem"
plan: "01"
subsystem: infra
tags: [python3.12, uv, faster-whisper, kokoro-onnx, edge-tts, pipewire]

requires: []
provides:
  - Python 3.12 virtualenv managed by uv with all STT and TTS extras
  - Desktop execution launcher ~/.local/bin/voicemode and symlink ~/.local/bin/voice
  - PipeWire/PulseAudio client node stream labeling configuration

actuals:
  tokens: 1850
  tasks: 2
  commits: 2

tech-stack:
  added:
    - cpython-3.12.12
    - uv (virtualenv and packaging manager)
    - faster-whisper>=1.2.1, kokoro-onnx==0.5.0, edge-tts>=7.2.8
  patterns:
    - Zero-activation desktop binary wrapper pattern
    - PipeWire/PulseAudio client node tagging via env variables

key-files:
  created:
    - ~/.local/bin/voicemode
    - ~/.local/bin/voice
    - scripts/voicemode
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Enforce Python 3.12+ in pyproject.toml for binary AI wheel compatibility on Arch Linux"
  - "Install all optional dependencies ([kokoro,edge]) upfront in the virtual environment"
  - "Use env invocation in ~/.local/bin/voicemode to safely pass PULSE_PROP_application.name containing dots"

patterns-established:
  - "Launcher wrapper pattern: ~/.local/bin/voicemode sets audio stream environment before executing venv Python"

requirements-completed: ["ENV-01"]

coverage:
  - id: D1
    description: "Python 3.12 virtual environment initialized with all STT and TTS extras"
    requirement: "ENV-01"
    verification:
      - kind: integration
        ref: "/home/pera/github_repo/Voice/.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12); import faster_whisper, kokoro_onnx, edge_tts, sounddevice, numpy, soundfile'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Desktop launcher script installed in ~/.local/bin with PipeWire stream properties"
    requirement: "ENV-01"
    verification:
      - kind: e2e
        ref: "~/.local/bin/voicemode --help && ~/.local/bin/voice --help && ~/.local/bin/voicemode --status"
        status: pass
    human_judgment: false

duration: 2m
completed: 2026-09-18
status: complete
---

# Phase 01 Plan 01: Environment & Dependency Foundation Summary

**Isolated Python 3.12 virtual environment via uv with full STT/TTS dependencies and desktop launcher wrappers**

## Performance

- **Duration:** 2 min
- **Started:** 2026-09-18T17:33:00Z
- **Completed:** 2026-09-18T17:35:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Updated `pyproject.toml` to enforce Python 3.12+ (`requires-python = ">=3.12"`) and ruff target version `py312`.
- Recreated the project-local virtualenv at `.venv` with Python 3.12.12 using `uv`, installing `faster-whisper`, `kokoro-onnx`, `edge-tts`, `sounddevice`, `soundfile`, and `numpy` upfront with full extras without invoking `pacman`.
- Created executable desktop launcher `~/.local/bin/voicemode` and symlink `~/.local/bin/voice`, injecting PipeWire stream tags and allowing zero-activation execution across the desktop.

## Task Commits

1. **Task 01-01-01: Python 3.12 Virtual Environment & Full Dependency Installation** - `1b8ad0e` (feat)
2. **Task 01-01-02: Desktop Launcher Script & Global Symlink Setup** - `6ae63b4` (feat)

## Files Created/Modified

- `pyproject.toml` - Enforces Python >=3.12 and ruff py312 target version
- `uv.lock` - Deterministic uv dependency lockfile
- `scripts/voicemode` - Tracked repository copy of desktop launcher wrapper
- `~/.local/bin/voicemode` - User executable launcher with PipeWire environment properties
- `~/.local/bin/voice` - Convenience symlink to voicemode

## Decisions Made

- Enforced Python 3.12 explicitly to match tested binary wheel stability across Faster-Whisper, Kokoro, and PyTorch/CTranslate2 runtimes.
- Used `exec env "PULSE_PROP_application.name=voicemode"` in the bash launcher wrapper because bash variable names cannot contain dot (`.`) characters in direct `export` syntax.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Bash export syntax rejected dot in environment variable name**
- **Found during:** Task 01-01-02 (Desktop Launcher Script setup)
- **Issue:** `export PULSE_PROP_application.name="voicemode"` failed in bash with `not a valid identifier` because bash identifiers cannot include dots.
- **Fix:** Switched launcher invocation to `exec env "PULSE_PROP_application.name=voicemode" "${VENV_PYTHON}" "${VOICE_SCRIPT}" "$@"` while keeping `PIPEWIRE_PROPS` as standard export.
- **Files modified:** `~/.local/bin/voicemode`, `scripts/voicemode`
- **Verification:** `~/.local/bin/voicemode --status` and `~/.local/bin/voice --status` succeed cleanly.
- **Committed in:** `6ae63b4`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** None; standard environment passing ensures seamless PipeWire audio labeling.

## Issues Encountered

None - installation and verification completed cleanly.

## User Setup Required

None - no external services or API keys required.

## Next Phase Readiness

- Environment and dependencies are fully operational.
- Ready for Plan 01-02: Audio Subsystem & Whisper CPU Defaults.

---
*Phase: 01-environment-audio-subsystem*
*Completed: 2026-09-18*
