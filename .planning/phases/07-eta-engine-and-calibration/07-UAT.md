---
status: complete
phase: 07-eta-engine-and-calibration
source:
  - 07-01-SUMMARY.md
  - 07-02-SUMMARY.md
  - 07-03-SUMMARY.md
  - 07-04-SUMMARY.md
started: 2026-10-29T08:10:30Z
updated: 2026-10-29T09:16:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Core ETA Estimator & Ratio-of-Sums Engine
expected: Ratio-of-sums rate resolution sum(decode_s)/sum(audio_s), 4-tier hierarchy (L0..L3), James-Stein shrinkage blending, dynamic model load subtraction, and prediction horizon ending at text insertion all execute correctly with 100% pass across hermetic unit tests.
result: pass

### 2. Mid-Run Recalculation & 1-Second Dwell Overrun
expected: Mid-run segment rate updates recalculate smoothly during Whisper generator consumption; downward revisions step down immediately while upward revisions are debounced; overruns dwell at 1s for 1.0s before transitioning to "Finishing…" with overrun: true.
result: pass

### 3. Calibration Persistence, Exclusion Gating & Cold Boot
expected: Worker finalization updates calibration.json cache strictly post-paste with 0o600 permissions; failed, fallback, cold, and outlier runs are filtered out of calibration; tmpfs .boot_session marker cleanly marks cold boot runs; MAD confidence score is computed on bounded residuals.
result: pass

### 4. CLI Status JSON Contract Extended Fields
expected: Running python voice.py --status --json outputs valid JSON adhering to extended status contract, exposing revision_count, last_revised_at, key_level, key_n, eta_source, eta_confidence, overrun, eta_remaining_s, and eta_epoch.
result: pass

### 5. CLI Reset Calibration and Epoch Marker
expected: Running python voice.py --reset-calibration deletes calibration.json, sets .calibration_reset epoch timestamp file, and outputs "Calibration reset to priors."
result: pass

### 6. Environment Variable Kill Switch (VOICE_ETA=off)
expected: Setting VOICE_ETA=off suppresses ETA calculations across all telemetry queries, returning None for all ETA fields in status and telemetry.
result: pass

### 7. Live Push-to-Talk Dictation with Visible ETA & Dual Timer
expected: |
  1. The status overlay / pill appears immediately upon entering transcription with a single integer countdown (e.g., "~2s", "1s") or "Finishing…" on overrun.
  2. During active parallel chunk recording, dual clocks X:XX | X:XX display recording time and transcribed audio duration.
  3. The transcribed text types directly into your focused window.
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0

## Deferred Follow-Ups

- phase_target: "09"
  topic: "VoicePill Dual Timer Colors & State UI Enhancements"
  ideas:
    - "Keep existing theme colors (Sage/Cyber Green default)"
    - "When recording stops: stop left clock (freeze at total recorded duration), continue right clock (transcribed duration catch-up) until finished, then transition to typing without squiggly wave art"
    - "Add distinct transcribing icon (e.g. neurology, sync, or hourglass) and typing icon (keyboard)"
    - "Explicit 'Typing...' label and lingering 'Cancelled' state on cancel"
  deferred_at: 2026-10-29

## Gaps

[none yet]
