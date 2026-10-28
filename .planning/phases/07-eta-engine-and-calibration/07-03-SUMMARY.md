---
phase: 07-eta-engine-and-calibration
plan: 03
subsystem: calibration-persistence-cli
tags: [telemetry, calibration, mad-confidence, cold-boot, cli, kill-switch]

# Dependency graph
requires:
  - 07-01
  - 07-02
provides:
  - "Post-paste calibration cache update in finalize_background_run strictly after text insertion"
  - "Gating predicate _is_calibration_excluded filtering failed, fallback, cold, contended, and outlier runs"
  - "MAD-based confidence scoring (1.0 - MAD/median) over bounded residuals window of 30 items"
  - "Cold boot detection via tmpfs marker $XDG_RUNTIME_DIR/voice-stt/.boot_session with 0o600 permissions"
  - "CLI flag --reset-calibration removing cache and setting reset epoch timestamp"
  - "CLI flag --status --json exposing extended ETA fields (revision_count, last_revised_at, key_level, key_n, overrun)"
  - "Environment kill switch VOICE_ETA=off suppressing ETA calculations across telemetry and CLI"
  - "Test suite in tests/test_eta_cli.py covering ETA-03 and ETA-09"
affects: [08-packaging-verification]

# Tech tracking
tech-stack:
  added: []
  patterns: [post-paste cache update, exclusion gating, mad confidence scoring, tmpfs boot detection, cli reset epoch, env kill switch]

key-files:
  created:
    - tests/test_eta_cli.py
  modified:
    - voicemode_telemetry.py
    - voice.py
    - tests/test_status_contract.py

key-decisions:
  - "Worker finalization updates calibration cache post-paste, guaranteeing text insertion is never delayed by disk I/O"
  - "Excluded records (errors, fallbacks, cold runs, high load > 3600ms, rate outliers) remain in ledger but are omitted from calibration accumulators"
  - "Cold boot detection uses tmpfs marker .boot_session with 0o600 permissions, naturally reset across reboots"
  - "Confidence score uses 1.0 - MAD/median on last 30 residuals, clamped to [0.0, 1.0]"
  - "CLI --reset-calibration prints 'Calibration reset to priors.' and writes reset epoch timestamp so subsequent rebuilds ignore older ledger rows"
  - "VOICE_ETA=off suppresses ETA calculations across all telemetry queries, returning None for all ETA fields"

patterns-established:
  - "voicemode_telemetry.update_calibration_from_run executed defensively inside finalize_background_run"
  - "check_and_mark_boot_session invoked during worker initialization to identify cold runs"

requirements-completed: [ETA-03, ETA-09]

coverage:
  - deliverable: "Worker finalization calibration persistence post-paste"
    verification:
      kind: pytest
      ref: tests/test_eta_cli.py#TestCalibrationPersistence.test_post_paste_finalization_updates_calibration
      status: pass
    human_judgment: false
  - deliverable: "Exclusion gating for failed, fallback, cold, and outlier runs"
    verification:
      kind: pytest
      ref: tests/test_eta_cli.py#TestCalibrationPersistence.test_exclusion_failed_outcome
      status: pass
    human_judgment: false
  - deliverable: "MAD confidence score and bounded residuals window"
    verification:
      kind: pytest
      ref: tests/test_eta_cli.py#TestCalibrationPersistence.test_mad_confidence_basic
      status: pass
    human_judgment: false
  - deliverable: "Cold boot detection via tmpfs marker"
    verification:
      kind: pytest
      ref: tests/test_eta_cli.py#TestETACLI.test_boot_session_cold_detection
      status: pass
    human_judgment: false
  - deliverable: "CLI --reset-calibration and reset epoch"
    verification:
      kind: pytest
      ref: tests/test_eta_cli.py#TestETACLI.test_reset_calibration_cli_output
      status: pass
    human_judgment: false
  - deliverable: "Extended --status --json fields"
    verification:
      kind: pytest
      ref: tests/test_eta_cli.py#TestETACLI.test_status_json_eta_fields
      status: pass
    human_judgment: false
  - deliverable: "VOICE_ETA=off kill switch"
    verification:
      kind: pytest
      ref: tests/test_eta_cli.py#TestETACLI.test_voice_eta_kill_switch
      status: pass
    human_judgment: false
---

# Plan 07-03: Calibration Persistence, Cold Boot, and CLI Integration Summary

Plan 07-03 completes Wave 3 of Phase 07, closing the learning loop from executed dictation sessions to persistent calibration accumulators, implementing exclusion gating for abnormal runs, cold boot detection via tmpfs, and CLI inspection and management controls.

## Key Changes Implemented

1. **Worker Finalization & Calibration Persistence (ETA-03, D-04):**
   - In `voice.py`: In `finalize_background_run()`, invoked `voicemode_telemetry.update_calibration_from_run(record)` strictly post-paste and after ledger row write, wrapped in defensive exception handling to guarantee audio insertion is never delayed.
   - In `voicemode_telemetry.py`: Updated `update_calibration_from_run()` to track residuals for successful runs, update L0/L1/L2 accumulators for non-excluded runs, maintain bounded residuals (last 30 runs), update MAD confidence, and atomically save to `calibration.json` with `0o600` permissions.

2. **Exclusion Gating (ETA-03, D-18, D-31):**
   - Implemented `_is_calibration_excluded()` in `voicemode_telemetry.py` to filter out:
     - Non-success outcomes (`outcome != "success"`)
     - Fallback engine executions (`fallback_used == True`)
     - Cold boot runs (`source == "cold"`)
     - Load contention proxy runs (`load_ms > 3600.0`, 3x shipped prior load)
     - Rate outliers (`rate < 0.01` or `rate > 10.0`)
   - Excluded runs remain in `metrics.jsonl` for observability while preserving calibration accumulator purity.

3. **MAD Confidence Score (ETA-03, D-28):**
   - Implemented `compute_mad_confidence()` calculating $1.0 - \text{MAD} / \text{median}$ on the bounded residuals window, clamped to $[0.0, 1.0]$.

4. **Cold Boot Detection (ETA-03, D-19, D-20):**
   - Implemented `check_and_mark_boot_session()` using tmpfs marker `$XDG_RUNTIME_DIR/voice-stt/.boot_session` with `0o600` permissions.
   - Connected cold boot detection into `run_background_recording()` initialization, reporting `source="cold"` and `confidence="low"` on first run after boot.

5. **CLI Controls & Extended JSON Status (ETA-09, D-03, D-11, D-30):**
   - Connected `--reset-calibration` in `main()` to delete `calibration.json`, establish a timestamped `.calibration_reset` epoch, and output `"Calibration reset to priors."`.
   - Updated `rebuild_calibration_from_ledger()` to ignore any ledger rows timestamped prior to the reset epoch.
   - Extended `print_status()` for `--status --json` and `--status --json-status` to expose `revision_count`, `last_revised_at`, `key_level`, `key_n`, `eta_source`, `eta_confidence`, `overrun`, `eta_remaining_s`, `eta_epoch`.
   - Connected `VOICE_ETA=off` kill switch in `calibrated_eta_seconds()` and `print_status()` to cleanly suppress ETA fields without affecting dictation.

6. **Test Suite:**
   - Authored `tests/test_eta_cli.py` with 26 automated tests covering all calibration persistence, exclusion rules, MAD confidence calculations, cold boot behavior, CLI reset epoch, JSON fields, and kill switch variants.

## Verification Results

- Unit & CLI tests: `uv run pytest tests/test_eta_cli.py -v` (26 passed in 0.05s)
- Mid-run & smoothing tests: `uv run pytest tests/test_midrun_eta.py -v` (5 passed in 0.02s)
- Core estimator tests: `uv run pytest tests/test_eta_engine.py -v` (10 passed in 0.01s)
- Status contract tests: `uv run pytest tests/test_status_contract.py -v` (9 passed in 2.92s)
- Full regression suite: `uv run pytest -q` (201 passed, 19 subtests passed in 9.32s)
