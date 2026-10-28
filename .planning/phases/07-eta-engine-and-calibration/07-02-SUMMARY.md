---
phase: 07-eta-engine-and-calibration
plan: 02
subsystem: ui-smoothing
tags: [telemetry, eta, hysteresis, smoothing, overrun, segment-generator]

# Dependency graph
requires:
  - 07-01
provides:
  - "Segment yield generator callback in transcribe_timed calculating decoded duration progress"
  - "Mid-run rate blending activating after >= 5.0s of decoded audio"
  - "Asymmetric revision hysteresis via update_midrun_eta suppressing upward jitter"
  - "1-second dwell state machine in calculate_countdown_display before transitioning to Finishing…"
  - "format_eta_pill enforcing single integer format and persistent '~' prefix for uncalibrated/cold sources"
  - "Integration tests in tests/test_midrun_eta.py"
affects: [07-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [generator consumption yield hook, asymmetric revision hysteresis, dwell-overrun state machine, pill formatting]

key-files:
  created:
    - tests/test_midrun_eta.py
  modified:
    - voice.py

key-decisions:
  - "Downward revisions step down immediately without debouncing; upward jumps require delta >= 1.0s and elapsed >= 2.0s"
  - "Remaining ETA dwells at 1s for exactly 1.0 full second before transitioning to Finishing… with overrun: true"
  - "Display is strictly integer seconds with persistent '~' prefix for uncalibrated/cold sources until Finishing…"
  - "ETA is visible only in transcribing/finalize/decode states and nulled during starting/recording"

patterns-established:
  - "transcribe_timed supports on_segment_yield callback gracefully with backward compatibility for mocks"
  - "Revision metrics (count and max upward jump) are tracked in run_state for ledger finalization"

requirements-completed: [ETA-04, ETA-05, ETA-06, ETA-07]

coverage:
  - deliverable: "Whisper generator segment yield mid-run rate blending"
    verification:
      kind: pytest
      ref: tests/test_midrun_eta.py#test_generator_segment_blending
      status: pass
    human_judgment: false
  - deliverable: "Asymmetric revision hysteresis and downward step immediacy"
    verification:
      kind: pytest
      ref: tests/test_midrun_eta.py#test_revision_hysteresis
      status: pass
    human_judgment: false
  - deliverable: "1s dwell overrun state machine and transition to Finishing…"
    verification:
      kind: pytest
      ref: tests/test_midrun_eta.py#test_1s_dwell_and_finishing_transition
      status: pass
    human_judgment: false
  - deliverable: "Persistent '~' prefix and integer display pill"
    verification:
      kind: pytest
      ref: tests/test_midrun_eta.py#test_prefix_persistence
      status: pass
    human_judgment: false
  - deliverable: "ETA visibility lifecycle (hidden during starting/recording)"
    verification:
      kind: pytest
      ref: tests/test_midrun_eta.py#test_eta_visibility_lifecycle
      status: pass
    human_judgment: false

# Metrics
duration: 12 min
completed: 2026-10-29
status: complete
---

# Phase 07 Plan 02: Mid-Run Recalculation & Display Smoothing Summary

Delivered mid-run ETA recalculation and display smoothing in `voice.py` during Whisper segment generator consumption, enforcing asymmetric revision hysteresis, monotonic non-increasing integer countdown, 1s dwell overrun transition to `Finishing…`, visibility lifecycle rules, and `~` prefix persistence.

## Accomplishments

1. **Segment Generator Hook & Mid-Run Blending**: Integrated `on_segment_yield` into `transcribe_timed` and `_consume()`, blending observed decode rate with calibrated initial rate once $\ge 5.0$s of audio has decoded.
2. **Asymmetric Revision Hysteresis**: Implemented `update_midrun_eta()` allowing immediate downward integer steps while debouncing upward jumps (requiring jump $\ge 1.0$s and elapsed $\ge 2.0$s since prior revision).
3. **1s Dwell Overrun Transition**: Implemented `calculate_countdown_display()` dwelling at `1s` for 1.0 second before cleanly transitioning to `Finishing…` with `overrun: true`.
4. **Pill Formatting & Prefix Persistence**: Implemented `format_eta_pill()` preserving `~` prefix across countdown for uncalibrated/prior/cold sources until `Finishing…`, eliminating negative, zero, fractional, or range values.
5. **Visibility Lifecycle**: Ensured ETA is published within 100ms of entering `transcribing` and completely hidden during `starting` and `recording`.

## Verification Results

- `pytest tests/test_midrun_eta.py -v`: 5 passed
- `pytest tests/test_eta_engine.py -v`: 10 passed
- `pytest tests/test_status_contract.py -v`: 9 passed
- Full regression suite: 175 passed, 19 subtests passed

## Self-Check: PASSED
