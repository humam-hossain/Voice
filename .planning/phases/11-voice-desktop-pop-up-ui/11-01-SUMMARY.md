---
phase: "11"
plan: "01"
subsystem: "ui"
tags:
  - quickshell
  - qml
  - config
  - overlay
requires: []
provides:
  - "load_user_config, save_user_config, get_config_dir, get_config_path in voice.py"
  - "12 settings CLI > env > config > default precedence resolution in parse_args"
  - "VoicePopup.qml desktop overlay component with action buttons, telemetry, config, and recent runs"
affects:
  - "voice.py"
  - "tests/test_config.py"
  - "integrations/quickshell/VoicePopup.qml"
  - "tests/test_pill_integration_simulation.py"
tech-stack:
  added: []
  patterns:
    - "Atomic JSON config file management via tempfile.mkstemp and os.replace"
    - "Hierarchical precedence evaluation (CLI > ENV > config.json > default)"
    - "Material 3 desktop overlay pop-up architecture in Quickshell QML"
key-files:
  created:
    - "tests/test_config.py"
    - "integrations/quickshell/VoicePopup.qml"
    - "/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePopup.qml"
  modified:
    - "voice.py"
    - "tests/test_pill_integration_simulation.py"
key-decisions:
  - "D-03/D-04: Action buttons use Start (#4ade80), Stop (colPrimary), and Cancel (#f43f5e) with Quickshell.execDetached."
  - "D-05/D-06: 12 configuration settings sync immediately to ~/.config/voicemode/config.json with 0600 file and 0700 dir permissions."
  - "D-07/D-08/D-09/D-10: Live state telemetry, recent runs inside StyledFlickable with reverse JSONL parser, and Open Full Report button."
requirements-completed:
  - "POP-01"
  - "POP-02"
duration: "4 min"
completed: "2026-11-03T03:04:00Z"
coverage:
  - deliverable: "Configuration backend persistence and precedence in voice.py"
    verification:
      kind: "pytest"
      ref: "tests/test_config.py"
      status: "pass"
    human_judgment: false
  - deliverable: "VoicePopup.qml overlay component with buttons, state, controls, and recent runs"
    verification:
      kind: "pytest"
      ref: "tests/test_pill_integration_simulation.py#test_popup_components"
      status: "pass"
    human_judgment: false
---

# Phase 11 Plan 01: Core Configuration Backend & VoicePopup Overlay Foundation Summary

Implemented the persistent configuration subsystem in `voice.py`, unit test suite in `tests/test_config.py`, and the foundational `VoicePopup.qml` desktop overlay component.

## Accomplishments

1. **Persistent Configuration Backend (`voice.py`):**
   - Added `get_config_dir() -> Path` resolving `$XDG_CONFIG_HOME/voicemode` (or `~/.config/voicemode`) with `0700` directory permissions.
   - Added `get_config_path() -> Path` resolving `config.json`.
   - Added `load_user_config() -> dict[str, Any]` and `save_user_config(data)` using atomic temporary file write and replacement with `0600` permissions.
   - Added strict precedence resolution (`CLI > Environment Variable > config.json > Default`) in `parse_args()` across all 12 configuration settings: `model`, `device`, `compute_type`, `language`, `chunk_duration`, `output_method`, `beam_size`, `vad_filter`, `beep`, `tts_voice`, `tts_backend`, and `capture_corpus`.
   - Updated `background_argv()` to forward `--vad-filter`, `--chunk-seconds`, and `--capture-corpus`.

2. **Unit Test Suite (`tests/test_config.py`):**
   - 12 comprehensive unit tests validating directory/file paths and permissions, config persistence roundtrip, corruption resilience, and precedence hierarchy for all 12 settings.

3. **Desktop Overlay Component (`VoicePopup.qml`):**
   - Built `VoicePopup.qml` extending `StyledPopup` (width 350px) in both `integrations/quickshell/` and `.dotfiles`.
   - Provided instant action buttons: Start (`#4ade80`), Stop (`colPrimary`), Cancel (`#f43f5e`) via array-based `Quickshell.execDetached`.
   - Provided real-time live telemetry display for recorded duration, transcribed audio, total duration, and character count.
   - Provided 12 interactive configuration controls immediately syncing to `~/.config/voicemode/config.json`.
   - Provided scrollable recent runs card using `StyledFlickable` parsing `metrics.jsonl` in stable reverse chronological order and an "Open Full Report" button invoking `Voice.openReport()`.

## Verification Results

- `uv run pytest tests/test_config.py -x`: 12 passed in 0.10s.
- `uv run pytest tests/test_pill_integration_simulation.py -k test_popup_components -x`: 1 passed in 0.04s.
- Full simulation suite: 23 passed in 0.10s.

## Self-Check: PASSED
