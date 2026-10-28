# Phase 7: ETA Engine & Calibration - Context

**Gathered:** 2026-10-29
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase turns measured telemetry runs into a calibrated, honest, single-number transcription ETA. It delivers: a prediction engine that appears within 100 ms of entering transcribing (using shipped priors on fresh installs), counts down smoothly, corrects mid-run after each Whisper segment, clamps and transitions to `Finishing…` on overrun, and learns from ledger history via a persistent calibration cache. It also adds CLI flags (`--reset-calibration`, `--status --json` ETA fields, `VOICE_ETA=off`) and cold-start detection. No new dependencies, no daemon, no UI changes (those are Phase 9).
</domain>

<decisions>
## Implementation Decisions

### Calibration storage & cache
- **D7-01:** Calibrated parameters are stored in a dedicated atomic cache file `calibration.json`, updated by the worker at the end of each run. — **Reversibility:** reversible — cache can be deleted and rebuilt from ledger at any time.
- **D7-02:** `calibration.json` lives persistently at `~/.local/state/voicemode/calibration.json` (via `get_metrics_dir()`), surviving reboots. Automatically rebuilt from `metrics.jsonl` if missing or invalid. — **Reversibility:** costly — changing the path after deployment means orphaning existing calibration data.
- **D7-03:** `--reset-calibration` removes `calibration.json` and records a reset timestamp so earlier ledger rows are ignored during rebuilds, reverting to prior-based estimates without deleting ledger history.
- **D7-04:** `calibration.json` is updated during worker finalization **after** text insertion is done, ensuring pasting is never delayed by calibration I/O.
- **D7-05:** Per-key stats are comprehensive: rate (ratio of sums), finalize_s, load_s, sample_count, residuals window (last 20–30 prediction errors), and confidence score.
- **D7-06:** All writes use atomic `tempfile + os.replace` with `0o600` permissions, matching the existing `atomic_write_json()` pattern. Readers never see torn JSON.
- **D7-07:** Calibration uses incremental running accumulators (`sum_decode_s`, `sum_audio_s`, sample counts) for O(1) updates per run. Full rebuild from `metrics.jsonl` only if the file is missing.
- **D7-08:** On missing or corrupted `calibration.json` during a status query, instantly fall back to shipped priors (zero latency). The worker rebuilds from `metrics.jsonl` during its next finalization.

### Mid-run revision sensitivity
- **D7-09:** Upward revisions require both a ≥1.0 s jump AND ≥2.0 s elapsed since the prior revision — suppresses jittery flickers.
- **D7-10:** Downward revisions step immediately to the lower integer estimate — strictly monotone non-increasing, truthfully reflects fast progress.
- **D7-11:** `revision_count` and `last_revised_at` are exposed in `status.json`; total revisions and max upward jump are recorded in the ledger summary.
- **D7-12:** Countdown dwells at `1s` for 1 full second, then transitions to `Finishing…` — natural pacing: `2s → 1s → Finishing…`.
- **D7-13:** Remaining ETA is recalculated on each segment yielded by the Whisper transcription generator (immediate response to real decoding progress).
- **D7-14:** Mid-run rate blends calibrated rate with this run's observed rate once ≥5 s of audio has decoded: `remaining = blended_rate × (total_audio - decoded_audio) + insert_s`.
- **D7-15:** The `~` prefix persists across the entire countdown for uncalibrated runs (e.g. `~4s`, `~3s`, `~1s`) until `Finishing…` — uncalibrated confidence is honest throughout.
- **D7-16:** Extended overrun stays on `Finishing…` continuously until text insertion begins; `status.json` marks `overrun: true`. No label escalation.

### Cold start & early-load accounting
- **D7-17:** Remaining model load in initial ETA: `remaining_load = max(0.0, estimated_load_s - elapsed_record_s)` — dynamic subtraction accounting for parallel loading during recording.
- **D7-18:** Cold and warm load times are tracked separately; cold run decodes are excluded from fitting the steady-state transcription rate. — **Reversibility:** costly — changing the cold/warm boundary retroactively invalidates accumulated cold-run exclusion history.
- **D7-19:** Cold run = first run after system boot only (not inactivity-based).
- **D7-20:** Boot detection uses a `$XDG_RUNTIME_DIR/voice-stt/.boot_session` marker file — tmpfs clears automatically on every reboot; zero dependencies, instant check.
- **D7-21:** Cold runs use shipped prior load time; warm runs use calibrated `load_s` from `calibration.json`.
- **D7-22:** ETA is published in `status.json` immediately (<100 ms) when entering transcribing state — before model load completes — using priors or calibration. Revised on first segment yield.
- **D7-23:** `eta_source` has 4 distinct values: `prior` (fresh install, no calibration data), `calibrated` (fitted from ledger history), `mid-run` (blended with this run's observed rate), `cold` (first-after-boot, using shipped prior with inflated load estimate). `cold` and `prior` use the same prior values but carry different diagnostic meaning.

### Key hierarchy & fallback shrinkage
- **D7-24:** 4-level hierarchy: L0 (all 8 fields: model/device/compute_type/backend/beam_size/vad_filter/language/chunk_s) → L1 (drop chunk_s + vad_filter) → L2 (model/device/compute_type/backend only) → L3 (shipped prior). — **Reversibility:** costly — changing the hierarchy structure invalidates all per-level accumulators in calibration.json.
- **D7-25:** Minimum 3 samples per level before trusting it (matches ETA-02); below 3, fall to the next broader level.
- **D7-26:** Shrinkage blend: `weight = min(1.0, n_exact / 10.0)` → `result = weight × narrow_rate + (1 - weight) × broader_rate` — smoothly trusts the narrow key as samples accumulate.
- **D7-27:** Rate statistic is ratio of sums (`Σdecode_s / Σaudio_s`) per ETA-01, **not** median of per-run rates. Outlier resistance is achieved via exclusion-before-accumulation rather than robust statistics on the rate itself. — **Reversibility:** costly — changing the rate statistic retroactively requires re-scanning the full ledger to rebuild accumulators.
- **D7-28:** Confidence = `1.0 - MAD/median_residual` clamped [0.0, 1.0], computed on a residuals window (last 20–30 prediction errors). MAD is used for confidence scoring only, not for rate fitting.
- **D7-29:** Per-level accumulators are stored in `calibration.json` so each level's stats are always available for instant lookup and shrinkage blending.
- **D7-30:** The resolved key level (L0/L1/L2/L3), sample count, and confidence are recorded in both `status.json` and the ledger row.
- **D7-31:** Exclusions from fitting: `outcome ≠ success`, GPU→CPU fallback, cold runs, `load_ms > 3× calibrated load` (contention proxy), outliers (rate outside [0.01, 10.0]).

### Resolved conflicts
- **D7-C1:** Ratio of sums wins over median of per-run rates for fitting (ETA-01 compliance). MAD/median used only on prediction residuals for confidence, not for rate fitting.
- **D7-C2:** `eta_source: cold` is distinct from `eta_source: prior` — cold means "known cold boot with inflated load"; prior means "no calibration data at all (fresh install)".

### The agent's discretion
- Exact residuals window size within 20–30 range.
- Shrinkage blend weight ramp shape (linear via `n/10` is specified, but the agent may adjust the denominator if testing reveals a better ramp).
- Internal naming of estimator class/functions.
- Test placement and mocking strategy.
- Exact fields in the `--status --json` output beyond the specified ETA fields.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone
- `.planning/REQUIREMENTS.md` — ETA-01 through ETA-09 requirements (9)
- `.planning/ROADMAP.md` — Phase 7 goal and success criteria
- `.planning/research/SUMMARY.md` — Phase 7 rationale, pure predictor design, testability with synthetic ledgers
- `.planning/research/PITFALLS.md` — Predictor structure, cold start, contention, mean-of-ratios trap, overrun UX

### Prior phase context
- `.planning/phases/06-foundations-ledger-status-contract/06-CONTEXT.md` — Ledger schema, status contract, calibration_key design, recording heartbeat, early model load, incremental transcription decisions

### Codebase
- `voice.py` — Worker lifecycle, `run_background_recording()`, `transcribe()`, signal handling, CLI dispatch
- `voicemode_telemetry.py` — `calibration_key()`, `prior_eta_seconds()`, `build_status()`, `publish_status()`, `read_status()`, `append_ledger_row()`, `atomic_write_json()`, existing Phase 7 stubs (`get_calibration_path()`, `load_calibration()`, `save_calibration()`, `fit_calibration_from_ledger()`, `calibrated_eta_seconds()`)
- `.planning/codebase/ARCHITECTURE.md` — IPC/state machine, worker coordination
- `.planning/codebase/TESTING.md` — Test patterns, mocking strategy

### Architecture visualization
- `.planning/phases/07-eta-engine-and-calibration/07-architecture.html` — Interactive HTML with full architecture diagrams, formula breakdown, fallback chain, state machine, and decision register
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `calibration_key(backend, config)` in `voicemode_telemetry.py` — already computes the 8-field pipe-delimited key; Phase 7 needs to add L1/L2 prefix extraction
- `prior_eta_seconds(audio_s, model)` — existing prior formula; Phase 7 replaces this with the full estimator but keeps it as L3 fallback
- `atomic_write_json(path, obj, mode)` — atomic tempfile + os.replace pattern; reuse directly for calibration.json writes
- `build_status(...)` — already accepts `eta_epoch`, `eta_remaining_s`, `eta_confidence`, `eta_source`, `overrun`, `report_path` fields; Phase 7 populates these
- Existing stubs: `get_calibration_path()`, `load_calibration()`, `save_calibration()`, `fit_calibration_from_ledger()`, `calibrated_eta_seconds()` — partial Phase 7 scaffolding already in place

### Established Patterns
- Detached worker processes with PID tracking in `$XDG_RUNTIME_DIR/voice-stt/`
- File-based IPC: `status.json` (advisory) + PID file (authority)
- All state files use `0o700` directories and `0o600` files
- `PRIOR_RTF` dict provides per-model-family RTF constants
- `STATUS_ALLOWED_FIELDS` whitelist controls what enters `status.json`

### Integration Points
- `run_background_recording()` in `voice.py` — instrument mid-run ETA revision loop inside the transcription generator consumption
- `transcribe()` in `voice.py` — segment yield point where ETA recalculates
- `toggle_background_recording()` — cold detection check at worker spawn
- `--status` CLI handler — add `--json` ETA fields
- `main()` CLI dispatch — add `--reset-calibration` command
- `STATUS_ALLOWED_FIELDS` — add `revision_count`, `last_revised_at`, `key_level`, `key_n`
</code_context>

<specifics>
## Specific Ideas

- Use the existing `PRIOR_RTF` dict as the L3 (shipped prior) fallback — no new constants needed for rate.
- The incremental accumulator stores raw sums, not derived rates — the rate is always computed on read as `sum_decode_s / sum_audio_s`.
- `.boot_session` marker is a zero-byte file created on first run; tmpfs lifetime handles cleanup.
- The `~` prefix is a display concern only — `status.json` carries `eta_source` and `eta_confidence` as structured data; the consumer (Quickshell in Phase 9) decides how to render the prefix.
- Mid-run blending formula: `blended_rate = (1 - α) × calibrated_rate + α × observed_rate` where `α = min(1.0, observed_audio_s / 30.0)` ramps smoothly from 0 to 1 over 30 s of observed audio (agent may tune; 5 s is the minimum before blending starts at all).
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---
*Phase: 07-ETA Engine & Calibration*
*Context gathered: 2026-10-29*
