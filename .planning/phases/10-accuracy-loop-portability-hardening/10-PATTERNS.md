# Phase 10: Accuracy Loop, Portability & Hardening — Pattern Map

## Files to Create / Modify

### Summary Table

| # | File | Role | Action | Closest Analog |
|---|------|------|--------|----------------|
| 1 | `voicemode_telemetry.py` | Telemetry schema, outlier detection, corpus FIFO management, path resolution, and resilient writes | **Modify** | Self (existing path, schema, atomic write, and health patterns) |
| 2 | `voicemode_report.py` | Latency reporting engine, outlier SVG rendering, drift calculations, stratified duration metrics, and `--outliers` filter | **Modify** | Self (existing filter, SVG generator, and terminal summary patterns) |
| 3 | `voice.py` | CLI dispatch, hardware backend probe, in-memory audio array fallback on disk full, 16kHz resampling, low-RAM thread clamping, doctor diagnostics, and finalizer integration | **Modify** | Self (existing `load_model`, `Recorder`, `transcribe_timed`, `finalize_background_run`, and `run_doctor`) |
| 4 | `tests/test_durability.py` | Automated durability & degraded operations test suite covering all 7 portability conditions, outlier detection, and corpus retention | **Create** | `tests/_hermetic.py` (`TempXdgTestCase`) + `tests/test_telemetry.py` + `tests/test_audio_chunking.py` |
| 5 | `tests/test_telemetry.py` | Schema v1 allowlist validation, privacy checks (relative corpus paths), outlier classification, and resilient write tests | **Modify** | Self (existing `TestSchemaV1`, `TestPrivacy`, `TestTracerContract`) |
| 6 | `tests/test_report.py` | Unit tests for `--outliers` filtering, drift % calculation, stratified duration metrics, SVG `#f43f5e` markers, and ghost empty state | **Modify** | Self (existing `_make_record`, `TestReportCLI`, `TestHtmlReportGeneration`) |
| 7 | `tests/test_verification_doctor.py` | Unit tests for hardware backend probe, doctor telemetry card, path permissions audit, JSON contract keys, and exit code semantics | **Modify** | Self (existing `TestCLIDispatch`, `TestDoctorDiagnostics`) |
| 8 | `docs/telemetry.md` | Authoritative documentation of Schema v1 updates, outlier criteria, opt-in corpus retention, degraded fallback modes, and evaluation protocol | **Modify** | Self (existing markdown tables and privacy guarantees) |
| 9 | `README.md` | Top-level documentation for new CLI flags (`--outliers`, `--capture-corpus`, `--purge-corpus`), doctor capabilities, and environment variables | **Modify** | Self (existing "At a Glance" and "CLI Reference" sections) |

---

## File 1: `voicemode_telemetry.py` (Telemetry & Corpus Engine) — MODIFY

**Path:** `/home/pera/github_repo/Voice/voicemode_telemetry.py`  
**Role:** Data contracts, schema validation, outlier classification, diagnostic corpus FIFO management, atomic filesystem writes, and status publishing.  
**Data flow:**  
- Telemetry write: `finalize_background_run()` → `classify_outlier()` → `build_record()` → `validate_record()` → `append_ledger_row()`.  
- Corpus capture: `save_diagnostic_corpus()` → `prune_corpus_if_needed()` → raw WAV saved to `$XDG_STATE_HOME/voice-stt/corpus/` (0700 dir, 0600 file) → relative path `corpus/{filename}` placed into ledger record.

### Analog: Self (`voicemode_telemetry.py`)

#### Pattern 1: Path Management with Strict POSIX Permissions (`get_corpus_dir()`)
Copy the pattern from `get_state_dir()` and `get_metrics_dir()` to create `get_corpus_dir()` pointing to `$XDG_STATE_HOME/voice-stt/corpus/` with `0700` permissions.

```python
# ANALOG: voicemode_telemetry.py:23-36
def get_state_dir() -> Path:
    xdg_runtime_dir = os.getenv("XDG_RUNTIME_DIR", f"/tmp/voice-stt-{os.getuid()}")
    state_dir = Path(xdg_runtime_dir) / "voice-stt"
    state_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    return state_dir

def get_metrics_dir() -> Path:
    xdg_state_home = os.getenv("XDG_STATE_HOME", "~/.local/state")
    metrics_dir = Path(xdg_state_home).expanduser() / "voicemode"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(metrics_dir, 0o700)
    return metrics_dir
```

**Implementation Pattern:**
```python
def get_corpus_dir() -> Path:
    xdg_state_home = os.getenv("XDG_STATE_HOME", "~/.local/state")
    corpus_dir = Path(xdg_state_home).expanduser() / "voice-stt" / "corpus"
    try:
        corpus_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(corpus_dir, 0o700)
    except OSError:
        pass
    return corpus_dir
```

#### Pattern 2: Schema Definition & Validation (`SCHEMA_V1_KEYS`, `NESTED_KEYS`, `build_record()`)
Extend `SCHEMA_V1_KEYS` with `"outlier"`, `"outlier_reason"`, `"corpus_file"`, `"cold_load"`, `"failed_chunks"`, `"chunks"`.

```python
# ANALOG: voicemode_telemetry.py:57-70
SCHEMA_V1_KEYS = {
    "schema", "source", "run_id", "install_id", "ts_start", "ts_end",
    "outcome", "error_stage", "actual", "audio_s",
    "chars_out", "chars_typed", "fallback_used", "insert_ok",
    "segments", "config", "backend", "tts",
    # NEW SCHEMA V1 KEYS (ACC-01, ACC-04):
    "outlier", "outlier_reason", "corpus_file", "cold_load", "failed_chunks", "chunks"
}

NESTED_KEYS = {
    "actual": {"total_ms", "finalize_ms", "load_ms", "decode_ms", "insert_ms"},
    "segments": {"idx", "audio_s", "decode_ms", "chars", "ok", "fallback", "avg_logprob", "compression_ratio", "no_speech_prob", "temperature", "vad_audio_s", "error_type"},
    "chunks": {"idx", "audio_s", "decode_ms", "rtf", "outlier", "retries", "ok"},
    "config": {"model", "device", "compute_type", "beam_size", "vad_filter", "language", "chunk_s"},
    "tts": {"predicted_ms", "actual_ms", "chars", "voice", "backend", "synth_ms", "play_ms"},
}
```

In `build_record()`, initialize defaults for every new key:
```python
# ANALOG: voicemode_telemetry.py:190-245
def build_record(*, run_id, install_id, ts_start, ts_end, outcome, error_stage=None,
                 actual=None, audio_s=0.0, chars_out=0, chars_typed=0,
                 fallback_used=False, insert_ok=False, segments=None, config=None,
                 backend=None, tts=None, source="stt",
                 outlier=False, outlier_reason=None, corpus_file=None,
                 cold_load=False, failed_chunks=None, chunks=None, **kwargs) -> dict:
    ...
    record["outlier"] = bool(outlier)
    record["outlier_reason"] = str(outlier_reason) if outlier_reason is not None else None
    record["corpus_file"] = str(corpus_file) if corpus_file is not None else None
    record["cold_load"] = bool(cold_load)
    record["failed_chunks"] = list(failed_chunks) if failed_chunks is not None else []
    record["chunks"] = list(chunks) if chunks is not None else []
    ...
```

#### Pattern 3: Outlier Classification (`classify_outlier()`)
Pure function evaluating RTF and tail decode duration:
```python
def classify_outlier(audio_s: float, decode_ms: float) -> tuple[bool, Optional[str]]:
    rtf_thresh = float(os.getenv("VOICEMODE_OUTLIER_RTF_THRESHOLD", "1.0"))
    tail_thresh_s = float(os.getenv("VOICEMODE_OUTLIER_TAIL_S", "10.0"))
    
    decode_s = (decode_ms or 0.0) / 1000.0
    rtf = (decode_s / audio_s) if (audio_s and audio_s > 0) else 0.0
    
    if rtf > rtf_thresh:
        return True, "rtf_exceeded"
    elif decode_s > tail_thresh_s:
        return True, "tail_decode"
    return False, None
```

#### Pattern 4: Diagnostic Corpus Capture with Atomic Placement (`save_diagnostic_corpus()`)
Follows `atomic_write_text()` temporary file and `os.replace()` pattern:
```python
# ANALOG: voicemode_telemetry.py:319-338
def save_diagnostic_corpus(
    audio_source: Any,
    run_id: str,
    reason: str,
    sample_rate: int = 16000,
) -> Optional[str]:
    """Saves raw 16kHz mono WAV to corpus dir using atomic .tmp_ placement. Returns relative path."""
    corpus_dir = get_corpus_dir()
    
    # 1. Free-space guard (> 1 GB required)
    try:
        free_bytes = shutil.disk_usage(corpus_dir).free
        if free_bytes < 1_000_000_000:
            return None
    except OSError:
        return None

    # 2. Prune FIFO limits before writing
    prune_corpus_if_needed(corpus_dir)

    # 3. Target filename (relative path contract: corpus/{filename})
    ts_str = time.strftime("%Y%m%d_%H%M%S")
    clean_reason = re.sub(r"[^a-zA-Z0-9_]", "_", reason)
    filename = f"{run_id}_{ts_str}_{clean_reason}.wav"
    target_path = corpus_dir / filename
    tmp_path = corpus_dir / f".tmp_{filename}"

    try:
        if isinstance(audio_source, (str, Path)) and Path(audio_source).exists():
            # Exact bit-for-bit file copy
            shutil.copyfile(str(audio_source), str(tmp_path))
        else:
            # In-memory PCM / numpy array export
            import wave
            import numpy as np
            pcm = (np.clip(audio_source, -1.0, 1.0) * 32767.0).astype(np.int16)
            with wave.open(str(tmp_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(pcm.tobytes())

        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, target_path)
        return f"corpus/{filename}"
    except OSError:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        return None
```

#### Pattern 5: Bounded FIFO Corpus Retention & Purge (`prune_corpus_if_needed()`, `purge_corpus()`)
```python
MAX_CORPUS_FILES = 50
MAX_CORPUS_BYTES = 100 * 1024 * 1024  # 100 MB
CORPUS_GRACE_PERIOD_S = 60.0

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

    files.sort(key=lambda x: x[0])  # Oldest mtime first
    pruned_count = 0
    for mtime, size, path in files:
        if (now - mtime) < CORPUS_GRACE_PERIOD_S and (len(files) - pruned_count) <= (MAX_CORPUS_FILES + 5):
            continue
        try:
            path.unlink()
            pruned_count += 1
            total_bytes -= size
            if (len(files) - pruned_count) <= MAX_CORPUS_FILES and total_bytes <= MAX_CORPUS_BYTES:
                break
        except OSError:
            pass
    return pruned_count

def purge_corpus(corpus_dir: Optional[Path] = None) -> tuple[int, int]:
    """Deletes all captured diagnostic audio files. Returns (count, bytes_reclaimed)."""
    if corpus_dir is None:
        corpus_dir = get_corpus_dir()
    if not corpus_dir.is_dir():
        return 0, 0
    count, total_bytes = 0, 0
    try:
        for entry in os.scandir(corpus_dir):
            if entry.name.endswith(".wav") or entry.name.startswith(".tmp_"):
                try:
                    size = entry.stat().st_size
                    Path(entry.path).unlink()
                    count += 1
                    total_bytes += size
                except OSError:
                    pass
    except OSError:
        pass
    return count, total_bytes
```

#### Pattern 6: Resilient Non-Fatal Writes on Hostile Filesystems (`append_ledger_row()`, `publish_status()`)
Wrap writing in `try ... except OSError:` catching `ENOSPC`, `EROFS`, `EACCES` so speech dictation never aborts on full or read-only disk:
```python
# ANALOG: voicemode_telemetry.py:346-375
def append_ledger_row(record: dict) -> bool:
    if not get_metrics_enabled():
        return False
    try:
        validate_record(record)
    except Exception:
        raise
    try:
        path = get_ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Rotation logic ...
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=True, sort_keys=True) + "\n"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except OSError:
        # Gracefully degrade on ENOSPC / EROFS / EACCES
        return False
```

---

## File 2: `voicemode_report.py` (Reporting & SVG Visualization) — MODIFY

**Path:** `/home/pera/github_repo/Voice/voicemode_report.py`  
**Role:** Statistics aggregation, drift % tracking, stratified clip duration metrics, outlier markers in SVG plots, "Outlier Runs" filter card, and CLI table output.  
**Data flow:** Ledger JSONL lines → `filter_records(..., outliers=True)` → `compute_report_metrics()` → `render_html_report()` / `render_terminal_summary()`.

### Analog: Self (`voicemode_report.py`)

#### Pattern 1: Multi-Criteria Filtering with Outliers Flag (`filter_records()`)
Extend `filter_records()` with `outliers: bool = False`:

```python
# ANALOG: voicemode_report.py:143-185
def filter_records(
    records: list[dict],
    since: Optional[str] = None,
    last: Optional[int | str] = 200,
    model: Optional[str] = None,
    device: Optional[str] = None,
    outliers: bool = False,
) -> list[dict]:
    filtered = list(records)
    ...
    if outliers:
        filtered = [
            r for r in filtered
            if bool(r.get("outlier")) or (
                voicemode_telemetry.classify_outlier(
                    r.get("audio_s", 0.0),
                    (r.get("actual") or {}).get("decode_ms", 0.0)
                )[0]
            )
        ]
    return filtered
```

#### Pattern 2: Statistics Aggregation with Drift & Stratified Duration Buckets (`compute_report_metrics()`)
Calculate:
1. `outlier_count` and `outlier_rate` (outliers / total runs).
2. `drift_pct`: comparison of median wait latency in the most recent 20 runs vs lifetime baseline:
   $$\text{drift\_pct} = \frac{\text{median}(\text{recent}_{20}) - \text{median}(\text{lifetime})}{\text{median}(\text{lifetime})} \times 100$$
3. Stratified clip durations: Short (<5s), Medium (5–30s), Long (>30s) duration buckets with count, median RTF, and median wait:

```python
# ANALOG: voicemode_report.py:221-293
def compute_report_metrics(records: list[dict]) -> dict:
    ...
    # Stratified Duration Buckets (ACC-06)
    buckets = {"short": [], "medium": [], "long": []}
    for r in records:
        aud, wait, rtf = extract_run_latency(r)
        if aud > 0:
            if aud < 5.0:
                buckets["short"].append((aud, wait, rtf))
            elif aud <= 30.0:
                buckets["medium"].append((aud, wait, rtf))
            else:
                buckets["long"].append((aud, wait, rtf))

    stratified = {}
    for b_key, b_items in buckets.items():
        waits = [w for _, w, _ in b_items if w > 0]
        rtfs = [r for _, _, r in b_items if r > 0]
        stratified[b_key] = {
            "count": len(b_items),
            "median_wait_s": round(statistics.median(waits), 3) if waits else None,
            "median_rtf": round(statistics.median(rtfs), 3) if rtfs else None,
        }

    # Drift percentage: recent 20 vs lifetime (D-22, ACC-02)
    drift_pct = None
    if len(wait_latencies) >= 5:
        lifetime_med = statistics.median(wait_latencies)
        recent_waits = [extract_run_latency(r)[1] for r in records[-20:] if extract_run_latency(r)[1] > 0]
        if recent_waits and lifetime_med > 0:
            recent_med = statistics.median(recent_waits)
            drift_pct = round(((recent_med - lifetime_med) / lifetime_med) * 100.0, 1)

    return {
        "total_runs": total_runs,
        "median_wait_s": median_wait_s,
        "p90_latency_s": p90_latency_s,
        "mean_rtf": mean_rtf,
        "outlier_count": outlier_count,
        "outlier_rate": round(outlier_count / total_runs, 3) if total_runs > 0 else 0.0,
        "drift_pct": drift_pct,
        "stratified": stratified,
        "stage_medians": stage_medians,
        "stage_p90s": stage_p90s,
        "last_run_timestamp": last_ts,
    }
```

#### Pattern 3: SVG Chart Outlier Markers (`#f43f5e` Hollow Diamonds / Crosses)
In `render_latency_scatter_svg()` and `render_rtf_trend_svg()`, render normal points as Sky blue circles and outliers as Crimson `#f43f5e` diamond markers (`<polygon>`):

```python
# ANALOG: voicemode_report.py:489-496
COLOR_OUTLIER = "#f43f5e"  # Crimson

for aud, wait, rid, is_outlier, reason in valid_pts:
    cx = pad_l + (min(aud, max_x) / max_x) * plot_w
    cy = pad_t + plot_h - (min(wait, max_y) / max_y) * plot_h
    if is_outlier:
        # Hollow diamond marker with Crimson stroke
        d_size = 5.0
        pts = f"{cx:.1f},{cy - d_size:.1f} {cx + d_size:.1f},{cy:.1f} {cx:.1f},{cy + d_size:.1f} {cx - d_size:.1f},{cy:.1f}"
        elements.append(
            f'<polygon points="{pts}" fill="none" stroke="{COLOR_OUTLIER}" stroke-width="2" class="chart-outlier">'
            f'<title>Run {html.escape(rid)} [OUTLIER: {html.escape(reason or "RTF/Tail")}]: Audio {aud:.1f}s, Wait {wait:.2f}s</title>'
            f'</polygon>'
        )
    else:
        elements.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="#38bdf8" opacity="0.85" class="chart-dot">'
            f'<title>Run {html.escape(rid)}: Audio {aud:.1f}s, Wait {wait:.2f}s</title>'
            f'</circle>'
        )
```

#### Pattern 4: Terminal Summary Table Outlier Pill (`render_terminal_summary()`)
Display `[OUTLIER]` tag and prune audio indicators:

```python
# ANALOG: voicemode_report.py:447-450
is_outlier = bool(r.get("outlier"))
status_str = f"{outcome} [OUTLIER]" if is_outlier else outcome
corpus_file = r.get("corpus_file")
if corpus_file:
    # Check if file still exists on disk
    full_path = voicemode_telemetry.get_metrics_dir().parent / "voice-stt" / corpus_file
    audio_tag = "[audio: wav]" if full_path.exists() else "[audio: pruned]"
```

---

## File 3: `voice.py` (Core Engine, Hardware Probing & Doctor) — MODIFY

**Path:** `/home/pera/github_repo/Voice/voice.py`  
**Role:** Main CLI router, guarded hardware probe, in-memory array fallback on disk full, 16kHz resampling, low-RAM thread clamping, doctor diagnostics suite, and finalizer integration.  
**Data flow:** CLI args → hardware check / background loop → `Recorder` → `transcribe_timed()` → `finalize_background_run()` → typing injection.

### Analog: Self (`voice.py`)

#### Pattern 1: Guarded Hardware Backend Probing (`probe_hardware_backend()`)
Safe probe checking CPU vector extensions without instantiating models, and querying CUDA devices with strict 1.0s timeout:

```python
# ANALOG: voice.py:3140-3178 (Doctor probes pattern)
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

    # 2. CUDA Device Count (ctranslate2 query without model init)
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

    # 3. ROCm & Intel check
    result["rocm"] = os.path.exists("/dev/kfd")
    result["intel_gpu"] = os.path.exists("/dev/dri")
    return result
```

#### Pattern 2: Doctor Diagnostics Extension (`run_doctor()`)
Extend `run_doctor()` to:
1. Audit path permissions (runtime dir 0700, state dir 0700, corpus dir 0700, `metrics.jsonl` 0600) and disk free space (> 1 GB).
2. Render Telemetry Diagnostics Card (n, median wait, p90, mean RTF, outlier count/rate, drift %, last run timestamp).
3. Render Hardware Backend Card (CPU vector flags, discrete GPUs, default backend `cpu, int8`).
4. Output structured JSON contract on `--json` with `"telemetry"`, `"hardware"`, and `"paths"` keys.
5. Pre-render `report.html` onboarding state on 0 runs if it does not already exist.
6. Enforce exit code 0 for advisory warnings (telemetry defects, low disk space); exit code 1 strictly for fatal STT breaks.

```python
# ANALOG: voice.py:3181-3241
# JSON Output Contract:
if getattr(args, "json", False) or getattr(args, "json_verify", False):
    report = {
        "status": "pass" if overall_ok else "fail",
        "critical_failures": critical_failures,
        "binaries": binary_results,
        "audio": audio_result,
        "models": model_results,
        "keybinds": kb_result,
        "daemons": daemon_results,
        "telemetry": telemetry_metrics,
        "hardware": hw_info,
        "paths": path_audit_results,
    }
    print(json_lib.dumps(report, indent=2))
    return 0 if overall_ok else 1
```

#### Pattern 3: Audio Resampling & In-Memory Array Fallback on Full Disk (`Recorder`)
Handle non-16kHz audio input transparently using `resample_pcm()`.
When `_write_chunk_file()` catches `OSError` (e.g. `ENOSPC`), keep audio array in-memory as a float32 numpy array:

```python
# ANALOG: voice.py:192-214
def _write_chunk_file(self, audio, idx: int, save_dir: Optional[Path]) -> tuple[Any, float]:
    import numpy as np
    audio_s = round(len(audio) / float(self.actual_sample_rate or self.target_sample_rate), 3)
    if self.actual_sample_rate != self.target_sample_rate:
        audio = resample_pcm(audio, self.actual_sample_rate, self.target_sample_rate)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)

    try:
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
            wav_path = save_dir / f"voice-{self._session_id}-seg{idx:02d}.wav"
        else:
            temp = tempfile.NamedTemporaryFile(prefix=f"voice-{self._session_id}-seg{idx:02d}-", suffix=".wav", delete=False)
            wav_path = Path(temp.name)
            temp.close()

        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.target_sample_rate)
            wav.writeframes(pcm.tobytes())
        return wav_path, audio_s
    except OSError as e:
        # Full disk / read-only fallback: return raw float32 array in memory
        print(f"Warning: disk write failed ({e}), falling back to in-memory audio array", file=sys.stderr)
        audio_float = pcm.astype(np.float32) / 32768.0
        return audio_float, audio_s
```

#### Pattern 4: Low-RAM Thread Clamping (`load_model()`)
Clamp CPU inference threads to `min(4, os.cpu_count() or 4)` to prevent memory exhaustion on 4 GB RAM systems:

```python
# ANALOG: voice.py:671-685
def load_model(args: argparse.Namespace, *, force_cpu: bool = False) -> ModelState:
    from faster_whisper import WhisperModel

    device = "cpu" if force_cpu else args.device
    compute_type = "int8" if force_cpu and args.compute_type == "auto" else args.compute_type
    cpu_threads = min(4, os.cpu_count() or 4)
    print(f"Loading faster-whisper {args.model!r} on {device} ({compute_type}, {cpu_threads} threads)...", flush=True)
    model = WhisperModel(
        args.model,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        local_files_only=not args.allow_download,
    )
    state = ModelState(model=model, requested_device=device, requested_compute_type=compute_type)
    return state
```

#### Pattern 5: In-Memory Array Transcription (`transcribe_timed()`)
Accept `audio_input: Union[Path, str, np.ndarray]` and pass numpy array directly to `WhisperModel.transcribe()`:

```python
# ANALOG: voice.py:706-735
def transcribe_timed(
    model_state: ModelState,
    audio_input: Union[Path, str, np.ndarray],
    args: argparse.Namespace,
    *,
    initial_prompt: Optional[str] = None,
    audio_s: Optional[float] = None,
    on_segment_yield: Optional[Callable[[float, float, float], None]] = None,
) -> TranscriptionEvidence:
    ...
    def _decode(state: ModelState):
        t0 = time.monotonic()
        input_data = str(audio_input) if isinstance(audio_input, (Path, str)) else audio_input
        raw_segments, info = state.model.transcribe(input_data, **kwargs)
        ...
```

#### Pattern 6: Run Finalization with Outlier Detection, Opt-In Corpus Saving & `gc.collect()` (`finalize_background_run()`)
```python
# ANALOG: voice.py:1242-1271
# 1. Outlier detection
is_outlier, outlier_reason = voicemode_telemetry.classify_outlier(audio_s, decode_ms_total)

# 2. Cold-load detection
cold_load = voicemode_telemetry.check_and_mark_boot_session()

# 3. Opt-in diagnostic corpus capture
corpus_file = None
capture_mode = getattr(args, "capture_corpus", None) or os.getenv("VOICEMODE_CORPUS_CAPTURE", "none").lower()
if capture_mode == "all" or (capture_mode == "outliers" and is_outlier):
    corpus_file = voicemode_telemetry.save_diagnostic_corpus(
        audio_source=full_audio_wav_or_array,
        run_id=run_id,
        reason=outlier_reason or "manual_capture",
    )

# 4. Memory reclamation
import gc
gc.collect()
```

#### Pattern 7: CLI Argument Parsing (`parse_args()`)
```python
# ANALOG: voice.py:3770-3782
parser.add_argument("--outliers", action="store_true", help="Filter report strictly to outlier runs.")
parser.add_argument(
    "--capture-corpus",
    nargs="?",
    const="outliers",
    choices=("none", "outliers", "all"),
    help="Capture diagnostic audio corpus (default: outliers when flag is specified).",
)
parser.add_argument(
    "--purge-corpus",
    action="store_true",
    help="Permanently delete all captured diagnostic corpus audio files and exit.",
)
```

---

## File 4: `tests/test_durability.py` (Automated Durability Test Suite) — CREATE

**Path:** `/home/pera/github_repo/Voice/tests/test_durability.py`  
**Role:** Automated pytest/unittest suite verifying degraded execution resilience and portability across hostile environments (ACC-01, ACC-04).  
**Data flow:** Mocks/fixtures simulating hostile OS conditions → invoke voicemode components → assert core STT typing completes and degraded fallbacks activate.

### Analog: `tests/_hermetic.py` & `tests/test_telemetry.py`

#### Pattern 1: Test Suite Setup & Hermetic Isolation
Inherit from `TempXdgTestCase` to guarantee test isolation:

```python
# ANALOG: tests/_hermetic.py:19-54
from _hermetic import TempXdgTestCase, advancing_monotonic
import voice
import voicemode_telemetry
import voicemode_report
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import numpy as np

class TestDurabilityPortability(TempXdgTestCase):
    ...
```

#### Pattern 2: Testing Non-Standard UID and Unset `XDG_RUNTIME_DIR` (Condition 1 & 2)
```python
def test_unset_xdg_runtime_dir_fallback(self):
    with patch.dict(os.environ, {}, clear=True):
        state_dir = voicemode_telemetry.get_state_dir()
        self.assertTrue(str(state_dir).startswith(f"/tmp/voice-stt-{os.getuid()}"))
        self.assertTrue(state_dir.exists())
        self.assertEqual(oct(state_dir.stat().st_mode)[-3:], "700")
```

#### Pattern 3: Testing Read-Only State Directory & Disk Full Handling (Condition 3 & 4)
```python
def test_readonly_state_dir_degraded_typing_succeeds(self):
    """Core transcription and typing must succeed even if metrics/status writes fail due to EROFS/EACCES."""
    args = voice.parse_args([])
    args.no_beep = True
    args.no_notify = True
    
    # Simulate read-only filesystem by making append_ledger_row fail with OSError(EROFS)
    with patch("voicemode_telemetry.append_ledger_row", side_effect=OSError(30, "Read-only file system")), \
         patch("voicemode_telemetry.publish_status", side_effect=OSError(30, "Read-only file system")), \
         patch("voice.insert_text", return_value=True) as mock_insert:
        # Run execution pipeline
        ...
        self.assertTrue(mock_insert.called)

def test_disk_full_inmemory_numpy_array_fallback(self):
    """When creating temporary WAV files fails with ENOSPC, Recorder returns numpy array and transcribe_timed accepts it."""
    recorder = voice.Recorder()
    pcm_audio = np.zeros(16000, dtype=np.float32)
    with patch("wave.open", side_effect=OSError(28, "No space left on device")):
        audio_output, audio_s = recorder._write_chunk_file(pcm_audio, 1, None)
        self.assertIsInstance(audio_output, np.ndarray)
        self.assertEqual(audio_s, 1.0)
```

#### Pattern 4: Testing Audio Sample Rate Resampling (Condition 5)
```python
def test_sample_rate_resampling_44100_to_16000(self):
    pcm_44k = np.ones(44100, dtype=np.float32)
    resampled = voice.resample_pcm(pcm_44k, orig_sr=44100, target_sr=16000)
    self.assertEqual(len(resampled), 16000)
```

#### Pattern 5: Testing Low-RAM Guarding (Condition 6)
```python
def test_load_model_clamps_cpu_threads_to_four(self):
    args = voice.parse_args([])
    with patch("os.cpu_count", return_value=32), \
         patch("faster_whisper.WhisperModel") as mock_whisper:
        voice.load_model(args, force_cpu=True)
        _, kwargs = mock_whisper.call_args
        self.assertEqual(kwargs.get("cpu_threads"), 4)
```

#### Pattern 6: Testing Cold Boot Session Marker (Condition 7)
```python
def test_cold_boot_session_marker(self):
    # First check on fresh state_dir returns True (cold)
    self.assertTrue(voicemode_telemetry.check_and_mark_boot_session())
    # Second check in same session returns False (warm)
    self.assertFalse(voicemode_telemetry.check_and_mark_boot_session())
```

#### Pattern 7: Testing Corpus Capture, FIFO Quotas & `--purge-corpus` (ACC-01)
```python
def test_corpus_fifo_eviction_and_purge(self):
    corpus_dir = voicemode_telemetry.get_corpus_dir()
    # Create 55 fake corpus files
    for i in range(55):
        f = corpus_dir / f"run_{i:02d}.wav"
        f.write_bytes(b"RIFF" + b"\x00" * 1000)
        os.utime(f, (time.time() - 100 + i, time.time() - 100 + i))
        
    pruned = voicemode_telemetry.prune_corpus_if_needed(corpus_dir)
    self.assertGreaterEqual(pruned, 5)
    remaining = [p for p in corpus_dir.glob("*.wav") if not p.name.startswith(".tmp_")]
    self.assertLessEqual(len(remaining), 50)
    
    # Test purge
    count, reclaimed = voicemode_telemetry.purge_corpus(corpus_dir)
    self.assertEqual(count, len(remaining))
    self.assertEqual(len(list(corpus_dir.glob("*.wav"))), 0)
```

---

## File 5: `tests/test_telemetry.py` (Schema & Privacy Suite) — MODIFY

**Path:** `/home/pera/github_repo/Voice/tests/test_telemetry.py`  
**Role:** Verification of Schema v1 keys, privacy allowlist, relative corpus path enforcement, and outlier helper functions.  
**Data flow:** Test assertions on `build_record()`, `validate_record()`, and file persistence.

### Analog: Self (`tests/test_telemetry.py`)

#### Pattern 1: Schema v1 Top-Level Key Validation
Ensure `SCHEMA_V1_KEYS` match record keys exactly:

```python
# ANALOG: tests/test_telemetry.py:101-115
class TestSchemaV1(TempXdgTestCase):
    def test_every_top_level_key_present(self):
        r = t.build_record(
            run_id='r1', install_id=t.get_install_id(), ts_start=1.0, ts_end=2.0,
            outcome='success', audio_s=1.0, chars_out=10, chars_typed=9,
            config={'model': 'm', 'device': 'cpu', 'compute_type': 'int8',
                    'beam_size': 1, 'vad_filter': True, 'language': 'en', 'chunk_s': 180.0},
            backend='cpu, int8', segments=[],
            outlier=False, outlier_reason=None, corpus_file="corpus/r1_rtf.wav",
            cold_load=False, failed_chunks=[], chunks=[],
        )
        self.assertEqual(set(r.keys()), set(t.SCHEMA_V1_KEYS))
        self.assertEqual(r['outlier'], False)
        self.assertIsNone(r['outlier_reason'])
        self.assertEqual(r['corpus_file'], "corpus/r1_rtf.wav")
```

#### Pattern 2: Privacy Allowlist & Relative Corpus Path Enforcement
Verify that `corpus_file` strictly allows relative paths (`corpus/{filename}`) and rejects absolute `/home/` paths:

```python
# ANALOG: tests/test_telemetry.py:129-151
def test_corpus_file_relative_path_privacy(self):
    r = t.build_record(
        run_id='r1', install_id=t.get_install_id(), ts_start=1.0, ts_end=2.0,
        outcome='success', corpus_file="corpus/r1_audio.wav"
    )
    line = json.dumps(r)
    # Ensure no absolute paths are leaked
    for pat in [r'/home/', r'/tmp/', r'/usr/', r'/etc/']:
        self.assertIsNone(re.search(pat, line))
```

---

## File 6: `tests/test_report.py` (Report & SVG Visualizations) — MODIFY

**Path:** `/home/pera/github_repo/Voice/tests/test_report.py`  
**Role:** Verification of report calculations, drift % formula, stratified duration buckets, SVG Crimson outlier styling, and `--outliers` CLI flag.

### Analog: Self (`tests/test_report.py`)

#### Pattern 1: Extending `_make_record()` Mock Helper
Update `_make_record()` to supply `outlier`, `outlier_reason`, and `corpus_file`:

```python
# ANALOG: tests/test_report.py:26-85
def _make_record(
    run_id="run-1",
    audio_s=4.0,
    actual_s=2.4,
    load_ms=200.0,
    decode_ms=2100.0,
    finalize_ms=50.0,
    insert_ms=50.0,
    model="medium",
    device="cpu",
    outcome="success",
    ts_start=None,
    outlier=False,
    outlier_reason=None,
    corpus_file=None,
):
    ...
```

#### Pattern 2: Testing `--outliers` Filtering and Stratified Duration Metrics
```python
def test_filter_records_by_outliers(self):
    r1 = _make_record(run_id="r1", audio_s=2.0, decode_ms=1000.0, outlier=False)
    r2 = _make_record(run_id="r2", audio_s=2.0, decode_ms=3000.0, outlier=True, outlier_reason="rtf_exceeded")
    filtered = voicemode_report.filter_records([r1, r2], outliers=True)
    self.assertEqual(len(filtered), 1)
    self.assertEqual(filtered[0]["run_id"], "r2")

def test_drift_percentage_calculation(self):
    # Create 30 records with an upward latency shift in recent runs
    records = [_make_record(run_id=f"r{i}", actual_s=1.0) for i in range(20)]
    records.extend([_make_record(run_id=f"r{i}", actual_s=2.0) for i in range(20, 30)])
    metrics = voicemode_report.compute_report_metrics(records)
    self.assertIsNotNone(metrics["drift_pct"])
    self.assertGreater(metrics["drift_pct"], 0.0)
```

#### Pattern 3: Testing SVG Outlier Markers (`#f43f5e`)
```python
def test_render_latency_scatter_outlier_crimson_markers(self):
    r = _make_record(run_id="out1", audio_s=2.0, decode_ms=4000.0, outlier=True, outlier_reason="rtf_exceeded")
    svg = voicemode_report.render_latency_scatter_svg([r], {})
    self.assertIn("#f43f5e", svg)
    self.assertIn("chart-outlier", svg)
```

---

## File 7: `tests/test_verification_doctor.py` (Doctor & Diagnostics Suite) — MODIFY

**Path:** `/home/pera/github_repo/Voice/tests/test_verification_doctor.py`  
**Role:** Tests for `probe_hardware_backend()`, telemetry card rendering, filesystem permission audits, and `--json` format output.

### Analog: Self (`tests/test_verification_doctor.py`)

#### Pattern 1: Testing Hardware Backend Probing (`probe_hardware_backend()`)
```python
# ANALOG: tests/test_verification_doctor.py:77-112
def test_probe_hardware_backend_cpu_and_cuda_mocked(self):
    with patch("ctranslate2.get_cuda_device_count", return_value=1), \
         patch("shutil.which", return_value="/usr/bin/nvidia-smi"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="NVIDIA GeForce RTX 3060\n")
        hw = voice.probe_hardware_backend()
        self.assertEqual(hw["cuda_devices"], 1)
        self.assertEqual(hw["cuda_name"], "NVIDIA GeForce RTX 3060")
        self.assertEqual(hw["default_backend"], "cpu, int8")
```

#### Pattern 2: Testing Doctor JSON Contract with `"telemetry"` and `"hardware"` Keys
```python
def test_run_doctor_json_contains_telemetry_and_hardware(self):
    args = voice.parse_args(["--doctor", "--json"])
    with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
        ret = voice.run_doctor(args)
        self.assertEqual(ret, 0)
        data = json.loads(mock_out.getvalue())
        self.assertIn("telemetry", data)
        self.assertIn("hardware", data)
        self.assertIn("paths", data)
        self.assertEqual(data["hardware"]["default_backend"], "cpu, int8")
```

---

## File 8: `docs/telemetry.md` (Telemetry & Schema Documentation) — MODIFY

**Path:** `/home/pera/github_repo/Voice/docs/telemetry.md`  
**Role:** Technical design specification of telemetry Schema v1, outlier thresholds, diagnostic corpus capture, degraded execution, and latency evaluation protocol.

### Analog: Self (`docs/telemetry.md`)

#### Content Patterns to Extend:
1. **Schema v1 Table:** Add `outlier`, `outlier_reason`, `corpus_file`, `cold_load`, `failed_chunks`, `chunks` to the field table.
2. **Outlier Detection Criteria:** Document `RTF > 1.0` or `tail_decode_s > 10.0s`, configurable via `VOICEMODE_OUTLIER_RTF_THRESHOLD` and `VOICEMODE_OUTLIER_TAIL_S`.
3. **Opt-in Diagnostic Corpus:** Document default `none`, modes `outliers` and `all`, local directory `$XDG_STATE_HOME/voice-stt/corpus/` (0700/0600), FIFO caps (50 files / 100 MB), 1 GB free-space gate, and `voice --purge-corpus`.
4. **Degraded Execution Policies:** Document `/tmp/voice-stt-$UID/` fallback, in-memory array transcription during full disk (`ENOSPC`), 44.1 kHz auto-resampling, and 4 GB RAM thread clamping.
5. **Evaluation Protocol (ACC-06):** Stratified duration benchmarks: Short (<5s), Medium (5–30s), Long (>30s) on Intel Alder Lake CPU int8 (median RTF ≤ 0.35, outlier share ≤ 5% over 20 reference runs).

---

## File 9: `README.md` (Top-Level Documentation) — MODIFY

**Path:** `/home/pera/github_repo/Voice/README.md`  
**Role:** User guide and quick reference for CLI flags, doctor capabilities, and environment variables.

### Analog: Self (`README.md`)

#### Content Patterns to Extend:
1. **At a Glance Table:**
   - `voice --report --outliers`: Filter latency report specifically to outlier runs.
   - `voice --purge-corpus`: Purge all captured diagnostic audio files and reclaim disk space.
2. **CLI Command Reference:** Add descriptions and examples for `--report --outliers`, `--capture-corpus`, `--purge-corpus`, and expanded `--doctor`.
3. **Environment Variables Table:** Add `VOICEMODE_OUTLIER_RTF_THRESHOLD`, `VOICEMODE_OUTLIER_TAIL_S`, and `VOICEMODE_CORPUS_CAPTURE`.

---

## Architecture Conventions & Implementation Rules

### 1. Focus Safety
- Keystroke typing via `wtype` requires that the active window retains focus.
- **Rule:** Never emit desktop notifications, audio beeps, or window interaction on outlier detection. Outliers are handled silently and surfaced only in reports and doctor.

### 2. Relative Corpus Path Contract
- Storing absolute paths like `/home/pera/...` violates privacy requirements and breaks test regex scanners.
- **Rule:** `corpus_file` in `metrics.jsonl` must ALWAYS be a relative path: `corpus/{filename}.wav`.

### 3. CPU int8 Execution Baseline
- Discrete GPUs (CUDA, ROCm) detected during `--doctor` or `probe_hardware_backend()` are reported purely informatively.
- **Rule:** Never auto-switch `--device` to GPU. Default execution remains strictly `cpu` with `int8` compute type on all hardware.

### 4. Non-Fatal Resilient Telemetry
- If disk is full (`ENOSPC`) or state directory is read-only (`EROFS`), dictation must succeed.
- **Rule:** Catch `OSError` around all logging, status publishing, and ledger appending; retain audio in-memory as numpy arrays if WAV file writes fail; ensure `wtype` keystroke typing completes without interruption.
