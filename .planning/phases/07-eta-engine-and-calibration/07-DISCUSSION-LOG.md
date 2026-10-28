# Phase 7: ETA Engine & Calibration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-29
**Phase:** 07-eta-engine-and-calibration
**Areas discussed:** Calibration Storage & Cache, Mid-Run Revision Sensitivity, Cold Start & Early-Load Accounting, Key Hierarchy & Fallback Shrinkage

---

## Calibration Storage & Cache

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated atomic cache file | calibration.json in state dir, updated at end of each run | ✓ |
| On-the-fly streaming fit | Reparse metrics.jsonl on each lookup | |

**User's choice:** Dedicated atomic cache file
**Notes:** Ensures `--status` responds in under 100 ms without scanning unbounded ledger.

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent in get_metrics_dir() | ~/.local/state/voicemode/calibration.json; rebuilt from metrics.jsonl if missing | ✓ |
| Ephemeral in get_state_dir() | $XDG_RUNTIME_DIR; rebuilt after every reboot | |

**User's choice:** Persistent in get_metrics_dir()

| Option | Description | Selected |
|--------|-------------|----------|
| Remove + reset timestamp | Delete calibration.json, record timestamp to ignore earlier ledger rows | ✓ |
| Remove + truncate ledger | Delete calibration.json and archive/truncate metrics.jsonl | |

**User's choice:** Remove + reset timestamp
**Notes:** Preserves ledger history for reporting while reverting to prior-based estimates.

| Option | Description | Selected |
|--------|-------------|----------|
| After text insertion | Update during worker finalization post-paste | ✓ |
| Before inserting text | Update immediately on decode completion | |

**User's choice:** After text insertion
**Notes:** Ensures pasting is never delayed by calibration I/O.

| Option | Description | Selected |
|--------|-------------|----------|
| Comprehensive per-key stats | rate, finalize_s, load_s, sample_count, error MAD, confidence | ✓ |
| Minimal stats | Only fitted rate and sample count | |

**User's choice:** Comprehensive per-key stats

| Option | Description | Selected |
|--------|-------------|----------|
| Atomic tempfile + os.replace | 0600 permissions, matching existing atomic_write_json pattern | ✓ |
| fcntl.flock advisory lock | Direct write with lock | |

**User's choice:** Atomic tempfile + os.replace

| Option | Description | Selected |
|--------|-------------|----------|
| Incremental running accumulator | sum_decode_s, sum_audio_s, residuals window; rebuild from ledger only if missing | ✓ |
| Full scan on every run | Parse entire metrics.jsonl after each completion | |

**User's choice:** Incremental running accumulator

| Option | Description | Selected |
|--------|-------------|----------|
| Instant prior fallback + async rebuild | Fall back to priors for queries; worker rebuilds from ledger during finalization | ✓ |
| Synchronous rebuild | Parse metrics.jsonl inline immediately | |

**User's choice:** Instant prior fallback + async rebuild

---

## Mid-Run Revision Sensitivity

| Option | Description | Selected |
|--------|-------------|----------|
| ≥1.0s threshold | Revise upward only if jump ≥1.0s AND ≥2.0s since prior revision | ✓ |
| ≥0.2s sensitive threshold | Revise on any noticeable fractional increase after 2.0s debounce | |

**User's choice:** ≥1.0s threshold
**Notes:** Avoids jittery flickers on minor recalculations.

| Option | Description | Selected |
|--------|-------------|----------|
| Immediate step down | Step to lower integer immediately | ✓ |
| Smooth acceleration | Tick faster (2x) until aligned | |

**User's choice:** Immediate step down

| Option | Description | Selected |
|--------|-------------|----------|
| revision_count + last_revised_at | In status.json; total + max jump in ledger | ✓ |
| Boolean revised flag | Simple revised: true in status.json | |

**User's choice:** revision_count + last_revised_at

| Option | Description | Selected |
|--------|-------------|----------|
| Hold 1s for 1 second | Natural pacing: 2s → 1s → Finishing… | ✓ |
| Transition immediately | Switch to Finishing… as soon as countdown drops below 1s | |

**User's choice:** Hold 1s for 1 second

| Option | Description | Selected |
|--------|-------------|----------|
| Per segment | Recalculate on each Whisper generator yield | ✓ |
| Fixed timer | Recalculate on 500ms interval | |

**User's choice:** Per segment

| Option | Description | Selected |
|--------|-------------|----------|
| Calibrated + blend after 5s | Calibrated rate for remaining audio, blend with observed rate once ≥5s decoded | ✓ |
| Strict calibrated only | Use calibrated rate throughout without blending | |

**User's choice:** Calibrated + blend after 5s

| Option | Description | Selected |
|--------|-------------|----------|
| Persist ~ throughout | ~4s, ~3s, ~1s until Finishing… | ✓ |
| Drop after first revision | Remove ~ prefix once mid-run revision occurs | |

**User's choice:** Persist ~ throughout

| Option | Description | Selected |
|--------|-------------|----------|
| Stay on Finishing… | Until text insertion begins; overrun: true in status | ✓ |
| Switch to Still working… | After 5 seconds of overrun | |

**User's choice:** Stay on Finishing…

---

## Cold Start & Early-Load Accounting

| Option | Description | Selected |
|--------|-------------|----------|
| Dynamic remaining load | max(0, estimated_load_s - elapsed_record_s) | ✓ |
| Binary check | 0 if loaded, full load_s if not | |

**User's choice:** Dynamic remaining load

| Option | Description | Selected |
|--------|-------------|----------|
| Track separately, exclude cold | Cold/warm tracked independently; cold excluded from rate fitting | ✓ |
| Single overall median | No cold/warm distinction | |

**User's choice:** Track separately, exclude cold

| Option | Description | Selected |
|--------|-------------|----------|
| Boot-only | First run after system startup | ✓ |
| Inactivity threshold >15 min | Cold if no run for >15 minutes | |

**User's choice:** Boot-only

| Option | Description | Selected |
|--------|-------------|----------|
| Runtime dir marker | $XDG_RUNTIME_DIR/voice-stt/.boot_session (tmpfs clears on reboot) | ✓ |
| boot_id from /proc | Read /proc/sys/kernel/random/boot_id, compare with stored | |

**User's choice:** Runtime dir marker

| Option | Description | Selected |
|--------|-------------|----------|
| Prior for cold, calibrated for warm | Shipped prior load_s for cold; calibrated load_s for warm | ✓ |
| Always shipped prior | Use prior load time regardless of cold/warm | |

**User's choice:** Prior for cold, calibrated for warm

| Option | Description | Selected |
|--------|-------------|----------|
| Immediate ETA | Publish ETA instantly before model load completes | ✓ |
| Wait for model load | No ETA until model is loaded | |

**User's choice:** Immediate ETA

| Option | Description | Selected |
|--------|-------------|----------|
| Four values: prior, calibrated, mid-run, cold | Distinct diagnostic values | ✓ |
| Two values: prior, calibrated | Simplified | |

**User's choice:** Four values

---

## Key Hierarchy & Fallback Shrinkage

| Option | Description | Selected |
|--------|-------------|----------|
| 4-level hierarchy | L0 (8 fields) → L1 (6) → L2 (4) → L3 (prior) | ✓ |
| 3-level hierarchy | L0 → L1 (3 fields) → L2 (prior) | |

**User's choice:** 4-level hierarchy

| Option | Description | Selected |
|--------|-------------|----------|
| Minimum 3 samples | Matches ETA-02 requirement | ✓ |
| Minimum 5 samples | Higher confidence threshold | |

**User's choice:** Minimum 3 samples

| Option | Description | Selected |
|--------|-------------|----------|
| Weighted blend (shrinkage) | weight = min(1.0, n/10) — smooth trust ramp | ✓ |
| Hard cutoff | Use narrow or broader, no blending | |

**User's choice:** Weighted blend

| Option | Description | Selected |
|--------|-------------|----------|
| Ratio of sums | Σdecode / Σaudio via incremental accumulators; MAD for confidence only | ✓ |
| Median of per-run rates | Median-based robust fitting | |

**User's choice:** Ratio of sums
**Notes:** Conflict resolved — ETA-01 requires ratio of sums. MAD/median used only on prediction residuals for confidence scoring, not rate fitting.

| Option | Description | Selected |
|--------|-------------|----------|
| 1.0 - MAD/median_residual | Clamped [0, 1], on residuals window | ✓ |
| Fixed confidence tiers | 0.3/0.6/0.9 based on sample count | |

**User's choice:** 1.0 - MAD/median_residual

| Option | Description | Selected |
|--------|-------------|----------|
| Per-level accumulators in calibration.json | Each level's stats available for instant lookup | ✓ |
| Finest level only | Compute broader levels on demand | |

**User's choice:** Per-level accumulators

| Option | Description | Selected |
|--------|-------------|----------|
| Both status.json and ledger | Record resolved level, n, confidence in both | ✓ |
| Ledger only | Not in status.json | |

**User's choice:** Both

| Option | Description | Selected |
|--------|-------------|----------|
| Comprehensive exclusions | failures + fallbacks + outliers + cold + high-load + GPU→CPU + load > 3× | ✓ |
| Minimal: failures only | Only outcome ≠ success | |

**User's choice:** Comprehensive exclusions

---

## The Agent's Discretion

- Exact residuals window size within 20–30 range
- Shrinkage blend weight ramp shape (denominator tuning)
- Internal naming of estimator class/functions
- Test placement and mocking strategy
- Exact `--status --json` output fields beyond specified ETA fields

## Deferred Ideas

None — discussion stayed within phase scope.
