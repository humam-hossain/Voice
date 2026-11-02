# Phase 10: Accuracy Loop, Portability & Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-02
**Phase:** 10-accuracy-loop-portability-hardening
**Areas discussed:** Outlier Definition & Visualization, Opt-in Corpus Capture, Doctor Telemetry & Backend Probing, Degraded Fallback & Durability Policies, Multi-Chunk Outlier Attribution, Corpus FIFO Eviction Mechanics, Cold-Boot & Zero-Run Baseline

---

## Outlier Definition & Visualization

| Option | Description | Selected |
|--------|-------------|----------|
| Real-Time Factor (RTF) > 1.0 or tail decode > 10s | Decodes taking longer than speech duration or >10s tail | ✓ |
| Statistical anomaly | RTF or wait latency > 2× running median | |
| Whisper internal fallback only | Only flag if temperature fallback or retry triggered | |
| You decide | Combine RTF > 1.0 and decode retry flags | |

**User's choice:** Real-Time Factor (RTF) > 1.0 or tail decode > 10s
**Notes:** Intuitive and model-independent.

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated "Outlier Runs" filter/callout in HTML + Amber/Crimson "OUTLIER" pill in terminal | Highlight in both HTML dashboard and terminal output | ✓ |
| Row highlighting only | Color rows amber/red without dedicated section | |
| Separate CLI flag only | Only show when `--outliers` is passed | |
| You decide | Prominent visual badge in both HTML and terminal | |

**User's choice:** Dedicated "Outlier Runs" filter/callout in HTML + distinct Amber/Crimson "OUTLIER" pill in terminal and table rows
**Notes:** Provides instant visibility into anomalous runs.

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit ledger fields (`outlier: true`, `outlier_reason: ...`) | Fast indexing, immutable run history | ✓ |
| Dynamic computation at report time only | Keep schema minimal | |
| You decide | Explicit ledger fields for zero-overhead reporting | |

**User's choice:** Explicit ledger fields (`outlier: true`, `outlier_reason: "rtf_exceeded" | "tail_decode"`)
**Notes:** Enables instant filtering without re-evaluating calculations.

| Option | Description | Selected |
|--------|-------------|----------|
| Silent (no toast notification) | Preserves focus-safe policy so Wayland typing and active focus are never interrupted | ✓ |
| Subtle post-injection notification | Low-urgency toast if decode exceeded 15s | |
| You decide | Follow focus-safe rule (silent during routine use) | |

**User's choice:** Silent (no toast notification)
**Notes:** Adheres strictly to the Hyprland focus-safe rule.

| Option | Description | Selected |
|--------|-------------|----------|
| Add `--outliers` flag to `voice --report` | Filter terminal/CSV/HTML output to outlier runs | ✓ |
| Inline only | Tag in existing `--report` without flag | |
| You decide | Provide `--outliers` convenience flag | |

**User's choice:** Add `--outliers` flag to `voice --report`
**Notes:** Default shows all runs with outliers highlighted; `--outliers` isolates them.

| Option | Description | Selected |
|--------|-------------|----------|
| Distinct marker shape and color | Hollow diamond/cross with Crimson stroke (`#f43f5e`) and SVG hover tooltip | ✓ |
| Color shift only | Circular dots with Crimson fill | |
| You decide | Hollow diamond with tooltip | |

**User's choice:** Distinct marker shape and color — hollow diamond/cross with Crimson stroke (`#f43f5e`) and SVG hover tooltip explaining outlier cause
**Notes:** High-contrast visibility on dark canvas.

| Option | Description | Selected |
|--------|-------------|----------|
| Keep separate | `outlier: true` applies strictly to completed runs with high latency; timeouts and cancellations keep distinct outcomes | ✓ |
| Unified outlier umbrella | Flag timeouts and slow runs together | |
| You decide | Keep separate so error statistics remain clean | |

**User's choice:** Keep separate — `outlier: true` applies strictly to completed runs (`outcome: "success"`); timeouts and cancellations keep their existing distinct outcomes
**Notes:** Prevents polluting latency benchmarks with uncompleted runs.

| Option | Description | Selected |
|--------|-------------|----------|
| Environment variable overrides | `VOICEMODE_OUTLIER_RTF_THRESHOLD=1.0`, `VOICEMODE_OUTLIER_TAIL_S=10.0` with baked-in defaults | ✓ |
| Hardcoded constants | Keep configuration surface minimal | |
| You decide | Support env vars with standard defaults | |

**User's choice:** Environment variable overrides (`VOICEMODE_OUTLIER_RTF_THRESHOLD=1.0`, `VOICEMODE_OUTLIER_TAIL_S=10.0`) with baked-in defaults
**Notes:** Allows user tuning on slower or faster hardware.

---

## Opt-in Corpus Capture

| Option | Description | Selected |
|--------|-------------|----------|
| `$XDG_STATE_HOME/voice-stt/corpus/` (fallback `~/.local/state/voice-stt/corpus/`) | Standard persistent XDG state directory | ✓ |
| `$XDG_DATA_HOME/voice-stt/corpus/` | XDG data directory | |
| Inside `$XDG_RUNTIME_DIR/voice-stt/corpus/` | Ephemeral, purged on reboot | |
| You decide | XDG state directory | |

**User's choice:** `$XDG_STATE_HOME/voice-stt/corpus/` (fallback `~/.local/state/voice-stt/corpus/`)
**Notes:** Proper location for persistent local diagnostic recordings.

| Option | Description | Selected |
|--------|-------------|----------|
| Multi-mode env var `VOICEMODE_CORPUS_CAPTURE=none|outliers|all` with `--capture-corpus {outliers,all}` flag | Default `none`, defaults to `outliers` when enabled | ✓ |
| Simple boolean `VOICEMODE_CAPTURE_OUTLIERS=1` | Strictly captures outliers | |
| You decide | Multi-mode with `outliers` default | |

**User's choice:** Multi-mode env var `VOICEMODE_CORPUS_CAPTURE=none|outliers|all` (default `none`) with `--capture-corpus {outliers,all}` CLI flag
**Notes:** Off by default; flexible diagnostic capture when enabled.

| Option | Description | Selected |
|--------|-------------|----------|
| FIFO cap of 50 files / 100 MB total + minimum 1 GB free disk space safeguard | Aborts save if available disk < 1 GB | ✓ |
| Strict small cap: max 10 files / 25 MB total + 500 MB free check | Smaller storage allocation | |
| Time-based TTL | Delete recordings older than 7 days | |
| You decide | 50 files / 100 MB FIFO with 1 GB safeguard | |

**User's choice:** FIFO cap of 50 files / 100 MB total + minimum 1 GB free disk space safeguard (aborts save if available disk < 1 GB)
**Notes:** Strictly prevents runaway disk consumption.

| Option | Description | Selected |
|--------|-------------|----------|
| Strict POSIX permissions (0700 dir, 0600 files), zero network, and `voice --purge-corpus` command | Secure local-only storage with purge utility | ✓ |
| Standard permissions (0755 / 0644) with manual `rm -rf` | Standard permissions | |
| You decide | Strict permissions and dedicated purge flag | |

**User's choice:** Strict POSIX permissions (`0700` directory, `0600` WAV files), zero network access, and built-in `voice --purge-corpus` purge command
**Notes:** Maximum user privacy protection.

| Option | Description | Selected |
|--------|-------------|----------|
| Structured filename `{run_id}_{timestamp}_{reason}.wav` and record `corpus_file` in ledger row | Exact traceability | ✓ |
| Timestamp only (`corpus_{timestamp}.wav`) | No reference in `metrics.jsonl` | |
| You decide | Include run ID and log path in ledger row | |

**User's choice:** Structured filename `{run_id}_{timestamp}_{reason}.wav` and record `corpus_file` relative path in the ledger row for exact traceability
**Notes:** Clean linkage between telemetry metrics and audio clips.

| Option | Description | Selected |
|--------|-------------|----------|
| Post-injection in `finalize_background_run()` | Completely off critical latency path; never delays text typing | ✓ |
| Immediately upon transcribing completion | Synchronous save before injection | |
| You decide | Asynchronous post-injection outside timed path | |

**User's choice:** Post-injection in `finalize_background_run()` — completely off the critical latency path so file I/O never delays text typing
**Notes:** Ensures user keystroke injection is never delayed by disk writes.

| Option | Description | Selected |
|--------|-------------|----------|
| Direct copy of 16kHz mono 16-bit PCM WAV | Zero CPU/encoding overhead, bit-exact for replay | ✓ |
| Re-encode to FLAC | Saves 50% space but costs encoding CPU | |
| You decide | Exact raw WAV copy | |

**User's choice:** Direct copy of 16kHz mono 16-bit PCM WAV (already written by recorder) — zero CPU/encoding overhead, perfectly bit-exact for local replay
**Notes:** Eliminates CPU spikes and guarantees replay fidelity.

| Option | Description | Selected |
|--------|-------------|----------|
| Report footer panel shows corpus storage metrics + run table shows `[audio: clip.wav]` badge | Visible storage metrics and download/inspect badge | ✓ |
| Only surface in `--doctor` diagnostics | Keep report clean | |
| You decide | Surface stats in both report footer and `--doctor` | |

**User's choice:** Report footer panel shows corpus storage metrics (file count, total MB, purge command) + run table shows `[audio: clip.wav]` badge for captured runs
**Notes:** Complete visibility into retained debugging audio.

---

## Doctor Telemetry & Backend Probing

| Option | Description | Selected |
|--------|-------------|----------|
| Sample count `n`, median wait latency, p90 latency, mean RTF, outlier count/rate, last run timestamp | Aligns with post-ETA telemetry schema | ✓ |
| Full histogram and stage averages | Verbose stage details | |
| Minimal: run count and ledger size only | Minimal summary | |
| You decide | Clean 5-line summary card | |

**User's choice:** Sample count `n`, median wait latency, p90 latency, mean RTF, outlier count/rate, and last run timestamp — aligns with post-ETA telemetry schema
**Notes:** Concise, actionable health overview.

| Option | Description | Selected |
|--------|-------------|----------|
| Lightweight non-blocking probe (check `/dev/dri`, `nvidia-smi`, `ctranslate2.get_cuda_device_count()` with 1.0s timeout) without loading models | Safe probe; verifies CPU int8, notes GPU without auto-switching | ✓ |
| Heavy model benchmark | Load tiny model to measure compute speed | |
| Static check only | Check CPU arch and vector flags only | |
| You decide | Lightweight non-blocking probe | |

**User's choice:** Lightweight non-blocking probe (check `/dev/dri`, `nvidia-smi`, `ctranslate2.get_cuda_device_count()` with 1.0s timeout) without loading Whisper weights — verifies CPU int8, notes CUDA if present but keeps Intel/AMD on stable CPU int8
**Notes:** Fast doctor execution (<200ms) with zero heavy model overhead.

| Option | Description | Selected |
|--------|-------------|----------|
| Full filesystem audit: state dir, runtime dir, `metrics.jsonl`, `status.json`, corpus dir, partition free space (>1 GB) | Comprehensive path and permission health | ✓ |
| Basic file check: verify existence of ledger and status only | Simple existence check | |
| You decide | Comprehensive audit | |

**User's choice:** Full filesystem audit: state dir, runtime dir, `metrics.jsonl` (size, rows, writable), `status.json` validity, corpus dir (0700 permissions), and partition free space (>1 GB)
**Notes:** Diagnoses potential permission or storage degradation upfront.

| Option | Description | Selected |
|--------|-------------|----------|
| Structured nested keys `telemetry` and `hardware` in `voice --doctor --json` | Modular schema extensible for Phase 11 popup | ✓ |
| Flat root-level keys | Flat dictionary | |
| You decide | Structured nested keys | |

**User's choice:** Structured nested keys `telemetry` and `hardware` in `voice --doctor --json` — keeps machine-readable schema modular and extensible for Phase 11 popup
**Notes:** Directly consumed by Phase 11 desktop popup and scripts.

| Option | Description | Selected |
|--------|-------------|----------|
| Safe default: CPU int8 remains default regardless of GPU; GPU noted in diagnostics but never auto-selected without `--device cuda` | Stable, predictable execution | ✓ |
| Auto-select CUDA if detected | Switch to GPU automatically | |
| You decide | Enforce CPU int8 default; GPU informational only | |

**User's choice:** Safe default: CPU int8 remains the default backend regardless of detected GPUs; CUDA/ROCm is noted in doctor diagnostics but never auto-selected unless explicitly passed via `--device cuda`
**Notes:** Prevents driver crashes and preserves verified CPU stability.

| Option | Description | Selected |
|--------|-------------|----------|
| Advisory WARNING (Yellow, exit 0) for telemetry/disk issues | Reserve ERROR (exit 1) for broken audio/typing binaries | ✓ |
| Strict ERROR (Red, exit 1) | Fail on any warning | |
| You decide | Warnings for non-critical telemetry | |

**User's choice:** Advisory WARNING (Yellow, exit 0) — telemetry defects or low disk space warn the user without failing doctor status, reserving ERROR (exit 1) for broken audio/typing binaries
**Notes:** Distinguishes core service failure from telemetry advisories.

| Option | Description | Selected |
|--------|-------------|----------|
| Rolling drift metric: compare recent 20 runs median RTF against overall lifetime median (`Drift: ±X%`) | Detects system throttling or slowdown | ✓ |
| Linear regression slope across entire history | Single slope coefficient | |
| Visual only | Trend line on SVG chart only | |
| You decide | Rolling 20-run median comparison | |

**User's choice:** Rolling drift metric: compare recent 20 runs median RTF against overall lifetime median (`Drift: ±X%`) in report and doctor, showing if system is slowing down
**Notes:** Quantifiable metric for performance degradation.

| Option | Description | Selected |
|--------|-------------|----------|
| Schema validation: verify `tts_reserved()` schema contract is intact and assert STT runs contain zero mixed TTS fields | Verifies TTS telemetry readiness | ✓ |
| Omit from doctor check | Keep STT-focused only | |
| You decide | Subtle sub-check in telemetry diagnostics | |

**User's choice:** Schema validation: verify `tts_reserved()` schema contract is intact and assert STT runs contain zero mixed TTS fields
**Notes:** Fulfills requirement ACC-05.

---

## Degraded Fallback & Durability Policies

| Option | Description | Selected |
|--------|-------------|----------|
| `/tmp/voice-stt-$UID/` (with strict 0700 permissions) | Standard POSIX fallback when `XDG_RUNTIME_DIR` is unset | ✓ |
| `~/.cache/voice-stt/` | User cache directory | |
| Fail immediately with error | Abort execution | |
| You decide | Secure `/tmp/voice-stt-$UID/` | |

**User's choice:** `/tmp/voice-stt-$UID/` (with strict 0700 permissions) — standard POSIX secure temporary fallback path if `XDG_RUNTIME_DIR` is unset or UID ≠ 1000
**Notes:** Ensures portability across server, container, and non-systemd sessions.

| Option | Description | Selected |
|--------|-------------|----------|
| Resilient graceful degradation: catch `OSError` (`ENOSPC`, `EROFS`), log warning, skip ledger/status writes, ensure dictation & typing succeed | Dictation never crashes due to metrics failure | ✓ |
| Halt and notify: abort run with urgent notification | Fail closed on full disk | |
| You decide | Resilient degradation | |

**User's choice:** Resilient graceful degradation: catch `OSError` (`ENOSPC`, `EROFS`), log warning to stderr/log, skip ledger/status/report writes, and ensure speech dictation & typing succeed uninterrupted
**Notes:** Core typing capability must never fail because disk is full.

| Option | Description | Selected |
|--------|-------------|----------|
| Request 16 kHz; if hardware enforces 44.1/48 kHz, resample via fast numpy interpolation in `Recorder` | Hardware compatibility without external deps | ✓ |
| Hardware-only: fail if sounddevice cannot deliver 16 kHz | Fail on incompatible rate | |
| You decide | Automatic in-memory numpy resampling | |

**User's choice:** Request 16 kHz from sounddevice; if hardware enforces native rate (e.g. 44.1 kHz, 48 kHz), transparently resample in `Recorder` using fast numpy interpolation to 16 kHz before chunking
**Notes:** Full compatibility with studio and USB microphones.

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated `tests/test_durability.py` covering UID≠1000, unset XDG, read-only dirs, ENOSPC, 44.1/48 kHz resampling, and cold boot | Clean isolation for stress/resilience testing | ✓ |
| Split tests across existing files | Fragmented test coverage | |
| You decide | Dedicated durability test suite | |

**User's choice:** Dedicated `tests/test_durability.py` covering UID≠1000, unset XDG, read-only dirs, ENOSPC, 44.1/48 kHz resampling, and cold boot — clean isolation for stress/resilience testing
**Notes:** Directly validates requirement ACC-04.

| Option | Description | Selected |
|--------|-------------|----------|
| Pure in-memory audio buffers: if writing WAV chunks fails, keep audio in-memory as numpy arrays and decode directly | Zero disk reliance for audio processing | ✓ |
| Fallback to `/tmp` directory | Disk-based fallback | |
| You decide | In-memory audio buffers on disk write failure | |

**User's choice:** Pure in-memory audio buffers: if writing temporary WAV chunks to disk fails, keep audio in-memory as numpy arrays and decode directly from memory — zero disk reliance for audio processing
**Notes:** Speech transcription continues even on 100% full partition.

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit memory hygiene: clamp CPU threads to `min(4, os.cpu_count())`, clear decoded chunk buffers immediately, and run `gc.collect()` after typing | Prevents OOM under 4 GB RAM | ✓ |
| Rely on OS virtual memory without manual intervention | Standard garbage collection | |
| You decide | Explicit memory management | |

**User's choice:** Explicit memory hygiene: clamp CPU threads to `min(4, os.cpu_count())`, clear decoded chunk buffers immediately, and run `gc.collect()` after typing completes to release RSS
**Notes:** Guarantees stability on 4 GB RAM machines.

| Option | Description | Selected |
|--------|-------------|----------|
| Stratified protocol: short (<5s), medium (5–30s), long (>30s); metrics: median wait latency, p90 latency, mean RTF (target ≤0.35 on Intel CPU int8), outlier share ≤5% over 20 runs | Structured evaluation benchmark | ✓ |
| Single aggregated target (RTF ≤ 0.40) | Unstratified benchmark | |
| You decide | Stratified protocol | |

**User's choice:** Stratified protocol: short (<5s), medium (5–30s), long (>30s); metrics: median wait latency, p90 latency, mean RTF (target ≤0.35 on Intel CPU int8), and outlier share ≤5% over 20 runs
**Notes:** Fulfills requirement ACC-06.

| Option | Description | Selected |
|--------|-------------|----------|
| Comprehensive documentation: full JSONL schema, privacy invariants, corpus capture controls, durability fallback behavior, complete env var table, and purge commands in `docs/telemetry.md` & README | Complete user transparency | ✓ |
| Minimal update: CLI flags in README only | Minimal doc additions | |
| You decide | Comprehensive documentation | |

**User's choice:** Comprehensive documentation: full JSONL schema, privacy invariants (no audio/text saved by default), corpus capture controls, durability fallback behavior, complete env var table, and purge commands in `docs/telemetry.md` & README
**Notes:** Fulfills requirement ACC-07.

---

## Multi-Chunk Outlier Attribution

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: session-level outlier flag based on end-to-end wait latency & total RTF, while per-chunk details are recorded in `chunks` array | Both macro and micro tracking | ✓ |
| Strict whole-session only | Ignore per-chunk details | |
| Taint-on-any: mark session outlier if any single chunk is slow | Aggressive session tainting | |
| You decide | Hybrid tracking | |

**User's choice:** Hybrid: session-level outlier flag based on end-to-end wait latency & total RTF, while per-chunk timing details (`rtf`, `decode_ms`, `outlier`) are recorded in the `chunks` array in `metrics.jsonl`
**Notes:** Granular insight without skewing top-level wait metrics.

| Option | Description | Selected |
|--------|-------------|----------|
| Save complete continuous audio recording (`{run_id}_full.wav`) | Preserves cadence and acoustic context | ✓ |
| Save only isolated slow chunk file | Disk-saving chunk only | |
| You decide | Full audio recording | |

**User's choice:** Save the complete continuous audio recording (`{run_id}_full.wav`) — preserves surrounding acoustic context and speech cadence for accurate offline reproduction
**Notes:** Critical for reproducing boundary context in Whisper decoding.

| Option | Description | Selected |
|--------|-------------|----------|
| Primary row displays total wait latency & session RTF, with `[chunks: 2]` badge expanding in HTML view | Clean summary with drilldown | ✓ |
| Strict single-row summary without multi-chunk distinction | No chunk indicator | |
| You decide | Table row with chunk count indicator | |

**User's choice:** Primary row displays total wait latency & session RTF, with a badge/sub-line `[chunks: 2]` linking or expanding to individual chunk timings in the HTML view
**Notes:** Clean visual hierarchy.

| Option | Description | Selected |
|--------|-------------|----------|
| Record `retries: int` (count of fallback temperature attempts) per chunk in telemetry | Quantifies Whisper difficulty without storing text | ✓ |
| Boolean flag `retry_occurred: bool` | Simple boolean | |
| You decide | Integer retry count | |

**User's choice:** Record `retries: int` (count of fallback temperature attempts) per chunk in the telemetry record — quantifies Whisper decoding difficulty without storing text
**Notes:** Pinpoints why specific chunks experienced high RTF.

| Option | Description | Selected |
|--------|-------------|----------|
| Resilient partial delivery: type text from successfully decoded chunks, log warning for failed chunk, record `failed_chunks: [i]`, mark `outcome: "partial_success"` | Maximizes user utility | ✓ |
| All-or-nothing: abort insertion entirely on any chunk failure | Discard all text | |
| You decide | Deliver available text with clear error telemetry | |

**User's choice:** Resilient partial delivery: type text from successfully decoded chunks, log a warning for any failed chunk, record `failed_chunks: [i]` in telemetry, and mark `outcome: "partial_success"`
**Notes:** Never lose already-transcribed sentences.

| Option | Description | Selected |
|--------|-------------|----------|
| User wait latency is strictly elapsed wall-clock time from `stop_requested` until typing completes | Reflects actual user wait time | ✓ |
| Total decode duration summed across all chunks | Excludes background overlap | |
| You decide | Measure time from hotkey release to typing finish | |

**User's choice:** User wait latency is strictly elapsed wall-clock time from `stop_requested` (hotkey release) until text typing completes — background decodes while recording are zero-wait to the user
**Notes:** Honest accounting of perceived user delay.

| Option | Description | Selected |
|--------|-------------|----------|
| Clean cancellation: discard partial transcripts, emit cancellation chime, record `outcome: "cancelled"`, unlink temp files | Clean abort | ✓ |
| Paste partial text that was decoded before cancel | Inject partial text | |
| You decide | Clean abort, no typing, record cancellation telemetry | |

**User's choice:** Clean cancellation: discard decoded partial transcripts, emit cancellation audio chime, record `outcome: "cancelled"` with completed chunk metrics, and unlink temporary files
**Notes:** Hotkey cancellation (`SUPER+ALT+M`) means user wants to discard dictation.

| Option | Description | Selected |
|--------|-------------|----------|
| Monotonic progression: publish status incrementally as each chunk finishes (`transcribed_audio_s` jumps forward, `segments_done` increments) | Drives real-time Quickshell dual timers | ✓ |
| Batch update at start and session finish | Infrequent updates | |
| You decide | Monotonic incremental updates | |

**User's choice:** Monotonic progression: publish status incrementally as each chunk finishes (`transcribed_audio_s` jumps forward, `segments_done` increments), powering real-time Quickshell dual timers
**Notes:** Perfectly powers the Phase 9 status pill.

---

## Corpus FIFO Eviction Mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| Inline before saving: enforce 50-file / 100 MB caps immediately prior to writing new corpus WAV in `finalize_background_run()` | Quota is never breached | ✓ |
| Periodic maintenance in `voice --doctor` | Delayed pruning | |
| You decide | Inline check before save | |

**User's choice:** Inline before saving: enforce 50-file / 100 MB caps immediately prior to writing a new corpus WAV file in `finalize_background_run()` — guarantees the quota is never breached at any moment
**Notes:** Absolute quota boundary enforcement.

| Option | Description | Selected |
|--------|-------------|----------|
| Strict chronological FIFO: prune oldest files first (by file `mtime` / timestamp) until count < 50 and size < 100 MB | Preserves recent history | ✓ |
| Largest-first | Delete largest files first | |
| You decide | Oldest-first FIFO | |

**User's choice:** Strict chronological FIFO: prune oldest files first (by file `mtime` / timestamp) until count < 50 and directory size < 100 MB — preserves the most recent diagnostic history
**Notes:** Most recent bugs and outliers remain inspectable.

| Option | Description | Selected |
|--------|-------------|----------|
| Atomic write + grace window: write incoming audio to `.tmp_*.wav` then `os.replace()`; never evict files newer than 60 seconds | Completely immune to torn/in-flight deletion | ✓ |
| Check `fuser` / `lsof` process locks | Subprocess inspection | |
| You decide | Atomic rename and grace window | |

**User's choice:** Atomic write + grace window: write incoming audio to `.tmp_*.wav` then `os.replace()` to final name; never evict files newer than 60 seconds — completely immune to torn/in-flight deletion
**Notes:** Rock-solid POSIX filesystem hygiene.

| Option | Description | Selected |
|--------|-------------|----------|
| Log to `voice.log` only (`Pruned N corpus files (X MB reclaimed)`) + surface cumulative count in `voice --doctor` | Quiet background execution | ✓ |
| Show desktop toast on eviction | Distracting notification | |
| You decide | Quiet file logging and doctor summary | |

**User's choice:** Log to `voice.log` only (`Pruned N corpus files (X MB reclaimed)`) + surface cumulative pruned count in `voice --doctor` diagnostics — completely quiet during normal use
**Notes:** No desktop distraction.

| Option | Description | Selected |
|--------|-------------|----------|
| Clear CLI feedback: print `Purged N corpus audio files (X.X MB reclaimed)` and exit 0 | Clean scriptable feedback | ✓ |
| Interactive confirmation prompt `[y/N]` | Requires interactive TTY | |
| You decide | Non-interactive CLI feedback with byte count | |

**User's choice:** Clear CLI feedback: print `Purged N corpus audio files (X.X MB reclaimed)` and exit 0 (with `--force` / `-y` flag if non-interactive)
**Notes:** Convenient administrative tool.

| Option | Description | Selected |
|--------|-------------|----------|
| Ledger remains strictly append-only and immutable: `metrics.jsonl` never modified; missing files show `[audio: pruned]` | Preserves historical metrics | ✓ |
| Rewrite `metrics.jsonl` to remove `corpus_file` references | Mutate ledger | |
| You decide | Immutable ledger with missing-file fallback | |

**User's choice:** Ledger remains strictly append-only and immutable: `metrics.jsonl` is never modified; if a referenced audio file is later pruned, reports gracefully show `[audio: pruned]`
**Notes:** Upholds immutable ledger architecture.

| Option | Description | Selected |
|--------|-------------|----------|
| Fail-safe non-blocking: catch permission/creation errors, log warning, skip corpus save, allow dictation to finish | Fail safe | ✓ |
| Crash and alert | Abort execution | |
| You decide | Fail-safe non-blocking | |

**User's choice:** Fail-safe non-blocking: catch permission or creation errors, log a one-line warning, skip corpus saving, and allow transcription and typing to finish without disruption
**Notes:** Diagnostic tools must never crash user dictation.

| Option | Description | Selected |
|--------|-------------|----------|
| Privacy card in HTML report footer displays total corpus disk usage and exact CLI command (`voice --purge-corpus`) | Zero JS, static command | ✓ |
| Dedicated HTML button calling background script | Requires web server | |
| You decide | Static text card with command | |

**User's choice:** Privacy card in HTML report footer displays total corpus disk usage and exact CLI command (`voice --purge-corpus`) to delete — zero JavaScript, zero active web server required
**Notes:** Preserves zero-JS, offline-only report design.

---

## Cold-Boot & Zero-Run Baseline

| Option | Description | Selected |
|--------|-------------|----------|
| Informative clean state: display `Telemetry: ready (0 runs recorded). Establish performance baseline by recording with SUPER+SHIFT+M` | Advisory neutral, exit 0 | ✓ |
| Warning state | Yellow warning | |
| You decide | Clean advisory status | |

**User's choice:** Informative clean state: display `Telemetry: ready (0 runs recorded). Establish performance baseline by recording with SUPER+SHIFT+M` (advisory neutral, exit 0)
**Notes:** Friendly onboarding experience.

| Option | Description | Selected |
|--------|-------------|----------|
| Onboarding state: terminal prints guidance and keyboard shortcuts; HTML displays onboarding card with dashed ghost chart outlines | Exit 0 with visual guidance | ✓ |
| Simple message: `No runs found in ledger` | Bare text | |
| You decide | Onboarding state with visual guidance | |

**User's choice:** Onboarding state: terminal prints guidance and keyboard shortcuts; HTML displays onboarding card with dashed ghost chart outlines (exit 0)
**Notes:** Matches existing D-08 onboarding card contract.

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit `cold_load: true` flag in ledger record (using `check_and_mark_boot_session()`) | Isolates cold model loading overhead from warm latency | ✓ |
| No flag | Treat all runs uniformly | |
| You decide | Explicit cold_load flag | |

**User's choice:** Explicit `cold_load: true` flag in ledger record (using `check_and_mark_boot_session()`), allowing reports and doctor to isolate cold-start overhead from steady-state warm latency
**Notes:** Honest attribution of disk load vs Whisper compute latency.

| Option | Description | Selected |
|--------|-------------|----------|
| Generate empty-state onboarding `report.html` on first doctor check or hotkey setup, then overwrite on first completed run | Clicking Quickshell pill never hits 404 | ✓ |
| Generate only after first successful run completes | Delay report creation | |
| You decide | Pre-generate onboarding report | |

**User's choice:** Generate empty-state onboarding `report.html` on first doctor check or hotkey setup, then overwrite on first completed run — ensures clicking the Quickshell pill never hits a 404 / missing file
**Notes:** Seamless desktop bar click-through experience.

---

## The Agent's Discretion

- Exact SVG styling parameters (stroke widths, marker dimensions) for outlier indicators.
- Internal helper decomposition in `voicemode_telemetry.py` and `voicemode_report.py`.
- Mocking harness details for `tests/test_durability.py`.

## Deferred Ideas

- **Phase 11: Voice Desktop Pop-up UI**: Desktop interactive Quickshell overlay popup window for voice recording history, settings, and telemetry. Confirmed by user to be built in Phase 11.
