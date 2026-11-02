# Phase 10: Accuracy Loop, Portability & Hardening - Context

**Gathered:** 2026-11-02
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers system hardening, outlier detection, opt-in audio corpus capture, hardware portability diagnostics, and durability resilience for voicemode. Following the removal of all ETA, prediction, and calibration code (commit `965af70`), this phase aligns voicemode's accuracy and telemetry architecture around honest stage timings, Real-Time Factor (RTF) tracking, multi-chunk outlier attribution, and bulletproof degraded operation. It extends `voice --doctor` with rich telemetry health and hardware probing, introduces opt-in diagnostic corpus capture with strict FIFO quotas and zero network access, ensures dictation survives constrained environments (disk full, read-only dirs, unset runtime dirs, non-standard sample rates, 4 GB RAM), establishes a stratified latency evaluation protocol, and updates `README.md` and `docs/telemetry.md`. All Desktop Pop-up UI features are deferred to Phase 11.
</domain>

<decisions>
## Implementation Decisions

### Outlier Definition & Visualization (ACC-01)
- **D-01:** An STT run is classified as an outlier if Real-Time Factor (RTF) > 1.0 (decoding took longer than audio length) OR tail decode duration > 10.0 seconds. Configurable via environment variables `VOICEMODE_OUTLIER_RTF_THRESHOLD=1.0` and `VOICEMODE_OUTLIER_TAIL_S=10.0`. — **Reversibility:** reversible.
- **D-02:** Outliers are recorded directly in `metrics.jsonl` with explicit fields: `outlier: true` (boolean) and `outlier_reason: "rtf_exceeded" | "tail_decode"`. If not an outlier, `outlier: false` and `outlier_reason: null`. — **Reversibility:** costly — changes published JSONL schema.
- **D-03:** Outlier classification is orthogonal to run outcomes: `outlier: true` applies strictly to completed runs (`outcome: "success"` or `outcome: "partial_success"`). Watchdog timeouts and user aborts maintain their distinct `outcome: "timeout"` and `outcome: "cancelled"` states. — **Reversibility:** reversible.
- **D-04:** In the HTML report, outliers are surfaced via a dedicated "Outlier Runs" callout filter card, and styled in SVG charts as distinct hollow diamond/cross markers with Crimson stroke (`#f43f5e`) and hover tooltips explaining the outlier cause. — **Reversibility:** reversible.
- **D-05:** In the terminal summary and table views, outlier rows display a distinct Amber/Crimson `[OUTLIER]` tag/pill. CLI reporting supports `voice --report --outliers` to filter output specifically to outlier runs. — **Reversibility:** reversible.
- **D-06:** Outliers operate strictly under the focus-safe policy: no desktop notifications or audio alerts are emitted on outlier detection, preventing active window focus theft before or after `wtype` typing. — **Reversibility:** reversible.

### Opt-in Corpus Capture & Storage (ACC-01)
- **D-07:** Corpus capture is disabled by default (`VOICEMODE_CORPUS_CAPTURE=none`). It can be enabled via environment variable `VOICEMODE_CORPUS_CAPTURE=none|outliers|all` or CLI flag `--capture-corpus {outliers,all}`. When enabled without specifying mode, it defaults to capturing `outliers`. — **Reversibility:** reversible.
- **D-08:** Corpus files are saved to `$XDG_STATE_HOME/voice-stt/corpus/` (fallback `~/.local/state/voice-stt/corpus/`). Directory permissions are strictly enforced to `0700` and WAV files to `0600`. Zero network access or external syncing is permitted. — **Reversibility:** costly — standard local path contract.
- **D-09:** Captured audio format is an exact raw bit-for-bit copy of the 16 kHz mono 16-bit PCM WAV recorded by `Recorder` (no re-encoding overhead). File naming follows `{run_id}_{timestamp}_{reason}.wav`, and the relative path is recorded in `metrics.jsonl` as `corpus_file`. — **Reversibility:** reversible.
- **D-10:** Corpus writing occurs post-injection in `finalize_background_run()`, completely off the critical latency path so disk I/O never delays keystroke injection. — **Reversibility:** reversible.
- **D-11:** If the corpus directory cannot be created or permissions fail, voicemode fails safe: logs a warning, skips corpus saving, and allows text dictation and typing to proceed uninterrupted. — **Reversibility:** reversible.

### Corpus FIFO Eviction Mechanics (ACC-01)
- **D-12:** Corpus storage is strictly bounded by a FIFO quota: maximum 50 files OR 100 MB total directory size. Additionally, saving is aborted if available filesystem free space is < 1 GB. — **Reversibility:** reversible.
- **D-13:** Quota check and eviction run inline immediately before writing a new corpus file in `finalize_background_run()`, guaranteeing limits are never exceeded at any point in time. — **Reversibility:** reversible.
- **D-14:** Eviction deletes the oldest files first based on file modification timestamp (`mtime`). In-flight files are protected by writing to a temporary file (`.tmp_*.wav`) followed by atomic `os.replace()`, with a 60-second grace window protecting recently modified files. — **Reversibility:** reversible.
- **D-15:** Eviction events are logged quietly to `voice.log` (`"Pruned N corpus files (X.X MB reclaimed)"`) and aggregated as a lifetime count in `voice --doctor`. No desktop toast notifications are shown. — **Reversibility:** reversible.
- **D-16:** A built-in CLI command `voice --purge-corpus` permanently deletes all corpus audio files, reporting `Purged N corpus audio files (X.X MB reclaimed)`. The JSONL ledger remains append-only and immutable; reports gracefully display `[audio: pruned]` if the underlying WAV file has been removed. — **Reversibility:** reversible.

### Multi-Chunk Streaming & Outlier Attribution (ACC-01, ACC-04)
- **D-17:** Multi-chunk sessions track outliers using a hybrid model: the overall session has an aggregate `outlier` flag based on total perceived wait latency (`wait_s`) and total RTF, while per-chunk timing details (`rtf`, `decode_ms`, `outlier`, `retries`) are recorded in the `chunks` array in `metrics.jsonl`. — **Reversibility:** costly — ledger schema structure.
- **D-18:** When an outlier occurs in a multi-chunk session, opt-in corpus capture preserves the continuous session audio (`{run_id}_full.wav`) rather than isolated chunk snippets, retaining full acoustic cadence and context. — **Reversibility:** reversible.
- **D-19:** If an individual chunk fails during multi-chunk streaming, voicemode delivers resilient partial typing (types successfully decoded chunks), logs a warning, records `failed_chunks: [i]` in telemetry, and marks `outcome: "partial_success"`. — **Reversibility:** reversible.
- **D-20:** User wait latency (`wait_s`) is strictly defined as elapsed wall-clock time from `stop_requested` (hotkey release) until text typing completes. Background chunk decoding performed during active speech recording is treated as zero user wait latency. — **Reversibility:** reversible.
- **D-21:** Mid-session cancellation (`SUPER+ALT+M` or `SIGTERM`) discards partially decoded transcripts, plays the cancel audio cue, writes `outcome: "cancelled"` to telemetry with completed chunk metrics, and purges temporary files. Incremental progress in `status.json` updates monotonically as each chunk finishes to drive Quickshell dual timers. — **Reversibility:** reversible.

### Doctor Telemetry Diagnostics & Backend Probing (ACC-02, ACC-03, ACC-07)
- **D-22:** `voice --doctor` displays a dedicated telemetry diagnostics card: sample count `n`, median wait latency, p90 latency, mean RTF, outlier count/rate, drift percentage (recent 20 runs vs lifetime baseline), and last run timestamp. — **Reversibility:** reversible.
- **D-23:** Hardware backend probing checks CPU architecture, vector extensions (AVX2/AVX-512), and probes for discrete GPUs (CUDA via `ctranslate2.get_cuda_device_count()` and `nvidia-smi`, ROCm via `/dev/kfd` / `/dev/dri`) with a strict 1.0s timeout without instantiating Whisper models. — **Reversibility:** reversible.
- **D-24:** Default execution strictly enforces CPU int8 on all platforms (including Intel UHD 770 and AMD/NVIDIA systems). GPU hardware is detected and reported informatively in `--doctor`, but is NEVER auto-selected unless explicitly requested via `--device cuda`. — **Reversibility:** costly — safety and portability baseline.
- **D-25:** `voice --doctor` audits filesystem paths and permissions: state directory, runtime directory, `metrics.jsonl` readability/writeability, `status.json` contract freshness, corpus directory permissions (0700), and filesystem free space (> 1 GB). — **Reversibility:** reversible.
- **D-26:** Telemetry defects, corrupt ledger lines, or low disk space are reported as advisory WARNINGs (Yellow, exit code 0) in `--doctor`. Only fatal breaks to core STT operation (missing microphone, missing `wtype`, missing faster-whisper) return ERROR (Red, exit code 1). — **Reversibility:** reversible.
- **D-27:** `voice --doctor --json` returns structured nested keys `"telemetry"` and `"hardware"` containing all metrics and diagnostic checks, providing a clean contract for scripting and the Phase 11 desktop popup. — **Reversibility:** costly — published JSON contract.

### Degraded Fallback & Durability Policies (ACC-04)
- **D-28:** When `XDG_RUNTIME_DIR` is unset or non-standard (e.g. custom UID ≠ 1000, SSH session), voicemode falls back securely to `/tmp/voice-stt-$UID/` with POSIX permissions `0700`. — **Reversibility:** reversible.
- **D-29:** On read-only state directories or full disk (`ENOSPC` / `EROFS`), voicemode gracefully degrades: catches filesystem write exceptions, logs warnings to stderr/log, bypasses `metrics.jsonl`, `status.json`, and `report.html` writes, and ensures voice audio capture, Whisper transcription, and `wtype` keystroke typing succeed without interruption. — **Reversibility:** reversible.
- **D-30:** If writing temporary WAV chunks to disk fails due to full disk, audio buffers are maintained in-memory as numpy arrays and passed directly to Whisper's decode pipeline, eliminating disk dependency for core dictation. — **Reversibility:** reversible.
- **D-31:** When audio hardware requests or provides non-16kHz audio (e.g. 44.1 kHz, 48 kHz USB mics), `Recorder` transparently performs fast in-memory numpy interpolation to 16 kHz before chunking, ensuring model input compatibility without external dependencies. — **Reversibility:** reversible.
- **D-32:** To protect low-RAM systems (4 GB RAM constraint), Whisper CPU inference threads are clamped to `min(4, os.cpu_count())`, decoded chunk buffers are unlinked and dereferenced immediately, and `gc.collect()` is invoked upon run finalization to release resident memory. — **Reversibility:** reversible.

### Cold-Boot, First-Run Baseline & Performance Targets (ACC-04, ACC-05, ACC-06)
- **D-33:** On fresh installs or system reboots with 0 ledger runs, `voice --doctor` reports `Telemetry: ready (0 runs recorded). Establish performance baseline by recording with SUPER+SHIFT+M` (exit code 0). `voice --report` renders an empty-state onboarding card with keyboard shortcuts and ghost charts. — **Reversibility:** reversible.
- **D-34:** Initial system boot runs record `cold_load: true` in the ledger row (detected via `check_and_mark_boot_session()`), allowing reports and doctors to cleanly separate one-time model load overhead from warm steady-state latency. — **Reversibility:** reversible.
- **D-35:** The pre-rendered `report.html` onboarding file is created during initial setup or first doctor check so that clicking the Quickshell pill never encounters a missing file. — **Reversibility:** reversible.
- **D-36:** Latency evaluation protocol (ACC-06) is stratified across clip durations: Short (<5s), Medium (5–30s), Long (>30s). Benchmark target on Intel Alder Lake CPU int8: median RTF ≤ 0.35, outlier share ≤ 5% over 20 reference runs. TTS readiness (ACC-05) verifies `tts_reserved()` schema fields exist in the ledger with zero TTS values mixed into STT records. — **Reversibility:** reversible.

### Documentation & Verification Updates (ACC-07)
- **D-37:** Update `README.md` and `docs/telemetry.md` to comprehensively document:
  - Updated JSONL schema, fields, and privacy guarantees (zero text stored, local-only).
  - Outlier detection criteria (RTF > 1.0, tail > 10s) and `--outliers` CLI flag.
  - Opt-in corpus capture configuration (`VOICEMODE_CORPUS_CAPTURE`), retention policies, and `--purge-corpus`.
  - Durability and degraded operation (`/tmp/voice-stt-$UID/`, in-memory fallback on full disk).
  - Expanded `voice --doctor` diagnostics, hardware backend policies, and environment variables table.
  - Verification with automated test suite in `tests/test_durability.py`. — **Reversibility:** reversible.

### The Agent's Discretion
- Exact SVG coordinate scaling and tooltip layout for outlier markers on the latency scatter and RTF trend charts.
- Internal function naming in `voicemode_telemetry.py` for corpus pruning (`prune_corpus_if_needed`, `save_corpus_clip`).
- Specific test fixtures and mock structures for simulating `ENOSPC` and read-only directories in `tests/test_durability.py`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone & Phase Scope
- `.planning/ROADMAP.md` — Phase 10 goals, requirements (ACC-01 through ACC-07), and success criteria
- `.planning/REQUIREMENTS.md` — ACC-01 through ACC-07 specification details
- `.planning/PROJECT.md` — v1.1 Latency Prediction & Telemetry milestone goals and hardware context

### Prior Phase Context
- `.planning/phases/09-quickshell-status-pill-integration/09-CONTEXT.md` — Progress timers, Material symbols, status contract, click-through report opener
- `.planning/phases/08-accuracy-report-click-through/08-CONTEXT.md` — Latency report generation, SVG charts, CSV/JSON rendering, atomic report generation
- `.planning/phases/06-foundations-ledger-status-contract/06-CONTEXT.md` — Telemetry ledger v1 schema, privacy allowlist, atomic JSON writes, boot session tracking
- `.planning/quick/261101-2lt-remove-all-prediction-and-eta-code/261101-2lt-PLAN.md` — Removal of prediction/ETA/calibration code and transition to pure stage latency tracking

### Codebase Implementations
- `voice.py` — Background worker execution, recorder, model loading, audio chunking, CLI dispatch, and `run_doctor()`
- `voicemode_telemetry.py` — Schema validation (`SCHEMA_V1_KEYS`), `build_record()`, `read_ledger_rows()`, `ledger_health()`, status publishing
- `voicemode_report.py` — Latency report generator (`render_html_report`, `render_terminal_summary`, `render_csv`, `render_json`)
- `docs/telemetry.md` — Published telemetry and schema documentation
- `README.md` — Main repository documentation

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `voicemode_telemetry.py`: Contains `atomic_write_json()`, `atomic_write_text()`, `ledger_health()`, `check_and_mark_boot_session()`, and `tts_reserved()`. Ready for corpus directory management and health inspection.
- `voicemode_report.py`: Contains `compute_report_metrics()`, `render_latency_scatter_svg()`, `render_rtf_trend_svg()`, `render_stage_bars_svg()`, and `render_empty_state_card()`. Ready for outlier marker styling and `--outliers` filtering.
- `voice.py`: Contains `Recorder`, `load_model()`, `run_background_recording()`, `finalize_background_run()`, and `run_doctor()`. Ready for hardware probing, in-memory chunk fallback, and corpus post-save integration.

### Established Patterns
- Atomic file operations: write to `.tmp_*` file in same filesystem followed by `os.replace()`.
- Resilient non-fatal telemetry: exceptions during metrics recording or report pre-rendering are caught and logged without aborting core speech typing.
- Privacy baseline: no transcript text or user audio is stored by default; all metrics are numeric durations and character counts.

### Integration Points
- `get_state_dir()` / `get_metrics_dir()`: Path resolution handles for `$XDG_RUNTIME_DIR` with `/tmp/voice-stt-$UID/` fallback.
- `finalize_background_run()` in `voice.py`: Post-injection execution point where corpus capture and report pre-rendering occur outside the timed path.
- `run_doctor()` in `voice.py`: Diagnostic check suite where telemetry health and backend hardware inspection integrate.

</code_context>

<specifics>
## Specific Ideas
- Outlier threshold: `RTF > 1.0` or `tail_decode_s > 10.0s`.
- Crimson accent color for outliers: `#f43f5e` on dark canvas.
- Corpus directory: `~/.local/state/voice-stt/corpus/` (0700 permissions).
- Resampling fallback: transparent numpy linear interpolation to 16 kHz in `Recorder`.
- Durability test module: `tests/test_durability.py`.
- Documentation updates: update both `README.md` and `docs/telemetry.md`.
</specifics>

<deferred>
## Deferred Ideas

### Phase 11: Voice Desktop Pop-up UI
- Desktop interactive Quickshell overlay popup window for voice recording history, settings, and telemetry.
- User explicitly confirmed this belongs in Phase 11, which will consume the telemetry and doctor data produced in Phase 10.

### Reviewed Todos (not folded)
- None — all pending tasks align with Phase 10 scope.

</deferred>

---

*Phase: 10-Accuracy Loop, Portability & Hardening*
*Context gathered: 2026-11-02*
