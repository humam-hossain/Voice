---
phase: 10-accuracy-loop-portability-hardening
plan: 01
subsystem: telemetry
tags: [durability, outlier-detection, corpus-capture, fallback, audio]

requires:
  - phase: 06-foundations-ledger-status-contract
    provides: telemetry ledger schema and status publishing

provides:
  - Resilient degraded execution across hostile environments (unset XDG_RUNTIME_DIR, non-standard UID, read-only state, full disk ENOSPC, non-16kHz audio, 4GB RAM)
  - Always-on outlier detection (RTF > 1.0 or tail decode > 10.0s) recorded in metrics.jsonl with zero focus-stealing notifications or sound cues
  - Opt-in diagnostic corpus capture (0700/0600 permissions, 50-file / 100MB FIFO cap, 1GB disk space check, 60s grace period)
  - CLI purge command (--purge-corpus)

affects:
  - 10-02-PLAN.md
  - 10-03-PLAN.md
  - voicemode_report.py
  - voice --doctor

actuals:
  tokens: 12500
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - In-memory numpy array decoding fallback on disk write errors (ENOSPC)
    - Focus-safe telemetry outlier classification with zero desktop UI interruptions
    - Atomic file creation via temporary files with strict 0600 POSIX permissions

key-files:
  created:
    - tests/test_durability.py
  modified:
    - voicemode_telemetry.py
    - voice.py
    - tests/test_telemetry.py

key-decisions:
  - "In-memory float32 numpy array fallback in Recorder._write_chunk_file and transcribe_timed prevents dictation failure on full disk (ENOSPC)"
  - "Outliers are tagged without desktop notifications or audio cues to protect active window focus during keystroke injection"
  - "Diagnostic corpus capture is disabled by default, strictly bounded by 50-file / 100MB FIFO limits, and stores only relative paths (corpus/*.wav) to preserve privacy"

patterns-established:
  - "Degraded durability fallback pattern: catch ENOSPC/EROFS/EACCES, log warnings to stderr, and continue dictation safely"
  - "Relative corpus path privacy: telemetry records never contain absolute paths or usernames"

requirements-completed:
  - ACC-01
  - ACC-04

coverage:
  - id: D1
    description: "Degraded durability pipeline surviving unset runtime dir, non-standard UID, read-only state, and full disk ENOSPC"
    requirement: ACC-04
    verification:
      - kind: unit
        ref: "tests/test_durability.py#TestDegradedDurability"
        status: pass
    human_judgment: false
  - id: D2
    description: "Always-on outlier detection for RTF > 1.0 and tail decode > 10.0s with focus safety"
    requirement: ACC-01
    verification:
      - kind: unit
        ref: "tests/test_durability.py#TestOutlierDetection"
        status: pass
    human_judgment: false
  - id: D3
    description: "Opt-in diagnostic audio corpus capture with FIFO retention, 0700/0600 permissions, and purge command"
    requirement: ACC-01
    verification:
      - kind: unit
        ref: "tests/test_durability.py#TestCorpusCapture"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-11-02
status: complete
---

# Phase 10: Accuracy Loop, Portability & Hardening — Plan 01 Summary

**Resilient degraded execution fallbacks, always-on outlier classification, and opt-in diagnostic corpus capture with bounded FIFO retention**

## Performance

- **Duration:** 25 min
- **Started:** 2026-11-02T10:26:00Z
- **Completed:** 2026-11-02T10:51:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Implemented degraded durability fallbacks across `voicemode_telemetry.py` and `voice.py`:
  - `get_state_dir()` falls back securely to `/tmp/voice-stt-$UID/` with POSIX permissions 0700 when `XDG_RUNTIME_DIR` is unset or custom UID is in effect (D-28).
  - `append_ledger_row()` and `publish_status()` catch `ENOSPC`, `EROFS`, `EACCES` and log a warning without interrupting dictation (D-29).
  - `Recorder._write_chunk_file()` falls back to in-memory float32 numpy array normalized to `[-1.0, 1.0]` when disk writing fails, and `transcribe_timed()` natively transcribes directly from numpy array input without disk dependency (D-30).
  - Resampling to 16 kHz via `resample_pcm` handles 44.1 kHz and 48 kHz USB mics cleanly (D-31).
  - Clamped Whisper CPU inference threads to `min(4, os.cpu_count() or 4)` and added `gc.collect()` in `finalize_background_run()` to guard 4GB RAM systems (D-32).
- Implemented always-on outlier detection and multi-chunk attribution:
  - `classify_outlier(audio_s, decode_ms)` flags RTF > 1.0 (`rtf_exceeded`) and tail decode > 10.0s (`tail_decode`) with environment variable threshold overrides (D-01).
  - Extended Schema v1 with `outlier`, `outlier_reason`, `corpus_file`, `cold_load`, `failed_chunks`, and `chunks` (D-02, D-17).
  - Allowed `outcome: "partial_success"` in `validate_record()` for resilient multi-chunk partial delivery (D-03, D-19).
  - Enforced focus safety: zero desktop notifications and zero audio cues are emitted on outlier detection (D-06).
- Implemented opt-in diagnostic corpus capture and retention:
  - Configurable via `--capture-corpus [none|outliers|all]` and `VOICEMODE_CORPUS_CAPTURE` (disabled by default) (D-07).
  - Stored in `$XDG_STATE_HOME/voice-stt/corpus/` with 0700 directory permissions and 0600 file permissions (D-08, D-09).
  - Guaranteed privacy by recording only relative paths (`corpus/{filename}.wav`) in telemetry, with zero network communication (D-08, D-09).
  - Enforced FIFO retention quota of 50 files and 100 MB with 60-second grace period protection and abort when free disk space < 1 GB (D-12, D-13, D-14).
  - Added CLI purge command `voice --purge-corpus` to reclaim disk space (D-16).

## Task Commits

1. **Task 1: Degraded Durability Fallback Pipeline** - `e851137` (feat)
2. **Task 2: Always-On Outlier Detection & Multi-Chunk Attribution** - `57ecb2e` (feat)
3. **Task 3: Opt-in Diagnostic Corpus Capture & FIFO Retention** - `881bc12` (feat)

## Files Created/Modified

- `voicemode_telemetry.py` - get_state_dir fallback, classify_outlier, schema v1 extension, corpus management and purge functions.
- `voice.py` - in-memory array transcription fallback, load_model thread clamping, corpus capture integration, --capture-corpus / --purge-corpus CLI flags.
- `tests/test_durability.py` - 20 test cases covering degraded durability, outlier detection, and corpus retention.
- `tests/test_telemetry.py` - added partial_success validation and relative corpus path privacy tests.

## Decisions Made

- Standardized in-memory float32 numpy array passing through `Recorder` to `transcribe_timed` to decouple transcription from disk availability.
- Maintained strict focus safety by guaranteeing zero toasts or sounds on outlier detection.
- Kept corpus paths strictly relative in telemetry to eliminate user path disclosure.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 10-01 hardening, outlier tagging, and corpus infrastructure are in place, ready for Plan 10-02 (reporting outlier visualization, drift tracking, and voice --doctor diagnostics).

---
*Phase: 10-accuracy-loop-portability-hardening*
*Completed: 2026-11-02*
