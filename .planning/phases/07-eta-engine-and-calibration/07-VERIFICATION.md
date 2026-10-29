---
phase: 07-eta-engine-and-calibration
verified: 2026-10-29T08:05:00Z
status: passed
score: 9/9 requirements verified
---

# Phase 07: ETA Engine & Calibration Verification Report

**Phase Goal:** Deliver a calibrated, honest, single-number transcription latency prediction (ETA) that appears immediately, counts down smoothly, corrects mid-run after Whisper segments, handles overruns truthfully, and learns from local ledger history while gating contaminated runs.
**Verified:** 2026-10-29T08:05:00Z
**Status:** passed

---

## Executive Summary

Phase 7 successfully builds on the Phase 6 ledger and status contract to deliver a high-accuracy, single-number transcription latency prediction engine. The predictor activates within 100 ms of entering `transcribing` using shipped priors on cold/fresh installs, transitions smoothly through a 4-tier hierarchy (L0 to L3) with ratio-of-sums rate calculation and James-Stein shrinkage blending, recalculates mid-run after each Whisper segment using an asymmetric revision hysteresis filter (downward immediate, upward debounced), and clamps on overrun to a 1-second dwell before transitioning to `Finishing…`.

In Plan 07-04, UAT Gap G-07-7 was resolved by exposing `transcribed_audio_s` in the status schema and worker consumer, connecting the Quickshell `Voice.qml` service to `status.json`, and rendering a dual clock (`X:XX | X:XX` — recording duration | audio transcribed so far) in `VoicePill.qml` during parallel chunk recording, as well as displaying the live ETA countdown pill (`~Xs` / `Finishing…`) during transcription.

Persistent calibration updates occur strictly post-paste in worker finalization, updating atomic `calibration.json` cache with `0o600` permissions. Gating predicates exclude failures, fallbacks, cold boot runs, high-load contention (> 3600ms), and rate outliers from fitting while preserving full records in the ledger. Cold boot is detected without external dependencies using `$XDG_RUNTIME_DIR/voice-stt/.boot_session` on tmpfs. Operator CLI verbs (`--reset-calibration`, `--status --json` extended fields, and `VOICE_ETA=off` kill switch) are fully operational.

All 205 automated tests across the entire repository pass hermetically.

---

## 1. Requirements Traceability Verification

All 9 requirements allocated to Phase 7 are implemented, tested, and verified:

| Req ID | Description | Implementation Artifact | Test Suite / Coverage | Status |
|--------|-------------|-------------------------|------------------------|--------|
| **ETA-01** | Estimate formula = finalize + load + rate × audio_s + insert; rate is ratio-of-sums `sum(decode_s)/sum(audio_s)` | `voicemode_telemetry.py:resolve_calibrated_rate`, `calibrated_eta_seconds` | `tests/test_eta_engine.py::TestETAEngine::test_ratio_of_sums_formula` | PASS |
| **ETA-02** | 4-tier key hierarchy (L0..L3) with $n \ge 3$ sample floor and James-Stein shrinkage blending | `voicemode_telemetry.py:extract_hierarchy_keys`, `resolve_calibrated_rate` | `tests/test_eta_engine.py::TestKeyHierarchy` (4 tests) | PASS |
| **ETA-03** | Calibration exclusion filter (failures, fallbacks, cold, contention, outliers) and MAD confidence score | `voicemode_telemetry.py:_is_calibration_excluded`, `compute_mad_confidence`, `update_calibration_from_run` | `tests/test_eta_cli.py::TestCalibrationPersistence` (15 tests) | PASS |
| **ETA-04** | Mid-run segment recalculation with asymmetric revision hysteresis and parallel chunk decoding progress | `voice.py:update_midrun_eta`, `transcribe_timed(on_segment_yield)`, `voicemode_telemetry.py:transcribed_audio_s` | `tests/test_midrun_eta.py::TestMidRunRevisions` (2 tests), `tests/test_status_contract.py` | PASS |
| **ETA-05** | Overrun behavior: 1s floor dwell for 1.0s, then `Finishing…` with `overrun: true` | `voice.py:calculate_countdown_display` | `tests/test_midrun_eta.py::TestOverrunAndDisplay::test_1s_dwell_and_finishing_transition` | PASS |
| **ETA-06** | State visibility: ETA shown during `transcribing`, dual clock `X:XX | X:XX` during recording | `voice.py:_publish_status`, `Voice.qml`, `VoicePill.qml` | `tests/test_midrun_eta.py::TestOverrunAndDisplay::test_eta_visibility_lifecycle` | PASS |
| **ETA-07** | Display format: single integer seconds, uncalibrated/cold prefixed with persistent `~`, dual timers | `voice.py:format_eta_pill`, `Voice.qml`, `VoicePill.qml` | `tests/test_midrun_eta.py::TestOverrunAndDisplay::test_prefix_persistence`, `tests/test_status_contract.py` | PASS |
| **ETA-08** | Prediction horizon endpoint is text insertion start; dynamic model load subtraction while recording | `voicemode_telemetry.py:calibrated_eta_seconds`, `voice.py:_compute_eta` | `tests/test_eta_engine.py::TestTimingEndpoints` (4 tests) | PASS |
| **ETA-09** | `--status --json` exposes extended fields; `--reset-calibration` with epoch reset; `VOICE_ETA=off` kill switch | `voice.py:print_status`, `main`, `voicemode_telemetry.py:reset_calibration` | `tests/test_eta_cli.py::TestETACLI` (11 tests), `tests/test_status_contract.py` | PASS |

---

## 2. Automated Test Suite Results

```text
============================= test session starts ==============================
platform linux -- Python 3.12.12, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/pera/github_repo/Voice
configfile: pyproject.toml
plugins: anyio-4.15.1
collected 205 items

205 passed, 19 subtests passed in 8.96s
============================== 205 passed in 8.96s ==============================
```

- `tests/test_status_contract.py` (18 tests): Verifies status schema v1 closed key validation, atomic write/read semantics, PID authority over status advisory files, heartbeat during recording, `transcribed_audio_s` non-negative clamping and JSON serialization, and `--status --json` CLI output.
- `tests/test_eta_engine.py` (10 tests): Verifies ratio-of-sums computation, hierarchy keys extraction, sample floors, James-Stein shrinkage blending, out-of-bounds rejection, dynamic model load subtraction, text insertion horizon, and status contract extensions.
- `tests/test_midrun_eta.py` (5 tests): Verifies Whisper segment callback blending, asymmetric revision hysteresis (immediate downward, debounced upward), 1s dwell overrun state machine, `Finishing…` transition, state visibility rules, and prefix persistence.
- `tests/test_eta_cli.py` (26 tests): Verifies post-paste calibration cache persistence, file permissions `0o600`, exclusion filtering (outcome, fallback, cold, load contention, extreme rates), MAD confidence scoring, ledger rebuild respecting reset epoch, tmpfs `.boot_session` marker detection, `--reset-calibration` CLI execution, `--status --json` payload schema, and `VOICE_ETA=off` kill switch.
- Regression suites (`test_telemetry.py`, `test_timing.py`, `test_lifecycle_outcomes.py`, `test_incremental_transcription.py`, `test_pid_race.py`, `test_audio_chunking.py`, `test_hyprland_daemon.py`, `test_verification_doctor.py`, `test_wayland_input.py`): 146 tests all passing hermetically.

---

## 3. Success Criteria Verification

1. **Immediate prior ETA:** Verified. `calibrated_eta_seconds()` provides estimate within < 1 ms based on shipped priors (`PRIOR_RTF`) and prefixes uncalibrated sources with `~`.
2. **Smooth countdown and asymmetric revision:** Verified. Monotone non-increasing countdown except for upward jumps $\ge 1.0$s after $\ge 2.0$s elapsed.
3. **1s Dwell and Overrun Transition:** Verified. Overruns dwell at 1s for 1.0s before transitioning to `Finishing…` and recording `overrun: true`.
4. **Learning & Exclusion:** Verified. Non-excluded runs accumulate decode and audio times into `calibration.json`; failed, fallback, cold, contended, and outlier runs are filtered out while persisting in `metrics.jsonl`.
5. **Cold Boot & CLI:** Verified. Tmpfs marker `.boot_session` cleanly marks boot runs; `--reset-calibration` wipes cache and records reset timestamp epoch; `--status --json` exposes extended fields; `VOICE_ETA=off` disables predictions cleanly.
6. **Parallel Transcription & Dual Timer (G-07-7):** Verified. `transcribed_audio_s` emitted during active parallel chunk recording, rendered in desktop status pill as `X:XX | X:XX`, with countdown ETA during transcription.

---

## 4. Conclusion

Phase 7 is verified complete. All 9 requirements (ETA-01 through ETA-09), validation contracts, and UAT gap closure (Plan 07-04) are fulfilled. The codebase is prepared to advance to Phase 08 (Accuracy Report & Click-Through).
