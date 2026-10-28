---
phase: 06-foundations-ledger-status-contract
plan: 07
gap_closure: true
gap_ids: [G-06-6, G-06-7]
subsystem: transcription-lifecycle
tags: [timing, evidence, consumer-queue, early-load, finalize, watchdog, reconciliation, hermetic-tests]

# Dependency graph
requires: [06-04]
provides:
  - "transcribe_timed measuring full generator consumption and returning TranscriptionEvidence"
  - "Early WhisperModel loading on worker consumer thread during recording"
  - "Concurrent chunk decoding via consumer queue during audio capture"
  - "Single finalize authority (finalize_background_run) writing exactly one ledger row per run"
  - "Watchdog terminal row written before exit on freeze"
  - "Next-invocation reconciliation (reconcile_abandoned_run) under flock for dead workers"
affects: [07-01, 07-02, 07-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [producer-consumer queue, early model preloading, exactly-once finalizer, watchdog timeout row, dead worker reconciliation]

key-files:
  created:
    - tests/test_timing.py
    - tests/test_incremental_transcription.py
    - tests/test_lifecycle_outcomes.py
  modified:
    - voice.py
    - pyproject.toml
    - tests/test_audio_chunking.py
    - tests/test_hyprland_daemon.py
    - tests/test_status_contract.py
    - tests/test_telemetry.py
    - tests/test_verification_doctor.py

key-decisions:
  - "Full faster-whisper generator consumption timed via list(raw_segments) to capture true decode latency"
  - "Model loads on worker consumer thread during audio capture; completed chunks decoded in background"
  - "finalize_background_run acts as sole exit authority with threading lock and finalized flag"
  - "Watchdog handler calls finalize_background_run with outcome watchdog_timeout before exit"
  - "reconcile_abandoned_run runs under with_pid_lock on toggle to write abandoned rows for killed processes"

requirements-completed: [DEC-01, DEC-02, DEC-03, DEC-04, LED-02, FND-04, STS-05]

# Metrics
duration: ~25min
completed: 2026-10-29
status: complete
---

# Phase 06: Plan 06-07 Summary (Gap Closure G-06-6 & G-06-7)

**Delivered early model loading during capture, concurrent chunk decoding queue, timed generator transcription seam, single finalizer authority, watchdog timeout row, and abandoned run reconciliation.**

## Accomplishments
- **Timed Transcription Seam (`transcribe_timed`)**: Added `TranscriptionEvidence` dataclass and wrapped segment materialization `list(raw_segments)` with monotonic timing to capture true `decode_ms`. Extracted decoder metadata (`avg_logprob`, `compression_ratio`, `no_speech_prob`, `temperature`, `vad_audio_s`, `decoder_segments`) with strict exclusion of transcript text from metrics. Supported GPU-to-CPU fallback with `fallback_load_ms` measurement.
- **Incremental Audio Transcription (`Recorder` + Worker Consumer)**: Added `Recorder.on_chunk_ready` callback and `chunk_audio_s` lookup. Spawned consumer thread during recording that preloads Whisper model early while speech capture occurs. Background consumer transcribes completed chunks via `chunk_queue`, maintaining prompt chaining and segment ordering.
- **Single Finalize Authority (`finalize_background_run`)**: Consolidated worker exit paths (success, cancelled, error, watchdog_timeout) under thread-safe lock with `finalized` flag. Guaranteed exactly one schema-v1 row written to ledger and clean removal of `status.json` and PID file.
- **Watchdog Timeout Row & Abandoned Reconciliation**: Updated `transcription_watchdog_handler` to write `watchdog_timeout` terminal row before exit. Implemented `reconcile_abandoned_run` under toggle flock to detect dead workers and append `abandoned` ledger rows.
- **Test Coverage**: Added 16 new unit tests across `tests/test_timing.py`, `tests/test_incremental_transcription.py`, and `tests/test_lifecycle_outcomes.py`. Migrated existing test mocks to `transcribe_timed`. All 160 unit tests pass hermetically.

## Verification
- `.venv/bin/pytest tests/ -q` -> `160 passed, 19 subtests passed in 8.89s`
- `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` -> `Ran 160 tests: OK`

## Gaps Closed
- **G-06-6**: Every worker process ends in exactly one terminal ledger row (success, cancelled, error, watchdog_timeout); watchdog expiry writes its own row; SIGKILLed runs are reconciled by next invocation as abandoned.
- **G-06-7**: Whisper model loads while recording is in progress (D-05); completed chunks decode incrementally via consumer queue (D-06); full generator consumption timed (DEC-01) and evidence recorded (D-07).
