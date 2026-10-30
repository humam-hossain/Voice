---
phase: quick-task
plan: 261030-shz
subsystem: telemetry-eta
tags: [telemetry, eta, chunk-streaming, accuracy, report]
requires: []
provides:
  - Chunk-aware remaining ETA estimation on recording stop
  - Accurate predicted.actual_s measuring transcription wait time from shown_s transition
  - Preservation of actual.total_ms measuring total session duration
affects: [voice.py, tests/test_midrun_eta.py]
actuals:
  tasks: 4
  tests: 264 passed
key-files:
  modified: [voice.py, tests/test_midrun_eta.py]
key-decisions:
  - "In run_background_recording(), subtract already-transcribed audio duration from live audio when computing post-recording ETA."
  - "Publish actual count of completed chunks as segments_done at transcribing transition rather than hardcoded 0."
  - "In finalize_background_run(), record predicted.actual_s as time.monotonic() - t_transcribe_start (falling back to t_start if unset), keeping predicted wait time aligned with actual wait time."
  - "Preserve actual.total_ms measuring total session wall-clock time from t_start."
status: complete
---

# Quick Task 261030-shz Summary

Aligned post-recording remaining ETA estimation with background chunk streaming progress, and aligned `predicted.actual_s` with the actual transcription wait duration from the moment `shown_s` was displayed.

## Key Changes

1. **Chunk-Aware Remaining ETA (`voice.py`):**
   - When recording stops and status transitions to `transcribing/finalize`, `transcribed_s` is summed from `results` under `results_lock`.
   - `_compute_eta` is passed `remaining_audio = max(0.0, live_audio - transcribed_s)` (and subsequently `remaining_d = max(0.0, d - transcribed_s)`).
   - This ensures that if 30s of 33.6s audio were already transcribed in background chunks during recording, the ETA accurately predicts the remaining work (~2–4s) rather than computing an ETA for all 33.6s from scratch (`24s`).
   - Published `segments_done` accurately reflects the count of completed chunks (`done_now`) rather than hardcoded `0`.

2. **Apple-to-Apple `predicted.actual_s` Accounting (`voice.py`):**
   - Recorded `run_state["t_transcribe_start"] = time.monotonic()` when recording ends and transcription state begins.
   - In `finalize_background_run()`, set `predicted["actual_s"] = round(time.monotonic() - t_transcribe_start, 3)` (falling back to `t_start` if `t_transcribe_start` is unset).
   - Preserved `actual["total_ms"] = round((time.monotonic() - t_start) * 1000.0, 3)` to maintain the total session duration in schema v1.
   - Eliminates artificial 30–90% error rates where the countdown wait time (`shown_s`) was compared against the entire recording + typing session wall-clock duration.

3. **Testing (`tests/test_midrun_eta.py`):**
   - Added `test_chunk_aware_remaining_eta_subtracts_pretranscribed_audio` verifying that when 25s of 30s audio are pre-decoded, post-recording ETA reflects remaining audio (`shown_s < 8.0`).
   - Added `test_actual_s_measures_transcription_duration_not_recording_time` verifying that `predicted.actual_s` measures time from `t_transcribe_start`, while `actual.total_ms` measures from `t_start`.
   - All 264 test suite tests pass cleanly.
