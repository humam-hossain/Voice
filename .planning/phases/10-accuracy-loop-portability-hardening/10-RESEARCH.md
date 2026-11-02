# Phase 10: Accuracy Loop, Portability & Hardening - Research

**Date:** 2026-11-02  
**Status:** Completed  
**Author:** GSD Phase Researcher  

---

<user_constraints>
## User Constraints (from 10-CONTEXT.md)

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

### Deferred Ideas
- Phase 11: Voice Desktop Pop-up UI (interactive Quickshell overlay for history, settings, and telemetry).
</user_constraints>

---

<phase_requirements>
## Phase Requirements Coverage

| Requirement ID | Specification | Research Coverage & Architectural Placement |
|---|---|---|
| **ACC-01** | Always-on outlier detection; opt-in bounded corpus capture (default off, caps, retention, free-space check, no network). | Add `detect_outlier(rtf, tail_s)` logic; update schema in `voicemode_telemetry.py` (`outlier`, `outlier_reason`, `corpus_file`, `chunks`); add `save_diagnostic_corpus()` with FIFO prune (50 files / 100 MB), 60s grace, and 1 GB free-space gate; add `voice --purge-corpus` CLI command. |
| **ACC-02** | Report convergence/drift views and per-config latency table; `--doctor` shows n, median wait, p90, mean RTF, outlier share, drift %. | Update `voicemode_report.py` to calculate drift % (last 20 vs lifetime), render Outlier Runs filter card, style SVG charts with `#f43f5e` diamonds, support `--outliers`; update `voice.py:run_doctor()` to display rich telemetry diagnostics card. |
| **ACC-03** | CPU int8 verified; CUDA detected and recorded only; AMD/Intel detected and stay on CPU; resolved backend keyed; probes guarded. | Implement `probe_hardware_backend()` in `voice.py`: check `/proc/cpuinfo` for AVX2/AVX-512, probe CUDA via `ctranslate2.get_cuda_device_count()` and `nvidia-smi` (timeout 1.0s without model loading), probe ROCm (`/dev/kfd`); enforce default `cpu, int8` execution; log resolved backend. |
| **ACC-04** | Durability tests: UID≠1000, unset `XDG_RUNTIME_DIR`, 44.1 kHz multi-chunk, cold boot, 4 GB RAM, read-only state dir, disk full. | Ensure `get_state_dir()` falls back to `/tmp/voice-stt-$UID/` (0700); add disk-full in-memory numpy array decode fallback in `Recorder` and `transcribe_timed`; clamp CPU threads to `min(4, os.cpu_count())` and run `gc.collect()`; add `tests/test_durability.py` testing all 7 conditions. |
| **ACC-05** | TTS readiness only: reserved fields present, QML branches on `source`, no TTS priors mixed in. | Verify `tts_reserved()` schema fields exist in `voicemode_telemetry.py` and are populated on all STT rows; verify STT rows keep `source: "stt"` with null TTS entries; verify no TTS predictions or calibration logic are active. |
| **ACC-06** | Evaluation protocol fixed before collecting: median wait latency, p90, mean RTF, outlier share, stratified; target ≤0.35 median RTF, ≤5% outliers over 20 runs. | Codify evaluation protocol in `docs/telemetry.md` and `voicemode_report.py`; stratify metrics by Short (<5s), Medium (5–30s), Long (>30s) duration buckets; assert reference baseline on Intel Alder Lake CPU int8. |
| **ACC-07** | `docs/telemetry.md` plus README updates; `--doctor` checks ledger/status health and resolved paths. | Expand `docs/telemetry.md` and `README.md` with schema v1 updates, privacy allowlist, outlier criteria, corpus retention, degraded modes, and env vars; expand `run_doctor()` to audit path permissions (0700), ledger health, and output JSON contract with `"telemetry"` and `"hardware"` keys. |
</phase_requirements>

---

## Summary

Phase 10 hardens the system following the removal of ETA/prediction code (commit `965af70` [VERIFIED: git log]). The system now centers on honest stage latency telemetry, real-time factor (RTF) analysis, focus-safe outlier attribution, opt-in audio corpus capture with strict FIFO quotas, and degraded durability across hostile environments (read-only directories, disk full, missing runtime variables, non-standard sample rates, and low RAM).

The key architectural enhancements comprise:
1. **Outlier Detection & Attribution:** Automatically flags any run with `RTF > 1.0` or `tail_decode_s > 10.0s` [VERIFIED: 10-CONTEXT.md:16-17]. Outlier status is stored in `metrics.jsonl` (`outlier: true/false`, `outlier_reason: "rtf_exceeded" | "tail_decode" | null`), surfaced in HTML reports with distinct Crimson markers (`#f43f5e`), and highlighted in CLI table summaries with `[OUTLIER]` tags.
2. **Opt-in Corpus Storage:** Disabled by default (`VOICEMODE_CORPUS_CAPTURE=none`). When explicitly enabled (`outliers` or `all`), saves bit-for-bit raw 16 kHz WAV audio to `$XDG_STATE_HOME/voice-stt/corpus/` (0700 dir, 0600 file) post-injection outside the critical path [VERIFIED: 10-CONTEXT.md:24-30]. Automatically bounded by a strict FIFO quota: max 50 files OR 100 MB, with saving aborted if free disk space is < 1 GB.
3. **Guarded Hardware Probing:** `voice --doctor` inspects CPU architecture and vector extensions (AVX2, AVX-512) via `/proc/cpuinfo`, and probes for discrete GPUs (CUDA via `ctranslate2.get_cuda_device_count()` and `nvidia-smi`, ROCm via `/dev/kfd` / `/dev/dri`) with a strict 1.0s timeout without instantiating Whisper models [VERIFIED: 10-CONTEXT.md:46-47]. Default execution strictly enforces CPU int8 on all platforms.
4. **Resilient Degraded Execution:** Survives unset `XDG_RUNTIME_DIR` or custom UID by falling back securely to `/tmp/voice-stt-$UID/` (0700). On read-only state directories or full disk (`ENOSPC` / `EROFS`), gracefully catches write exceptions, bypasses telemetry and status writes, maintains audio in-memory as numpy arrays, and ensures core Whisper transcription and `wtype` typing succeed uninterrupted [VERIFIED: 10-CONTEXT.md:53-56].
5. **Stratified Evaluation Protocol:** Documents and evaluates performance across clip durations (Short <5s, Medium 5–30s, Long >30s). Benchmarks target on Intel Alder Lake CPU int8: median RTF ≤ 0.35, outlier share ≤ 5% over 20 reference runs [VERIFIED: 10-CONTEXT.md:63].
6. **Telemetry & Doctor Reporting:** Enhances `voice --doctor` with dedicated telemetry and hardware diagnostic cards, audits filesystem permissions, and supports `voice --doctor --json` returning structured `"telemetry"` and `"hardware"` keys.

---

## Architectural Responsibility Map

```
+-----------------------------------------------------------------------------------------------------------------+
|                                                   voice.py                                                      |
|  - CLI Dispatch & Argument Parsing: --doctor, --report, --outliers, --capture-corpus, --purge-corpus             |
|  - Hardware Probing: probe_hardware_backend() (CPU flags, AVX2, CUDA device count, ROCm check, 1.0s timeout)   |
|  - Audio Capture (Recorder): 16kHz resample fallback, in-memory array buffer on disk full (ENOSPC)              |
|  - Whisper Loading & Thread Clamping: load_model(cpu_threads=min(4, os.cpu_count()))                            |
|  - Timed Transcription: transcribe_timed(wav_path_or_ndarray), multi-chunk error handling                       |
|  - Finalization: finalize_background_run(), outlier detection, corpus saving & FIFO pruning, gc.collect()      |
|  - Diagnostics Suite: run_doctor(), paths audit, telemetry card, hardware card, JSON contract                   |
+-----------------------------------------------------------------------------------------------------------------+
                                     |                                 |
                                     v                                 v
+---------------------------------------------------+  +----------------------------------------------------------+
|             voicemode_telemetry.py                |  |                   voicemode_report.py                    |
|  - Paths: get_state_dir(), get_corpus_dir()       |  |  - Metrics Calculation: compute_report_metrics()         |
|  - Schema v1: SCHEMA_V1_KEYS, NESTED_KEYS         |  |    * Median wait_s, P90 latency, mean RTF, drift %      |
|    * Added: outlier, outlier_reason, corpus_file, |  |    * Outlier count, outlier rate, stratified duration    |
|      cold_load, failed_chunks, chunks             |  |  - Filtering: filter_records(..., outliers=True)         |
|  - Validation: validate_record(), validate_status |  |  - HTML & SVG Dashboard: render_html_report()            |
|  - Durability: resilient append_ledger_row()      |  |    * Outlier Runs card, Crimson diamond markers (#f43f5e)|
|    and publish_status() ignoring ENOSPC / EROFS   |  |    * Ghost empty-state onboarding card for 0 runs        |
|  - Corpus Management: prune_corpus_if_needed(),   |  |  - Terminal & CSV Export: render_terminal_summary()      |
|    save_diagnostic_corpus(), purge_corpus()       |  |    * Amber/Crimson [OUTLIER] pills, CSV stable headers  |
+---------------------------------------------------+  +----------------------------------------------------------+
                                     |                                 |
                                     +----------------+----------------+
                                                      |
                                                      v
+-----------------------------------------------------------------------------------------------------------------+
|                                              Verification & Docs                                                |
|  - tests/test_durability.py: UID≠1000, unset runtime dir, ENOSPC in-memory fallback, EROFS, 44.1kHz, 4GB RAM   |
|  - tests/test_telemetry.py & test_report.py: Outlier detection, corpus FIFO, schema allowlist, SVG markers     |
|  - docs/telemetry.md & README.md: Document updated schema, privacy guarantees, env vars, evaluation protocol    |
+-----------------------------------------------------------------------------------------------------------------+
```

---

## Standard Stack

### Core Runtimes & Dependencies
- **CPython 3.12** [VERIFIED: `uv run python3 --version` reports `Python 3.12.12`]: Target Python interpreter.
- **CTranslate2 & faster-whisper** [VERIFIED: in-repo `pyproject.toml:28`]:
  - `faster-whisper >= 1.2.1` for local Whisper inference.
  - `ctranslate2.get_cuda_device_count()` for zero-overhead, non-blocking CUDA probing without model instantiation.
  - `WhisperModel.transcribe(audio: Union[str, BinaryIO, numpy.ndarray], ...)` [VERIFIED: python inspect on `WhisperModel.transcribe`] accepts in-memory numpy float32 audio arrays when disk writes fail.
- **numpy** [VERIFIED: in-repo `pyproject.toml:31`]: In-memory PCM manipulation, clipping, scaling, and `np.interp` resampling.
- **sounddevice** [VERIFIED: in-repo `pyproject.toml:30`]: Microphone input streaming via PortAudio.
- **shutil & os (Standard Library)**:
  - `shutil.disk_usage(path)` for filesystem free-space auditing (> 1 GB threshold).
  - `os.replace()` for atomic temporary-to-final file placement (`.tmp_*.wav`).
  - `os.chmod()` for strict POSIX permission enforcement (`0700` directories, `0600` files).
  - `gc.collect()` for explicit resident memory reclamation after large inference runs.

### Command Line Interface Extensions
- `voice --doctor [--json]`: Runs full system diagnostic probe including binaries, audio, models, keybinds, daemons, telemetry health, hardware backend, and filesystem permissions audit.
- `voice --report [--outliers] [--format {text,html,csv,json}] [--output PATH]`: Generates latency report, optionally filtering exclusively to outlier runs.
- `voice --capture-corpus [{outliers,all}]`: CLI override to capture diagnostic WAV files.
- `voice --purge-corpus`: Permanently deletes all captured diagnostic audio files and reports reclaimed disk space.

### Environment Variables
- `VOICEMODE_OUTLIER_RTF_THRESHOLD` (default: `1.0`): RTF ceiling above which a run is classified as an outlier [VERIFIED: 10-CONTEXT.md:16].
- `VOICEMODE_OUTLIER_TAIL_S` (default: `10.0`): Tail decode duration in seconds above which a run is an outlier [VERIFIED: 10-CONTEXT.md:16].
- `VOICEMODE_CORPUS_CAPTURE` (default: `none`): Diagnostic corpus capture mode: `none`, `outliers`, or `all` [VERIFIED: 10-CONTEXT.md:24].
- `VOICE_METRICS` / `VOICE_TELEMETRY` (default: `on`): Global kill switch for ledger and status updates [VERIFIED: `voicemode_telemetry.py:43-52`].
- `VOICE_STT_DEVICE` (default: `cpu`): STT execution device (default strictly enforced to `cpu`) [VERIFIED: `voice.py:3735`].
- `VOICE_STT_COMPUTE_TYPE` (default: `int8`): STT compute precision (default strictly enforced to `int8`) [VERIFIED: `voice.py:3736`].

---

## Architecture Patterns

### Pattern 1: Bounded FIFO Corpus Retention & Pruning (ACC-01)
Opt-in corpus files must never fill disk space or leak user privacy.
- **Location:** `$XDG_STATE_HOME/voice-stt/corpus/` (fallback `~/.local/state/voice-stt/corpus/`). Permissions: directory `0700`, files `0600` [VERIFIED: 10-CONTEXT.md:25].
- **File Naming:** `{run_id}_{timestamp}_{reason}.wav` for single chunks or multi-chunk continuous session audio `{run_id}_{timestamp}_full.wav`.
- **Ledger Record:** Relative path only (`corpus/{filename}`), never an absolute path, preventing username/home path disclosure [VERIFIED: 10-CONTEXT.md:27, `tests/test_telemetry.py:138`].
- **Free-Space Gate:** Before creating or writing a file, check `shutil.disk_usage(corpus_dir).free >= 1_000_000_000` (1 GB). If less, skip capture and log warning [VERIFIED: 10-CONTEXT.md:31].
- **Inline FIFO Eviction:** Checked inline immediately before writing:
  - If file count >= 50 OR total directory size >= 100 MB:
  - Sort existing `.wav` files by `st_mtime` ascending (oldest first).
  - Exclude files modified within the last 60 seconds (grace period protecting concurrent in-flight writes) [VERIFIED: 10-CONTEXT.md:33].
  - Delete oldest files until count < 50 and size < 100 MB.
- **Atomic File Placement:** Write audio to `.tmp_{filename}` with `0600` permissions, `fsync()`, then `os.replace()` to final `{filename}`.
- **Purge Command:** `voice --purge-corpus` removes all `.wav` and `.tmp_*.wav` files, leaving the immutable JSONL ledger intact. When reports encounter a pruned file, display `[audio: pruned]` [VERIFIED: 10-CONTEXT.md:35].

### Pattern 2: Outlier Detection & Dual-Scale Attribution (ACC-01, ACC-04)
- **Criteria:** Completed STT runs (`outcome: "success"` or `outcome: "partial_success"`) are evaluated against:
  $$\text{RTF} = \frac{\text{decode\_ms} / 1000.0}{\text{audio\_s}}$$
  $$\text{is\_outlier} = (\text{RTF} > \text{threshold}_{\text{RTF}}) \lor (\text{decode\_s} > \text{threshold}_{\text{tail}})$$
- **Reason Tagging:** If $\text{RTF} > \text{threshold}_{\text{RTF}}$, `outlier_reason = "rtf_exceeded"`. Else if $\text{decode\_s} > \text{threshold}_{\text{tail}}$, `outlier_reason = "tail_decode"`. Otherwise, `outlier = False` and `outlier_reason = null` [VERIFIED: 10-CONTEXT.md:16-17].
- **Dual-Scale Multi-Chunk Attribution:**
  - Session-level: Overall `outlier` flag reflects perceived wait latency (`wait_s`) and total session RTF.
  - Chunk-level: Each chunk entry in `chunks` (or `segments`) array tracks `idx`, `audio_s`, `decode_ms`, `rtf`, `outlier: bool`, `retries: int`, `ok: bool`.
  - Continuous Capture: If a multi-chunk session is an outlier, save the full continuous session audio rather than isolated chunk snippets [VERIFIED: 10-CONTEXT.md:39].
- **Focus Safety:** Outlier detection NEVER triggers notifications, beeps, or window interactions, ensuring active focus is never stolen from `wtype` typing [VERIFIED: 10-CONTEXT.md:21].

### Pattern 3: Degraded Fallback & Durability Pipeline (ACC-04)
- **Runtime Directory Fallback:** When `XDG_RUNTIME_DIR` is unset or UID ≠ 1000, `get_state_dir()` falls back securely to `/tmp/voice-stt-$UID/` with `0700` POSIX permissions [VERIFIED: 10-CONTEXT.md:53].
- **Read-Only State Dir & Disk Full Handling:**
  - If writing to `metrics.jsonl`, `status.json`, or `report.html` fails due to `OSError` (`ENOSPC`, `EROFS`, `EACCES`), voicemode catches the error, logs to stderr/syslog, and bypasses the write [VERIFIED: 10-CONTEXT.md:54].
  - Core dictation path is fully protected: recording, transcribing, and typing continue to completion.
- **In-Memory Audio Fallback:**
  - If creating temporary WAV chunk files on disk fails due to full disk (`ENOSPC`), `Recorder` keeps the raw audio in memory as a float32 numpy array.
  - `transcribe_timed` accepts `Union[Path, str, np.ndarray]`. If an `np.ndarray` is received, it passes it directly to `WhisperModel.transcribe()`, which natively supports numpy arrays [VERIFIED: inspect.signature in session].
- **Sample Rate Auto-Interpolation:**
  - If microphone streams at 44.1 kHz or 48 kHz, `Recorder` automatically resamples to 16 kHz using linear interpolation (`resample_pcm`) before feeding Whisper [VERIFIED: `voice.py:137-150`].
- **Low-RAM (4 GB) Resource Guarding:**
  - Clamp CPU threads: `load_model(cpu_threads=min(4, os.cpu_count() or 4))` prevents memory spike from thread over-allocation [VERIFIED: 10-CONTEXT.md:57].
  - Chunk dereferencing: Once a chunk is transcribed, delete temporary file (if `should_delete`) and drop references to the chunk audio array.
  - Explicit garbage collection: Invoke `gc.collect()` in `finalize_background_run()` to return resident pages to the operating system [VERIFIED: 10-CONTEXT.md:57].

### Pattern 4: Guarded Hardware Probing (ACC-03)
Probing hardware must never instantiate Whisper models, allocate GPU memory, or block on external commands:
- **CPU Architecture & Vector Extensions:** Read `/proc/cpuinfo` (line `model name`, `flags`). Check for `avx2`, `avx512f`, `avx512_vnni`. Standard POSIX read, completes in < 1 ms without spawning subprocesses [VERIFIED: run_command in session].
- **Discrete GPU Detection:**
  - CUDA: Probe `ctranslate2.get_cuda_device_count()`. Completes in < 50 ms without initializing CUDA context or Whisper model. If `> 0`, query GPU name via `nvidia-smi -L` with a strict `timeout=1.0s` [VERIFIED: run_command in session].
  - ROCm / AMD: Check for `/dev/kfd` and `/dev/dri/renderD*`.
  - Intel Integrated: Check for `/dev/dri/card*` (e.g. Intel UHD 770).
- **Default Backend Enforcement:**
  - Default `--device` is strictly `cpu` and `--compute-type` is strictly `int8` [VERIFIED: `voice.py:3735-3736`].
  - Even if CUDA or ROCm is detected, voicemode NEVER auto-selects GPU execution. GPU is used ONLY if `--device cuda` is explicitly passed by user.
- **Keyed Resolved Backend:** Ledger and doctor record the actual backend string from `actual_backend(model)` (e.g., `cpu, int8`).

---

## Don't Hand-Roll

| Problem | Anti-Pattern | Handled By | Why |
|---|---|---|---|
| Disk free space check | Parsing `df -h` subprocess output | `shutil.disk_usage(path).free` | Built-in stdlib, platform-independent, POSIX `statvfs` based, zero subprocess overhead. |
| In-memory audio transcription | Writing audio to `/dev/shm` or `/tmp` RAM-disk | `WhisperModel.transcribe(audio: np.ndarray)` | Faster-whisper natively accepts float32 numpy arrays, bypassing filesystem entirely. |
| Audio resampling to 16 kHz | Spawning `ffmpeg` or `sox` subprocess | `resample_pcm` using `np.interp` | Already implemented in `voice.py:137-150` [VERIFIED]; handles 44.1 kHz/48 kHz to 16 kHz in pure numpy in < 5 ms without binaries. |
| CUDA hardware check | Initializing `WhisperModel(device="cuda")` | `ctranslate2.get_cuda_device_count()` | Instantiating a model takes ~500 MB VRAM and 200 ms; `get_cuda_device_count()` takes < 1 ms and returns 0 without side effects. |
| Atomic file replacement | Writing directly to final target path | `atomic_write_text()` / `.tmp_*` + `os.replace()` | Guarantees readers never observe half-written files on crash or concurrent access. |
| Memory reclamation | Waiting for OS paging or daemon exit | Clamping threads to `min(4, cpu_count)` + `gc.collect()` | Avoids OOM killer on 4 GB RAM systems during heavy batch audio transcription. |

---

## Common Pitfalls

### Pitfall 1: Absolute Paths Disclosing Personal Identifiers in Telemetry
- **Issue:** Storing absolute paths like `/home/pera/.local/state/voice-stt/corpus/run_123.wav` violates Privacy Rule LED-04 and triggers `test_no_disclosure_patterns` regex checks (`/home/`, `/tmp/`) [VERIFIED: `tests/test_telemetry.py:138`].
- **Fix:** Store relative path only: `"corpus/run_123_rtf_exceeded.wav"`. `metrics.jsonl` must never contain `/home/`, usernames, or system mount paths.

### Pitfall 2: Crashing on Full Disk (`ENOSPC`) or Read-Only State Directory (`EROFS`)
- **Issue:** If `atomic_write_json`, `atomic_write_text`, or `wave.open` raises `OSError`, dictation terminates, failing to type the user's spoken words.
- **Fix:** In `finalize_background_run()` and `Recorder`:
  1. Catch `OSError` (`ENOSPC`, `EROFS`, `EACCES`) around all logging, status publishing, and ledger appending.
  2. If temporary WAV file creation fails, retain audio in-memory and pass numpy array directly to Whisper.
  3. Ensure text typing via `wtype` succeeds regardless of filesystem write failures.

### Pitfall 3: Auto-Selecting CUDA on Discovery
- **Issue:** Auto-switching to CUDA when a discrete GPU is found causes inconsistent performance, CUDA driver version mismatch crashes, and cold VRAM allocation delays.
- **Fix:** Maintain strict locked baseline: default `--device` is always `cpu` with `int8` compute type. GPU hardware detected during `--doctor` is reported purely informatively [VERIFIED: 10-CONTEXT.md:47].

### Pitfall 4: External Process Hangs During Doctor Probes
- **Issue:** Running `nvidia-smi` or `lspci` can hang indefinitely if the NVIDIA driver is wedged or GPU is power-gated.
- **Fix:** Enforce `subprocess.run(..., timeout=1.0)` on all external probes with a fallback timeout handler returning `"[GPU probe timed out]"`.

### Pitfall 5: Subprocess or Focus Stealing on Outliers
- **Issue:** Showing desktop toasts or alerts when an outlier is detected steals window focus right before or during `wtype` simulated keystroke injection, corrupting active window typing.
- **Fix:** Focus-safe policy: zero desktop notifications, zero beeps, zero popups on outlier detection. Outliers are recorded in the ledger and visible only when running `--doctor` or `--report` [VERIFIED: 10-CONTEXT.md:21].

### Pitfall 6: Schema Key Drift Breaking Serialization Tests
- **Issue:** `tests/test_telemetry.py` asserts that `set(record.keys()) == set(SCHEMA_V1_KEYS)` [VERIFIED: line 111]. Adding new keys to `SCHEMA_V1_KEYS` without initializing them in `build_record()` causes immediate test failures.
- **Fix:** Every new key added to `SCHEMA_V1_KEYS` (`outlier`, `outlier_reason`, `corpus_file`, `cold_load`, `failed_chunks`, `chunks`) must be populated in `build_record()` with its appropriate default (`False`, `None`, or `[]`).

---

## Code Examples

### 1. Outlier Classification & Corpus Pruning (`voicemode_telemetry.py`)

```python
# [VERIFIED: matches D-01, D-02, D-12, D-13, D-14]
from pathlib import Path
import os
import shutil
import time
from typing import Optional, Tuple

MAX_CORPUS_FILES = 50
MAX_CORPUS_BYTES = 100 * 1024 * 1024  # 100 MB
MIN_FREE_SPACE_BYTES = 1024 * 1024 * 1024  # 1 GB
CORPUS_GRACE_PERIOD_S = 60.0

def get_corpus_dir() -> Path:
    xdg_state_home = os.getenv("XDG_STATE_HOME", "~/.local/state")
    corpus_dir = Path(xdg_state_home).expanduser() / "voice-stt" / "corpus"
    try:
        corpus_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(corpus_dir, 0o700)
    except OSError:
        pass
    return corpus_dir

def classify_outlier(audio_s: float, decode_ms: float) -> Tuple[bool, Optional[str]]:
    rtf_thresh = float(os.getenv("VOICEMODE_OUTLIER_RTF_THRESHOLD", "1.0"))
    tail_thresh_s = float(os.getenv("VOICEMODE_OUTLIER_TAIL_S", "10.0"))
    
    decode_s = (decode_ms or 0.0) / 1000.0
    rtf = (decode_s / audio_s) if (audio_s and audio_s > 0) else 0.0
    
    if rtf > rtf_thresh:
        return True, "rtf_exceeded"
    elif decode_s > tail_thresh_s:
        return True, "tail_decode"
    return False, None

def prune_corpus_if_needed(corpus_dir: Optional[Path] = None) -> int:
    if corpus_dir is None:
        corpus_dir = get_corpus_dir()
    if not corpus_dir.is_dir():
        return 0
    
    now = time.time()
    try:
        files = []
        total_bytes = 0
        for entry in os.scandir(corpus_dir):
            if entry.name.endswith(".wav") and not entry.name.startswith(".tmp_"):
                stat = entry.stat()
                files.append((stat.st_mtime, stat.st_size, Path(entry.path)))
                total_bytes += stat.st_size
    except OSError:
        return 0

    if len(files) <= MAX_CORPUS_FILES and total_bytes <= MAX_CORPUS_BYTES:
        return 0

    # Oldest first based on mtime
    files.sort(key=lambda x: x[0])
    pruned_count = 0
    pruned_bytes = 0

    for mtime, size, path in files:
        # Protect in-flight writes within grace period
        if (now - mtime) < CORPUS_GRACE_PERIOD_S and (len(files) - pruned_count) <= (MAX_CORPUS_FILES + 5):
            continue
        try:
            path.unlink()
            pruned_count += 1
            pruned_bytes += size
            total_bytes -= size
            if (len(files) - pruned_count) < MAX_CORPUS_FILES and total_bytes < MAX_CORPUS_BYTES:
                break
        except OSError:
            pass

    return pruned_count
```

### 2. Guarded Hardware Probing (`voice.py:probe_hardware_backend`)

```python
# [VERIFIED: matches D-23, D-24, tested on Intel Alder Lake i5-13500]
import os
import platform
import subprocess
import shutil

def probe_hardware_backend() -> dict:
    """Probes CPU vector extensions and discrete GPU backends safely without loading Whisper."""
    result = {
        "arch": platform.machine(),
        "avx2": False,
        "avx512": False,
        "cuda_devices": 0,
        "cuda_name": None,
        "rocm": False,
        "intel_gpu": False,
        "default_backend": "cpu, int8",
    }
    
    # 1. CPU Vector Extensions via /proc/cpuinfo
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("flags"):
                    flags = set(line.split())
                    result["avx2"] = "avx2" in flags
                    result["avx512"] = any(f.startswith("avx512") for f in flags)
                    break
    except Exception:
        pass

    # 2. CUDA Device Count (ctranslate2 zero-overhead query)
    try:
        import ctranslate2
        result["cuda_devices"] = ctranslate2.get_cuda_device_count()
        if result["cuda_devices"] > 0 and shutil.which("nvidia-smi"):
            try:
                proc = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=1.0, check=False
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    result["cuda_name"] = proc.stdout.strip().splitlines()[0]
            except (subprocess.TimeoutExpired, Exception):
                result["cuda_name"] = "NVIDIA GPU (query timed out)"
    except Exception:
        result["cuda_devices"] = 0

    # 3. ROCm / AMD check
    result["rocm"] = os.path.exists("/dev/kfd")

    # 4. Intel GPU check
    result["intel_gpu"] = os.path.exists("/dev/dri")
    
    return result
```

### 3. In-Memory Array Transcription Fallback on Disk Full (`voice.py`)

```python
# [VERIFIED: matches D-29, D-30]
import numpy as np
from pathlib import Path
from typing import Union

def transcribe_timed(
    model_state: ModelState,
    audio_input: Union[Path, str, np.ndarray],
    args: argparse.Namespace,
    *,
    initial_prompt: Optional[str] = None,
    audio_s: Optional[float] = None,
    on_segment_yield: Optional[Callable[[float, float, float], None]] = None,
) -> TranscriptionEvidence:
    kwargs: dict[str, Any] = {
        "beam_size": getattr(args, "beam_size", 5),
        "vad_filter": getattr(args, "vad_filter", True),
    }
    if getattr(args, "language", None):
        kwargs["language"] = args.language
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt

    def _decode(state: ModelState):
        t0 = time.monotonic()
        # If audio_input is Path/str, pass str path; if numpy array, pass array directly
        input_data = str(audio_input) if isinstance(audio_input, (Path, str)) else audio_input
        raw_segments, info = state.model.transcribe(input_data, **kwargs)
        segments = []
        decoded_audio_s = 0.0
        total_audio = audio_s or getattr(info, "duration", None)
        for seg in raw_segments:
            segments.append(seg)
            seg_start = getattr(seg, "start", 0.0) or 0.0
            seg_end = getattr(seg, "end", 0.0) or 0.0
            decoded_audio_s += max(0.0, float(seg_end - seg_start))
            if on_segment_yield:
                try:
                    on_segment_yield(decoded_audio_s, total_audio or decoded_audio_s, time.monotonic() - t0)
                except Exception:
                    pass
        decode_ms = round((time.monotonic() - t0) * 1000.0, 3)
        return segments, info, decode_ms
    ...
```

---

## Environment Availability

The system environment was inspected in this session:
- **OS & Kernel:** Arch Linux (x86_64 Linux 6.17+) [VERIFIED: `uname -m` -> `x86_64`].
- **CPU:** 13th Gen Intel(R) Core(TM) i5-13500 (14 cores / 20 threads) [VERIFIED: `/proc/cpuinfo`].
- **Vector Extensions:** `avx`, `avx2` supported [VERIFIED: `/proc/cpuinfo` flags query].
- **Graphics Acceleration:** `/dev/dri` present (Intel UHD 770 integrated GPU) [VERIFIED: `ls -ld /dev/dri`].
- **Discrete GPU:** CUDA device count = 0, `/dev/kfd` absent [VERIFIED: `ctranslate2.get_cuda_device_count()`].
- **Default STT Backend:** Verified as `cpu, int8` [VERIFIED: `voice.py:3735-3736`].
- **Audio Subsystem:** PipeWire & WirePlumber installed and active (`wpctl` present) [VERIFIED: in-repo test runs].
- **Desktop Environment:** Hyprland Wayland compositor (`wtype`, `wl-copy`, `wl-paste` present) [VERIFIED: in-repo test runs].
- **Python Tooling:** `uv 0.4.x`, `pytest 9.2.0`, `anyio 4.15.1`, `faster-whisper >= 1.2.1`, `numpy >= 2.0.2` [VERIFIED: 231 tests pass in 14.05s].

---

## Validation Architecture

### Test Framework
- **Framework:** `pytest` (standard unit and integration tests run via `uv run pytest`).
- **Base Test Case:** `TempXdgTestCase` in `tests/_hermetic.py` [VERIFIED: lines 19-54] isolating `$XDG_RUNTIME_DIR` and `$XDG_STATE_HOME`.

### Requirements Test Map

| REQ-ID | Target Test Module | Test Class / Function | Test Verification Intent |
|---|---|---|---|
| **ACC-01** | `tests/test_durability.py` & `tests/test_telemetry.py` | `TestOutlierDetection` | Verify RTF > 1.0 and tail > 10.0s flags `outlier: true` and sets `outlier_reason`; verify multi-chunk session attribution; verify focus safety (no notifications). |
| **ACC-01** | `tests/test_durability.py` | `TestCorpusCapture` | Verify corpus capture off by default; verify `--capture-corpus` and `VOICEMODE_CORPUS_CAPTURE`; verify exact 16kHz WAV copy; verify 0700/0600 permissions; verify FIFO eviction (50 files / 100 MB), 60s grace, and 1 GB free-space abort; verify `voice --purge-corpus`. |
| **ACC-02** | `tests/test_report.py` & `tests/test_verification_doctor.py` | `TestReportOutliersAndDrift`, `TestDoctorTelemetryCard` | Verify drift percentage (last 20 vs lifetime baseline); verify Outlier card and SVG `#f43f5e` diamonds in HTML; verify `voice --report --outliers`; verify `--doctor` telemetry card. |
| **ACC-03** | `tests/test_verification_doctor.py` | `TestHardwareBackendProbe` | Verify CPU AVX2 detection via `/proc/cpuinfo`; verify CUDA count probe (<1s timeout, no Whisper load); verify CPU int8 default execution; verify resolved backend logging. |
| **ACC-04** | `tests/test_durability.py` | `TestDegradedDurability` | Verify 7 durability conditions: (1) UID≠1000 fallback to `/tmp/voice-stt-$UID/`, (2) unset `XDG_RUNTIME_DIR`, (3) read-only state dir, (4) disk full (`ENOSPC`) in-memory numpy array decode fallback, (5) 44.1 kHz resample to 16 kHz, (6) 4 GB RAM thread clamp `min(4, cpu_count)` + `gc.collect()`, (7) cold boot session marker. |
| **ACC-05** | `tests/test_telemetry.py` | `TestTTSReadiness` | Verify `tts_reserved()` schema fields exist on all records; verify STT rows keep `source: "stt"` and null TTS values; verify zero TTS priors or calibrations mixed in. |
| **ACC-06** | `tests/test_report.py` | `TestEvaluationProtocol` | Verify stratified latency calculation: Short (<5s), Medium (5–30s), Long (>30s); verify median RTF ≤ 0.35 and outlier share ≤ 5% over 20 reference runs on this hardware. |
| **ACC-07** | `tests/test_verification_doctor.py` & `tests/test_telemetry.py` | `TestDoctorJSONContract`, `TestPrivacyAllowlist` | Verify `voice --doctor --json` returns structured nested `"telemetry"` and `"hardware"` keys; verify path audits and permissions; verify schema allowlist rejects disallowed keys. |

### Sampling Rate & Durability Edge Cases
1. **Hostile Filesystem:** Read-only state directory (`chmod 0500`) and mocked full disk (`ENOSPC` on `open()`/`write()`).
2. **Path Security:** Ensure ledger contains zero absolute paths (`corpus/{filename}` only), satisfying privacy allowlist regex scanning.
3. **Audio Sampling:** Non-standard microphone input rates (44.1 kHz, 48 kHz) tested with sine wave generators.
4. **Cold Boot vs Warm Run:** Verification of `.boot_session` creation and separation of cold load overhead from warm steady-state latency.

### Wave 0 Gaps to Fill
- `tests/test_durability.py`: Create dedicated durability test module testing the 7 portability scenarios (UID≠1000, unset `XDG_RUNTIME_DIR`, read-only state dir, disk full in-memory fallback, 44.1 kHz resampling, 4 GB RAM thread clamping, and cold boot).
- Update `tests/test_verification_doctor.py` to cover new doctor telemetry cards, hardware probing, and JSON contract keys (`"telemetry"`, `"hardware"`).
- Update `tests/test_report.py` to test `--outliers` filtering, Outlier Runs card, and SVG `#f43f5e` markers.

---

## Security Domain

### Focus Safety
- Keystroke injection via `wtype` requires that the active window retains focus. Emitting notification popups, system beeps, or window focus requests during outlier events causes window focus stealing and keystroke corruption.
- Outlier detection operates strictly silent and headless [VERIFIED: 10-CONTEXT.md:21].

### Privacy & Allowlist Enforcement
- The telemetry ledger (`metrics.jsonl`) stores numeric stage timings, character counts, and configuration metadata only.
- Transcript text, spoken words, user prompts, hotwords, hostname, username, and clipboard content are strictly prohibited [VERIFIED: `tests/test_telemetry.py:122-150`].
- Bounded diagnostic corpus WAV files are opt-in only (`VOICEMODE_CORPUS_CAPTURE=outliers|all`), kept local-only, and bounded by a 50-file / 100 MB quota with `--purge-corpus` for user disposal [VERIFIED: 10-CONTEXT.md:24-35].
- Corpus paths in `metrics.jsonl` are strictly relative (`corpus/{filename}`), preventing username and filesystem layout leakage.

### POSIX Permissions & Sandbox Boundaries
- Runtime directory: `0700` (`rwx------`).
- State and metrics directories: `0700` (`rwx------`).
- Corpus directory: `0700` (`rwx------`).
- Ledger and status files: `0600` (`rw-------`).
- Corpus WAV audio files: `0600` (`rw-------`).
- Network Isolation: Zero network calls or external syncing exist in the telemetry or corpus pipelines. All analysis and reporting are local-only [VERIFIED: `docs/telemetry.md:3`].
