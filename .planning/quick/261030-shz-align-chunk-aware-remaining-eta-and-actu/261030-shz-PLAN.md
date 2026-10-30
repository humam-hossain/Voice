# Quick Plan: Align Chunk-Aware Remaining ETA and actual_s Ledger Metric

**Goal:** Ensure that when background chunk decoding is active, post-recording ETA predicts only the remaining un-transcribed audio (subtracting audio already decoded in background chunks), and `predicted.actual_s` measures the elapsed transcription wait time from when `shown_s` was displayed to insertion, eliminating false 30–90% error rates.

**Files in scope:**
- `voice.py`
- `tests/test_midrun_eta.py`

## Background & Root Cause
1. In `voice.py:2634-2660` and `2677-2702`, when recording stops, `_compute_eta(live_audio)` and `_compute_eta(d)` are invoked with the total recording audio duration. If 5-second background chunks were already decoded during recording (e.g., 30s decoded out of 33.6s), `_compute_eta` still estimates ETA as if all 33.6s must be decoded from scratch, presenting an over-inflated ETA (e.g., 24s instead of 2–3s).
2. In `voice.py:1232-1233`, `predicted["actual_s"]` is computed as `round(time.monotonic() - t_start, 3)` where `t_start` is recorded when the user *starts* recording. This sets `actual_s` to the total wall-clock session duration (recording time + processing time, e.g., 35.99s).
3. The report then compares `predicted.shown_s` (transcription estimate) against `predicted.actual_s` (total recording + processing duration), producing artificial high error rates.

## Tasks

### 1. Chunk-Aware Remaining ETA in `voice.py`
- In `run_background_recording()`:
  - When stopping recording (at `write_pid_state(pid, "transcribing")`), record `run_state["t_transcribe_start"] = time.monotonic()`.
  - Calculate `transcribed_s = sum(r.audio_s for r in results.values() if r and getattr(r, "audio_s", None))` under `results_lock`.
  - Compute `remaining_audio_s = max(0.0, live_audio - transcribed_s)`.
  - Pass `remaining_audio_s` to `_compute_eta` when publishing the initial transcribing status.
  - When exact duration `d` is known from `stop_to_wav`, recompute `remaining_d = max(0.0, d - transcribed_s)` and pass `remaining_d` to `_compute_eta`.

### 2. Apple-to-Apple `predicted["actual_s"]` Accounting in `voice.py`
- In `finalize_background_run()`:
  - When setting `predicted["actual_s"]`:
    - If `run_state.get("t_transcribe_start")` is present, set `predicted["actual_s"] = round(time.monotonic() - t_transcribe_start, 3)`.
    - Otherwise, fall back to `time.monotonic() - t_start`.
  - Preserve `actual["total_ms"] = round((time.monotonic() - t_start) * 1000.0, 3)` to maintain the total session duration in schema v1.

### 3. Unit and Integration Tests
- In `tests/test_midrun_eta.py`:
  - Add tests verifying that when background chunks have completed transcription prior to `capture_closed.set()`, the published ETA at transcribing transition reflects only the remaining un-transcribed audio duration.
  - Add tests verifying that `predicted["actual_s"]` records elapsed time from `t_transcribe_start` rather than `t_start` when `t_transcribe_start` is provided.
  - Verify that `actual["total_ms"]` continues to record the full elapsed time from `t_start`.

### 4. Verification
- Run `pytest tests/test_midrun_eta.py` and `pytest tests/test_report.py`.
- Run full pytest test suite across the repository to ensure zero regressions.
