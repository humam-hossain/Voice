---
phase: 09-quickshell-status-pill-integration
plan: 01
subsystem: telemetry
tags: [stt, status, telemetry, whisper, quickshell]

requires:
  - phase: 08-telemetry-accuracy-hardening
    provides: status.json schema v1 and publish infrastructure
provides:
  - Continuously published transcribed_audio_s during tail chunk decode
  - Explicit audio duration publishing during typing state transition
  - Unit tests asserting status v1 schema closure and duration contract
affects: [09-02, quickshell]

actuals:
  tokens: 2800
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns: [monotonic tail decode telemetry publishing, typing duration parity]

key-files:
  created: []
  modified:
    - voice.py
    - tests/test_status_contract.py

key-decisions:
  - "Compute transcribed_s under results_lock in chunk consumer so both recording and tail decode status emissions reflect current decoded chunk audio length."
  - "Publish transcribed_audio_s=d and audio_s=d on typing state transitions so consumer progress stays at 100% throughout text insertion."

patterns-established:
  - "Status decode publishing: tail decode branches must always supply transcribed_audio_s alongside segments and segments_done."

requirements-completed: [UI-01, UI-03]

coverage:
  - id: D1
    description: "Published transcribed_audio_s during tail decode and typing states in voice.py"
    requirement: UI-01
    verification:
      - kind: unit
        ref: "tests/test_status_contract.py#test_tail_decode_publishes_transcribed_audio_s"
        status: pass
    human_judgment: false
  - id: D2
    description: "Typing state publishes transcribed_audio_s and audio_s matching final duration"
    requirement: UI-03
    verification:
      - kind: unit
        ref: "tests/test_status_contract.py#test_typing_state_publishes_transcribed_audio_s_and_audio_s"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-11-01
status: complete
---

# Phase 09 Plan 01: Status Publishing Seam & Contract Tests Summary

**Continuous telemetry publishing of decoded audio duration during STT tail decode and typing transitions.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-11-01T14:00:00Z
- **Completed:** 2026-11-01T14:06:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Updated `run_background_recording` in `voice.py` to calculate total decoded audio duration under `results_lock` and pass `transcribed_audio_s` during tail chunk decoding (`capture_closed.is_set()`).
- Updated typing transitions (`state="typing"`, `phase="insert"`) in `voice.py` for both paste and keyboard typing modes to explicitly publish `transcribed_audio_s=d` and `audio_s=d`.
- Added unit tests in `tests/test_status_contract.py`:
  - `test_tail_decode_publishes_transcribed_audio_s`
  - `test_typing_state_publishes_transcribed_audio_s_and_audio_s`
  - `test_status_v1_keys_conformance`

## Task Commits

Each task was committed atomically:

1. **Task 1: Patch `voice.py` status publishing for tail decode and typing states** - `0751bd1` (feat)
2. **Task 2: Add unit and integration tests for tail decode and typing status publishing in `tests/test_status_contract.py`** - `1df4c7a` (test)

**Plan metadata:** `docs(09-01): complete plan summary`
