# Stack Research: v1.1 Latency Prediction & Telemetry

**Domain:** Desktop speech utility — single-file Python 3.12 app, per-dictation detached worker, PID state machine, Quickshell/QML status bar
**Researched:** 2026-10-26
**Confidence:** HIGH for stdlib/API choices and versions (all verified in the project venv and local Quickshell install); MEDIUM for hardware-probe portability (Intel verified locally, NVIDIA/AMD from documented interfaces); LOW for shipped predictor priors (seed values, replaced by per-machine calibration)

---

## Executive Recommendation

**Add zero Python dependencies.** Everything this milestone needs is in the Python 3.12 standard library plus APIs already installed: `json`, `os.replace`, `statistics`, `csv`, `html`, `string.Template`, `xml.sax.saxutils`, `wave`, `hashlib`, `importlib.metadata`, `fcntl.flock`, `resource`, `/proc`, `/sys`, and Quickshell 0.3.2's `FileView` + `JsonAdapter`.

Five concrete recommendations, in order of impact:

1. **Make the heavy imports lazy before adding anything else.** `sounddevice` and `faster_whisper` are imported at module top (`voice.py:40-42`). Measured on this machine: `import sounddevice` ≈ 250–320 ms, `from faster_whisper import WhisperModel` ≈ 245–260 ms, bare interpreter ≈ 76 ms. `--status`, `--report`, `--doctor`, `--toggle`, `--cancel`, and `--stop-tts` need neither. There are only 8 `sd.` call sites and 1 `WhisperModel` call site, and `from __future__ import annotations` is already present, so this is a mechanical refactor that removes ~0.5 s from every hotkey press and CLI query. This is a larger perceived-latency win than the entire ETA feature.
2. **One new in-repo module, not a package and not a dependency:** `voicemode_telemetry.py` (stdlib only, no numpy/sounddevice/faster_whisper import), as specified in `ARCHITECTURE.md`. `pyproject.toml` gains one `py-modules` entry. If the split is rejected, the same functions go at the end of `voice.py` — the design does not depend on the file boundary.
3. **Persistence: append-only JSONL + atomic-replace JSON.** One `os.write()` per run to a `O_APPEND` fd; `status.json` via `tempfile.mkstemp` in the same directory + `os.replace`. No SQLite, no ORM, no lock on the hot path, `fcntl.flock` only during rotation.
4. **Robust statistics from `statistics`**, not numpy: `median`, `median_low`, `quantiles(n=10)`, `linear_regression` (3.10+), plus ~15 lines of hand-rolled log-EWMA and MAD. Keep the telemetry module numpy-free so its imports stay in the tens of milliseconds (measured ~28 ms cumulative for the stdlib set) and tests run without audio/GPU.
5. **Charts as hand-written inline SVG** (~120 LOC) with `string.Template` for the HTML shell and `csv.writer` for export. Self-contained, deterministic, offline, no font embedding, no 40 MB wheel. Quickshell reads `status.json` with `FileView { watchChanges: true }` + `JsonAdapter` (both verified present in the installed 0.3.2), while the PID file stays the authority for state.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|---|---|---|---|
| Python | 3.12.12 (project `.venv`) | Runtime | Existing constraint; all chosen stdlib APIs exist here (`statistics.linear_regression` 3.10+, `datetime.UTC` 3.11+). Note `os.process_cpu_count` is 3.13-only — do not use it. |
| `time.perf_counter_ns` / `time.time_ns` | stdlib | Stage timing and timestamps | `perf_counter_ns` is monotonic and ns-resolution; `time_ns` is only for wall-clock fields (`ts`, `eta_epoch`). Never subtract `time.time()` values for durations. |
| `json` | stdlib | Ledger + status contract | `separators=(",", ":")`, `ensure_ascii=False`. No orjson (see NOT list). |
| `os.replace` + `tempfile.mkstemp` | stdlib | Atomic status writes | Same-directory rename is atomic for readers (`rename(2)`), so the 100 ms bar poll never sees a torn document. `path.write_text()` is not atomic. |
| `statistics` | stdlib | Robust central tendency, quantiles, fit | `median`, `median_low`, `quantiles(n=10)`, `linear_regression`, `fmean`. Raises `StatisticsError` on empty input — guard n=0. |
| `csv` | stdlib | CSV export | `lineterminator="\n"` for stable diffs; RFC 4180 quoting handled. |
| `html` + `string.Template` | stdlib | HTML escaping and shell | `html.escape(..., quote=True)`; `string.Template` avoids `str.format` conflicts with CSS braces. |
| `xml.sax.saxutils` | stdlib | SVG text/attribute escaping | `escape()` / `quoteattr()`; model names and paths must not break the SVG. |
| `wave` | stdlib | Exact audio seconds per segment | Already used by `Recorder._write_chunk_file`; `getnframes()/16000` is authoritative. `stop_to_wav()` returns *wall* duration (`voice.py:292`), which can differ. |
| `hashlib.blake2b(digest_size=8)` | stdlib | Config/hardware fingerprint | 16 hex chars, fast, no security requirement. Include an `fp_version` salt so field changes invalidate grouping. |
| `importlib.metadata.version` | stdlib | Record dependency versions | Verified: `faster-whisper 1.2.1`, `ctranslate2 4.8.2`, `numpy 2.5.3`, `sounddevice 0.5.6`. |
| `fcntl.flock` | stdlib | Rotation lock only | Single writer means appends need no lock; rotation (rename) does. Linux-only is acceptable for this project. |
| `resource.getrusage` | stdlib | Peak RSS per run | `ru_maxrss` is kB on Linux; cheap and stable. Complements the existing 2129 MB observation. |
| `os.getloadavg`, `os.sched_getaffinity` | stdlib | Noise covariates / usable CPUs | Load average at start/end lets the predictor exclude contended runs; `sched_getaffinity` respects taskset/cgroups unlike `os.cpu_count()`. |
| `/proc` + `/sys` | kernel | Hardware fingerprint | `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm/card*/device/*`, `/sys/devices/system/cpu/cpu0/cache/*`. No psutil. |
| `faster_whisper` introspection | 1.2.1 (existing) | Progress + decode truth | `info.duration`, `info.duration_after_vad`, `info.transcription_options`, `Segment.temperature/avg_logprob/compression_ratio/no_speech_prob`. |
| Quickshell `FileView` + `JsonAdapter` | 0.3.2 (installed, AUR git) | Status-bar contract | `watchChanges` + `onFileChanged: reload()`; source-verified to watch the parent directory and re-arm after atomic rename. |
| `unittest` | stdlib | Tests | Existing suite style; `tempfile.TemporaryDirectory` + injected clock/paths, no freezegun. |

### Supporting Libraries

**None new.** Explicitly:

| Need | Existing asset | When a new library would be justified |
|---|---|---|
| Statistics | `statistics` | Never for this data volume (≤20k floats). |
| Charts | Inline SVG | Only if print-quality raster output were required (it is not). |
| Hardware info | `/proc`, `/sys`, optional `nvidia-smi`/`rocm-smi` | Only if live GPU utilization/temperature were required (it is not). |
| HTTP/notifications | Existing `urllib.request`, `notify-send` | Never — the report is local. |

### Development Tools

| Tool | Purpose | Notes |
|---|---|---|
| `ruff` | Lint/format | Unchanged (`line-length = 120`, `target-version = "py312"`). Local imports inside functions are fine. |
| `pytest` | Runner over `unittest` classes | Unchanged; new tests are `tests/test_telemetry.py`. |
| `python -X importtime` | Enforce the import budget | Built-in; use it to prove `--status` no longer imports audio/ML. |
| `qs -c ii` / Quickshell log | Manual QML verification | External dotfiles; verify `fileChanged` fires on `os.replace`. |

### Files and Config Changes (not dependencies)

| File | Change | Why |
|---|---|---|
| `voicemode_telemetry.py` | **NEW**, stdlib-only | Schema v1, atomic writes, ledger I/O, predictor, report formatters, `RunTelemetry`. |
| `voice.py` | Instrument + lazy imports + CLI flags | Timing call sites, `--report` family, `--json` on `--status`. |
| `pyproject.toml` | `py-modules = ["voice", "voicemode_telemetry"]` | Package the new module. **No** `dependencies` change. |
| `docs/telemetry.md` | **NEW** | Schema contract, privacy, corpus opt-in and deletion. |
| `tests/test_telemetry.py` | **NEW** | Round-trip, atomicity, corrupt-line tolerance, predictor, formatters. |
| `~/.config/quickshell/ii/services/Voice.qml` | External | Add status `FileView`/`JsonAdapter`, ETA binding, click handling. |
| `~/.config/quickshell/ii/modules/ii/bar/VoicePill.qml` | External | ETA text, distinct color, click affordance. |

---

## Installation

**No installation step is added by this milestone.** The venv is unchanged; there is nothing new to fetch.

```bash
# Unchanged — no new runtime dependencies
uv sync                    # core (faster-whisper, numpy, PyYAML, sounddevice)
uv sync --extra kokoro     # optional local TTS
uv sync --extra edge       # optional online TTS

# After the pyproject edit, re-install the project itself so the new
# module is importable/packageable (no network fetch):
uv pip install -e .

# Verification (no audio hardware or GPU required):
python -X importtime -c "import voicemode_telemetry" 2>&1 | tail -1   # stdlib only: a few ms, no numpy/sd/fw
python -X importtime -c "import voice" 2>&1 | tail -1                 # must not import sounddevice or faster_whisper at top level
python -m unittest discover -s tests -v
voice --doctor        # prints resolved paths, telemetry status, hardware fingerprint
voice --report        # terminal summary from the existing ledger (never loads Whisper)
```

**System packages:** unchanged (`ffmpeg`/`ffplay`, `libportaudio2`, `wl-clipboard`/`xclip`, `xdg-utils` for `xdg-open`). `nvidia-smi` / `rocm-smi` are optional probes, never requirements — their absence is a normal, supported state.

---

## Integration Points (stack-level, line-mapped)

| # | Location | Change | Stack detail |
|---|---|---|---|
| 1 | `voice.py:40-42` | Lazy imports | Remove top-level `numpy`, `sounddevice`, `faster_whisper`; import inside `Recorder.start` (237), `play_tone` (566), `Recorder._write_chunk_file` (184), `--list-devices` branch (3125), and `load_model` (631). `from __future__ import annotations` already makes `sd.InputStream` / `WhisperModel` annotations strings. Tests never patch `voice.np`/`voice.sd` (verified), so mocks are unaffected. |
| 2 | `voice.py:44-72` | New paths | `STATUS_FILE = STATE_DIR / "status.json"`; `METRICS_DIR = Path(os.getenv("XDG_STATE_HOME", Path.home()/".local/state")) / "voicemode"`; `METRICS_FILE`, `REPORT_FILE`, `CORPUS_DIR`. Create with `mkdir(parents=True, exist_ok=True, mode=0o700)`. |
| 3 | `voice.py:277-337` | Segment audio truth | After `stop_to_wav()`, read each WAV's `getnframes()/getframerate()`; store `audio_s` per segment. Do not use the returned `duration` (wall clock) as audio content. |
| 4 | `voice.py:631-643` | Model-load timing | Wrap `load_model()` with `perf_counter_ns`; record `model_load_ms` and `actual_backend(model)` (`voice.py:621`). This is 2.2–3.0 s on this machine — always a separate ETA component. |
| 5 | `voice.py:646-680` | Per-segment progress | Keep the signature; add optional `on_progress: Callable[[float, float], None] \| None = None`. Restructure to `segments, info = model.transcribe(...)` then iterate: `info` is returned eagerly, so `info.duration` and `info.duration_after_vad` are available *before* the first decode. Call `on_progress(segment.end, info.duration)`. |
| 6 | `voice.py:666-680` | CPU fallback detection | Compare returned `ModelState.requested_device` with the run config; set `fallback=true` and re-key the predictor to CPU for remaining segments. |
| 7 | `voice.py:1168-1214` | Insert timing | Time `insert_text`; record `insert_ms` and success. ETA endpoint is "text begins inserting" (per FEATURES.md), so insertion is logged but outside the ETA. |
| 8 | `voice.py:1623-1658` | Hidden parent timestamp | Add `--invoked-at-monotonic-ns` (suppressed arg) so the worker can record `spawn_ms` (hotkey → worker up), including interpreter+import cost. `CLOCK_MONOTONIC` is system-wide and safely shared across processes. |
| 9 | `voice.py:1709-1865` | Worker instrumentation | Instantiate `RunTelemetry` at entry; write status at each transition; heartbeat every 5 s while recording; one ledger append in `finally:` after `remove_pid`. Wrap every telemetry call in `try/except`. |
| 10 | `voice.py:1991-1999` | `--status` | Print state + `eta_remaining_s` + phase + calibration source; add `--json` (repo convention from `--doctor`). Never import audio/ML here. |
| 11 | `voice.py:2884-3085` | CLI | `--report`, `--report-format {terminal,csv,html}`, `--report-since`, `--report-last`, `--report-out`, `--report-open`, `--capture-corpus`. Dispatch in `main()` (3088) before model work — but note this only avoids *work*, not imports; the startup win comes from item 1. |
| 12 | `Voice.qml:13-18, 54-67, 159-259` | Status consumption | Add `statusPath`, a `FileView` with `watchChanges`, `JsonAdapter` fields, ETA binding guarded by schema+pid+expiry. Keep PID-derived `overallState` as authority. |
| 13 | `VoicePill.qml:50-60, 104-112` | Display + click | `transcribing` shows ETA; enable the existing `inertMouseArea` only in `transcribing`/`typing`/`wrapup`; click → `Quickshell.execDetached(["xdg-open", reportPath])`. |

**Do not write `status.json` from the parent process** (`toggle_background_recording`, 1661-1706). Single writer = the worker; a second writer invites out-of-order phases.

---

## Verified APIs and Versions

| Claim | Evidence | Confidence |
|---|---|---|
| `WhisperModel.transcribe()` returns `(segments_generator, TranscriptionInfo)` and `info` is built eagerly | `faster_whisper/transcribe.py:1012-1022` (installed 1.2.1); `return segments, info` at 1022 | HIGH |
| VAD runs before `transcribe()` returns, so `duration_after_vad` is known immediately | `transcribe.py:884-893`; `duration_after_vad = audio.shape[0]/sampling_rate` | HIGH |
| A scalar `temperature=0.0` produces exactly one decode pass (disables fallback retries) | `transcribe.py:981-984` wraps scalar in a one-element list; fallback loop at 1432 iterates `options.temperatures` | HIGH |
| `Segment` exposes `temperature`, `avg_logprob`, `compression_ratio`, `no_speech_prob` (no text needed) | Dataclass fields at `transcribe.py:44-66` | HIGH |
| `info.transcription_options` contains `initial_prompt` / `hotwords` / `prefix` — i.e. **text** | `TranscriptionOptions` dataclass `transcribe.py:68-99` | HIGH (privacy trap) |
| Segment timestamps are restored to the original timeline when VAD is on | `restore_speech_timestamps()` at `transcribe.py:1844-1870` | HIGH — use `segment.end/info.duration` for progress, not `/duration_after_vad` |
| `ctranslate2.get_cuda_device_count()` fails soft (returned `0`) | Executed in project venv (ctranslate2 4.8.2) | HIGH |
| `ctranslate2.get_supported_compute_types("cuda")` raises `RuntimeError` on driver mismatch | Executed: `CUDA driver version is insufficient for CUDA runtime version` | HIGH — wrap it; never call from `--status` |
| Quickshell `FileView` has `watchChanges`, `fileChanged`, `reload()`, `atomicWrites` | `/usr/lib/qt6/qml/Quickshell/Io/quickshell-io.qmltypes:343-493`; docs v0.3.0 FileView page | HIGH |
| `FileView` watches the **parent directory** and re-adds the path, so `os.replace` still fires `fileChanged` | `src/io/fileview.cpp` v0.3.2 lines 493-546 (both `fileChanged` and `directoryChanged` connected; path re-added) | HIGH |
| `JsonAdapter` is the default property of `FileView` and maps declared typed properties to JSON keys | `quickshell-io.qmltypes:550`; docs JsonAdapter page | HIGH |
| Installed Quickshell is 0.3.2 with Qt 6.12.0 | `qs --version`, `qtpaths6 --qt-version` | HIGH |
| `statistics.linear_regression` / `quantiles` raise `StatisticsError` on empty/1-point input | Executed in venv (3.12.12) | HIGH |
| `os.sched_getaffinity(0)` = 20 here; `ru_maxrss` works | Executed | HIGH |

### Startup measurement (why item 1 matters)

| Command | Wall time |
|---|---|
| bare `python -c pass` | ~76 ms |
| `import sounddevice` | ~250–320 ms |
| `from faster_whisper import WhisperModel` | ~245–260 ms |
| `import numpy` | ~50–90 ms |
| `import voice` (current) | ~0.32–0.60 s (noisy under load) |

The milestone's 1.15 s `--status` figure is consistent with a cold page cache + busy machine. Removing `sounddevice` + `faster_whisper` from the import path is the reliable fix; import-order games in `main()` are not.

---

## Stack Patterns (implementation details)

### P1 — Stage timing (monotonic, integer ms)

```python
t0 = time.perf_counter_ns()
model_state = load_model(args)
model_load_ms = (time.perf_counter_ns() - t0) // 1_000_000
```

Use `perf_counter_ns` (not `time.time`) for all durations; use `time.time_ns()` only for `ts`, `started_at`, `eta_epoch`, `expires_at`. `time.monotonic()` already used by `Recorder.started_at` is the same Linux clock — do not mix it with `perf_counter_ns` in one subtraction.

### P2 — Atomic `status.json` (reader never tears)

```python
def write_status(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
            fh.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise
```

- Same directory = same filesystem = `rename(2)`, no `EXDEV`.
- **No `fsync` here.** Durability across power loss is irrelevant; readers see a complete file from page cache either way, and fsync at 5 s heartbeats is wasted I/O. (`metrics.jsonl` gets one fsync per run, not per event.)
- Serialize writes with a `threading.Lock` because the watchdog `Timer` thread (923-952) and the main thread can both write.
- Clean orphan `.status-*.tmp` older than 60 s at worker start.
- Write cadence: transitions + 5 s recording heartbeat + per segment + typing. Never 10 Hz.

### P3 — Append-only JSONL + bounded read + rotation

```python
line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
try:
    os.write(fd, line.encode("utf-8"))   # one write, no embedded newlines
    os.fsync(fd)                          # once per run
finally:
    os.close(fd)
```

- Readers: seek to `max(0, size - 1_000_000)`, drop a partial first line, `json.loads` per line, count and skip `ValueError`s. Never rewrite the file to "repair" it.
- Rotation is writer-only, under `fcntl.flock` on `metrics.jsonl.lock`: rename `.jsonl → .jsonl.1`, `.1 → .2`, delete `.2`, then append the new record. Rotate at ~5 MB (thousands of runs at ~1 KB/record).
- `O_APPEND` + single write makes a second writer safe in practice; do not add a lock to the append path.
- `run_id` = `time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]`.

### P4 — Robust statistics and the predictor (stdlib only)

```python
import statistics as st

def median_or_none(xs: list[float]) -> float | None:
    return st.median(xs) if xs else None

def mad(xs: list[float], med: float) -> float:
    return st.median([abs(x - med) for x in xs]) if xs else 0.0

def shrink(sample_med: float, prior: float, n: int, k: float = 2.0) -> float:
    """Pseudo-count shrinkage: 0 samples => prior, many samples => sample."""
    return (n * sample_med + k * prior) / (n + k)

def ewma_log(prev: float | None, rate: float, half_life: int = 20) -> float:
    alpha = 1.0 - 0.5 ** (1.0 / half_life)
    return math.log(rate) if prev is None else (1 - alpha) * prev + alpha * math.log(rate)
```

Rules that matter more than the estimator:

- **Rate = ratio of sums**, not mean of ratios: `sum(decode_ms) / max(sum(audio_after_vad_ms), 1)`. Short segments then cannot dominate.
- **Outlier gate before aggregation:** drop runs with `outcome != "ok"`, `fallback`, `timeout`, `load1 > 0.7 * usable_cpus`, or `rtf > 3 × median_rtf`. Keep them in the ledger — never delete evidence.
- **MAD confidence:** `mad/median < 0.15` and `n >= 5` ⇒ calibrated; `n` 1–4 ⇒ mixed; `n == 0` ⇒ prior.
- **Conservative quantile:** `st.quantiles(rates, n=10)[5]` is the 60th percentile (n=10 returns 9 cut points). Use `max(median, p60)`, cap the uplift at +15 % (`eta = min(eta_p60, eta_median * 1.15)`).
- **Model form:** `total_ms = spawn_ms + model_load_ms + finalize_ms + Σ(audio_after_vad_ms × rtf) + insert_ms`. Fit `audioms→ms` with `st.linear_regression(audio_s, total_s)` only for the report chart; ETA uses the stage model because the fixed cost (model load) is 2.2–3.0 s and cannot be folded into a single factor.
- Sanity check of the form against this machine (subtracting ~2.5 s load): 30 s→6.5 s decode (0.217), 60 s→13.9 (0.232), 115 s→28.3 (0.246), 180 s→43.4 (0.241). Near-linear with an intercept — do **not** add a quadratic term.

### P5 — Hardware probe (`/proc` + `/sys`, optional vendor tools)

| Signal | Primary source | Notes |
|---|---|---|
| CPU model | `/proc/cpuinfo`, first `model name` | Fallback `platform.processor()` / `"unknown"` |
| Physical cores | count unique `(physical id, core id)` pairs | Fallback `cpu cores`, then logical count (ARM/SBC) |
| Usable logical CPUs | `len(os.sched_getaffinity(0))` | Not `os.cpu_count()` (host-wide, ignores cgroups/taskset) |
| Max frequency / governor | `/sys/devices/system/cpu/cpu0/cpufreq/{scaling_max_freq,scaling_governor}` | Optional; absent in VMs |
| L3 cache | `/sys/devices/system/cpu/cpu0/cache/index*/{level,size}` where level=3 | Optional; useful prior feature |
| AVX support | `/proc/cpuinfo` `flags` → booleans `avx2`, `avx512f` | Store booleans, not the whole line |
| RAM | `/proc/meminfo` `MemTotal`, `MemAvailable` | kB; `MemAvailable` is a noise covariate, not identity |
| GPU (all) | `/sys/class/drm/card*/device/uevent` (`PCI_ID`, `DRIVER`) | Skip `card*-*` connector entries; 0x8086 Intel, 0x1002 AMD, 0x10de NVIDIA |
| GPU name | `lspci -mm -nn` filtered to class 0300/0302, if present | Optional; this machine: `Alder Lake-S GT1 [UHD Graphics 770]` |
| AMD/iGPU VRAM | `/sys/class/drm/card*/device/mem_info_vram_total` (and `lmem_total_bytes` for Intel dGPU) | Bytes; absent for Intel iGPU → `null` |
| NVIDIA name/VRAM | `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv,noheader,nounits` | `shutil.which` guard, `timeout=1.5`, `check=False` |
| NVIDIA fallback | `/proc/driver/nvidia/gpus/*/information` | Name only; no VRAM |
| AMD name | `rocm-smi --showproductname --json` | Only if vendor is 0x1002; `timeout=2` |
| CUDA present | `ctranslate2.get_cuda_device_count()` **in the worker** | Verified to return 0 here without raising; do not call `get_supported_compute_types("cuda")` |

Rules: probe once per worker run, wrapped in `try/except` per field; a probe failure yields `"unknown"`, never an exception. Spawn vendor tools only when sysfs says the vendor is present, after the first ETA/status write (there is a 2–3 s model-load window). Never probe from `--status`.

### P6 — Fingerprint (stable grouping key)

```python
FP_VERSION = 1

def fingerprint(hw: dict, cfg: dict) -> str:
    payload = json.dumps(
        {"v": FP_VERSION, "hw": hw, "cfg": cfg},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()
```

Include: CPU model, physical/logical cores, RAM MB, GPU vendor/name/VRAM, driver, model, device, compute_type, beam size, VAD flag, language, `cpu_threads`, faster-whisper/ctranslate2 versions. Exclude: load average, `MemAvailable`, current frequency, chunk seconds, run id. Changing the field set bumps `FP_VERSION`; old records stay readable but stop contributing to the new key.

### P7 — Self-contained HTML + SVG + CSV

```python
from string import Template

_HTML = Template("""<!doctype html>
<html><head><meta charset="utf-8"><title>voicemode latency</title>
<style>$css</style></head>
<body><h1>voicemode latency</h1>$summary$charts$table</body></html>""")

def _xy(v, lo, hi, out_lo, out_hi):
    span = (hi - lo) or 1.0
    return out_lo + (v - lo) / span * (out_hi - out_lo)

def line_chart(points, w=720, h=260, pad=32) -> str:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    path = " ".join(
        f"{_xy(x, 0, max(xs), pad, w - pad):.1f},{_xy(y, 0, max(ys), h - pad, pad):.1f}"
        for x, y in points
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" width="100%" '
        f'aria-label="actual vs predicted latency">'
        f'<title>Actual vs predicted latency</title>'
        f'<polyline fill="none" stroke="currentColor" stroke-width="2" points="{path}"/>'
        f"</svg>"
    )
```

- CSS in a plain constant (no interpolation), substituted through `Template` — this is why `str.format` is the wrong tool (braces).
- Escape every dynamic string: `html.escape` for HTML, `xml.sax.saxutils.escape` for SVG text, `quoteattr` for attributes. Model names and paths are user-controlled.
- Charts: (a) audio_s vs total_s scatter with identity + fitted line, (b) stacked per-stage bars for the last 20 runs, (c) residual histogram with manually computed bins. Add `<title>` inside each `<circle>` for native tooltips — no JavaScript.
- Dark mode with `@media (prefers-color-scheme: dark)` and CSS variables; `font-family: system-ui, sans-serif`. No web fonts, no CDN, no remote images: the file must open offline and leak nothing.
- CSV: build `io.StringIO`, `csv.writer(buf, lineterminator="\n")`, write via `fsync=False` because it is a byte-identical file on disk, not a byte-stream sink.
- Generate the clickable `report.html` from the **last 200 runs** at worker finish (≈1–5 ms) so the pill's click is instant; `voice --report` reads the full (bounded) ledger on demand. Both use the atomic write from P2.

### P8 — Quickshell status consumption (0.3.2 verified)

```qml
readonly property string stateDir: {
    const s = Quickshell.env("XDG_STATE_HOME");
    const base = (s && s.length > 0) ? s : (Quickshell.env("HOME") + "/.local/state");
    return base + "/voicemode";
}
readonly property string statusPath: runtimeDir + "/status.json"
readonly property string reportPath: status.report_path.length > 0
    ? status.report_path : stateDir + "/report.html"

FileView {
    id: statusFile
    path: root.statusPath
    watchChanges: true          // Quickshell 0.3.2; watches parent dir too
    printErrors: false
    onFileChanged: reload()
    JsonAdapter {
        id: status
        property int schema: 0
        property int pid: 0
        property string state: ""
        property string phase: ""
        property real eta_epoch: 0        // epoch SECONDS as double
        property real expires_at: 0
        property int segments_done: 0
        property int segments_total: 0
        property string report_path: ""
    }
}

readonly property real etaRemaining: (
    status.schema === 1 && status.pid === root.sttPid
    && Date.now() / 1000 < status.expires_at
    && status.eta_epoch > 0
) ? Math.max(0, status.eta_epoch - Date.now() / 1000) : -1
```

- **QML `int` is 32-bit.** Epoch seconds (1.76e9) fit, but epoch milliseconds (1.76e12) do **not** — use `real` (double) for `eta_epoch`, `expires_at`, `started_at`. Use `int` only for `pid`, segment counts, and durations under 24 days.
- JSON must contain **no `null`s** for adapter-typed fields; use `0` / `""` / `-1` sentinels. JsonAdapter type-coerces and a null can drop the update.
- Keep the PID file as the state authority (`Voice.qml:166-209` unchanged); `status.json` is advisory and ignored unless `schema==1 && pid==sttPid && state==pidState && now<expires_at`.
- Keep a slow safety poll (1000 ms; existing 2500 ms idle is fine) in addition to `watchChanges`, to recover if `$XDG_RUNTIME_DIR/voice-stt` did not exist when the watcher was installed. Drop the redundant per-tick `reload()` calls for PID files.
- Click: `MouseArea` currently swallows all buttons (`VoicePill.qml:104-112`). Accept clicks only in `transcribing`/`typing`/`wrapup`, set `cursorShape: Qt.PointingHandCursor`, validate `status.report_path.startsWith(root.stateDir)`, then `Quickshell.execDetached(["xdg-open", root.reportPath])`. Do **not** exec `voice --report` from QML: the venv console script may not be on Quickshell's `PATH`, and a 0.3–0.6 s spawn (pre-refactor) makes the click feel broken.
- `status.json` skeleton (schema 1, no nulls): `schema, pid, run_id, state, phase, started_at, updated_at, expires_at, audio_s, segments_total, segments_done, eta_epoch, eta_remaining_s, confidence, calibrations_n, fallback, backend{model,device,compute_type}, chars_out, report_path`.

### P9 — Lazy imports (do this first)

```python
# before: import numpy as np; import sounddevice as sd; from faster_whisper import WhisperModel
def load_model(args, *, force_cpu: bool = False) -> ModelState:
    from faster_whisper import WhisperModel
    ...
```

- `sd` sites: 165 (annotation — safe as string), 247, 255, 258, 260, 266 (`Recorder.start`), 586 (`play_tone`), 3125 (`--list-devices`).
- `WhisperModel` sites: 92 (dataclass annotation — string), 621 (annotation — string), 635 (`load_model` body).
- Move `import numpy as np` inside `resample_pcm`, `Recorder._write_chunk_file`, `play_tone`, `synthesize_kokoro_tts` too, or leave it: numpy is only ~50–90 ms. The two that matter are `sounddevice` and `faster_whisper`.
- Do not add a `voice_status.py` second entry point; a `sys.argv` fast-path above line 40 is a valid fallback if the mechanical refactor stalls, but it duplicates PID parsing and is easy to drift.

### P10 — Decode-parameter experiments (outlier lab)

Expose env overrides (the hotkey path cannot pass CLI flags — `background_argv` only forwards known args):

| Variable | Default | Effect |
|---|---|---|
| `VOICE_STT_TEMPERATURE` | unset (library default list) | `0` disables temperature fallback; this is the primary fix for the 47–65 s pathological clip (measured 12.5 s at `temperature=0`) |
| `VOICE_STT_CONDITION_ON_PREVIOUS_TEXT` | `true` | `0` prevents repetition loops; changes cross-segment context |
| `VOICE_STT_WITHOUT_TIMESTAMPS` | `false` | Fewer decoder tokens; progress still monotone from chunk boundaries |
| `VOICE_STT_VAD` | `true` (existing `--vad-filter`) | Changes `duration_after_vad`, i.e. the rate denominator |
| `VOICE_STT_CPU_THREADS` | `0` (auto) | Explicit physical-core count stabilizes throughput; record in fingerprint |

Record only a **whitelist** in the ledger `decode` block: `temperatures` (the list actually passed), `temp_used` (from `Segment.temperature`), `fallbacks` (count where temp > 0), `condition_on_previous_text`, `without_timestamps`, `vad`, `avg_logprob`, `max_compression_ratio`, `no_speech_prob`, `had_initial_prompt`, `initial_prompt_chars`. **Never** serialize `info.transcription_options` wholesale — it embeds `initial_prompt`, `hotwords`, and `prefix`, which are transcript text. Never store `segment.text` or `segment.words`.

Anomaly rule for corpus capture: `rtf > max(3 × median_rtf, p90_rtf × 2)` or `temp_used > 0` or `fallbacks > 0`; copy the WAV to `$XDG_STATE_HOME/voicemode/corpus/<run_id>/` **before** the existing unlink in `run_background_recording` (1820-1824). Opt-in via `VOICE_CORPUS_CAPTURE=1`, caps by file count and total MB, oldest-first pruning, `meta.json` with timings and decode params only.

---

## Alternatives Considered

| Need | Recommended | Alternative | When the alternative is right |
|---|---|---|---|
| Charts | Hand-written inline SVG | matplotlib | Only if raster/print-grade output is required and a ~40 MB wheel + font config is acceptable. Not here: the report must be one small offline file. |
| Charts | Inline SVG | pygal / svgwrite | Only if chart variety grows beyond ~4 hand-built types; both add a dependency for what is ~120 lines here. |
| Storage | JSONL | `sqlite3` (stdlib) | At >100k runs, concurrent readers, or ad-hoc SQL. At ~1 KB/run and one writer, SQLite adds schema migration cost for no benefit. |
| Statistics | `statistics` | numpy | Only if the module already imports numpy for vector work. Here numpy-free keeps telemetry importable in ~30 ms and unit-testable without audio. |
| Hardware | `/proc` + `/sys` | psutil | Only if per-process CPU/IO/thread metrics or cross-platform support were needed. Not for a static fingerprint. |
| GPU info | sysfs + optional `nvidia-smi` | `nvidia-ml-py` / `GPUtil` | Only for live utilization, temperature, or per-process VRAM. |
| Schema | Hand-rolled validation | pydantic / jsonschema | Only if the contract is shared with a service or generated from an IDL. A `schema` int + a key/type snapshot test is enough for one consumer. |
| JSON speed | stdlib `json` | orjson / ujson | Only at >10 MB/s; this is ~1 KB per run. |
| Report templates | `string.Template` | jinja2 | Only when templates need loops/conditionals beyond a few `$rows` substitutions. |
| Terminal table | f-strings + `shutil.get_terminal_size` | tabulate / rich | Only if ANSI color/box drawing is a requirement (it is not; the existing CLI is plain). |
| Status transport | `status.json` + `FileView` | DBus / a daemon | Only if a long-lived service existed. It does not, and the milestone forbids one. |
| File watching | Quickshell `watchChanges` | Python `watchdog` in the worker | The worker writes; it does not watch. The consumer is QML. |
| Locking | `fcntl.flock` around rotation | filelock / portalocker | Only if Windows support mattered. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|---|---|---|
| `matplotlib` | ~40 MB wheel, font cache warmup, slow import, Agg/raster or font-embedding headaches for a self-contained HTML file | Inline SVG + `string.Template` |
| `pandas` | Pulls a large dependency for ~20k rows of simple aggregation; import cost alone exceeds the report budget | `statistics` + list comprehensions |
| `psutil`, `py-cpuinfo`, `GPUtil`, `nvidia-ml-py` | New runtime deps to read files that are already world-readable | `/proc`, `/sys`, `os`, `platform` |
| `pydantic`, `jsonschema` | Heavy validation for a one-consumer, append-only contract | `schema` version + key/type snapshot test |
| `sqlite3` for this milestone | Adds schema/migration/locking surface; the file is append-only and human-inspectable | JSONL |
| `orjson`, `ujson` | Speed irrelevant at 1 KB/run; extra binary wheel | `json` |
| `rich`, `tabulate`, `colorama` | Terminal output is plain by project convention; ANSI complicates test assertions | f-strings, `get_terminal_size` |
| `jinja2` | Overkill for 3 HTML sections | `string.Template` |
| `pygal`, `svgwrite`, `cairosvg` | Dependency for primitives (`rect`, `circle`, `polyline`, `text`) | ~120 lines of f-strings |
| `watchdog`, `inotify` bindings | Python side only writes; QML side already has `watchChanges` | `FileView.watchChanges` |
| `filelock`, `portalocker` | Linux-only project; `fcntl.flock` is stdlib | `fcntl.flock` |
| `freezegun`, `time-machine` | Clock injection is a function parameter in the predictor | Pass `now_ns` / `clock` callables |
| `tenacity`, retry decorators | A failed telemetry write must be dropped, not retried | `try/except` + `enabled=False` after first hard failure |
| `prometheus_client`, OpenTelemetry, Sentry | Network exporters and a process model this tool does not have; privacy violation | Local JSONL + `--report` |
| `time.time()` for durations | Wall clock can jump (NTP/manual) and produce negative or inflated timings | `time.perf_counter_ns()` |
| `Path.write_text()` for `status.json` | Truncate-then-write gives the 100 ms reader a torn document | `mkstemp` + `os.replace` |
| `fsync` on every status update | Wasted I/O at 5 s heartbeats; durability is irrelevant for a runtime file | `fsync` once per run for the ledger only |
| Status rewrites at 10 Hz | Battery/wakeup cost for a whole-second display | Transition + 5 s heartbeat + per segment |
| QML `int` for epoch values | QML `int` is 32-bit; epoch ms overflows silently | `real`/`double` |
| `Quickshell.execDetached(["voice", "--report"])` | Venv console script may not be on Quickshell's `PATH`; spawn cost is visible on click | Generate `report.html` at run end; `xdg-open` it |
| Writing `status.json` from the parent toggle process | Two writers → out-of-order phase regressions | Worker-only writes |
| Storing transcript text, prompts, hotwords, or segment words in the ledger | Durable privacy leak; `info.transcription_options` contains text | Character/word counts and numeric decode stats only |
| Storing raw WAV paths in the ledger | Leaks filenames/session identifiers and breaks grouping across machines | `run_id` + `audio_s` only |
| Reconfiguring `logging` | Project convention is `print()` + perf-log files; a logger would duplicate/destructure output | Keep `print(..., flush=True)`; telemetry warnings go to stderr (captured in `voice.log`) |

---

## Stack Patterns by Variant

The stack does not change per machine — only which probes return data and which priors the predictor starts from. Each variant below is a **runtime branch in one code path**, not an install variant.

### Variant A — CPU-only, no vendor tools (the verified local machine)

| Aspect | Behaviour |
|---|---|
| Detection | `ctranslate2.get_cuda_device_count() == 0`; `shutil.which("nvidia-smi") is None`; `shutil.which("rocm-smi") is None`; `/sys/class/drm/card*/device/vendor` = `0x8086` (Intel). |
| Backend | `WhisperModel(..., device="cpu", compute_type="int8")` — the existing fallback path (`voice.py:312-316`) becomes the *normal* path, so it must be equally instrumented (do not time only the happy path). |
| Fingerprint | `cpu_model` from `/proc/cpuinfo` `model name` (i5-13500 locally); `physical_cores` = unique `(physical id, core id)` pairs; `usable_cores` = `len(os.sched_getaffinity(0))` (20 locally, not 24); `ram_gb` from `/proc/meminfo` `MemTotal`; `gpu = {vendor: "intel", model: <from `/sys/.../device/uevent` or omit>}`. |
| Priors | CPU int8 RTF ≈ 0.22–0.25 for this class of CPU. Seed `rtf_prior = 0.24`, `load_s_prior = 2.5`, and let calibration replace both. |
| Gotchas | `available_cores` ≠ `physical_cores` ≠ `cpu_count()`; hyperthreads inflate `cpu_count()` and shrink `VOICE_STT_CPU_THREADS` benefit. Record all three; key the model on `physical_cores` because that is what CTranslate2 uses. |

### Variant B — NVIDIA CUDA present

| Aspect | Behaviour |
|---|---|
| Detection | Prefer `ctranslate2.get_cuda_device_count() > 0` as the gate; it is a cheap, dependency-free call. Wrap it: on a machine with a driver but a mismatched runtime it can still throw, so `try/except Exception → 0`. |
| Do **not** gate on `get_supported_compute_types("cuda")` alone | Verified locally: with no usable driver it raises `RuntimeError: CUDA driver version is insufficient for CUDA runtime version`. Always wrap; treat an exception as "no CUDA". |
| Extra fingerprint | `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv,noheader,nounits` via `subprocess.run(timeout=2, capture_output=True, text=True)`; parse defensively, `FileNotFoundError`/`TimeoutExpired`/non-zero → omit the block. Never import `pynvml`. |
| `compute_type` | `float16` on compute capability ≥ 7.0, `int8_float16` on older/lower-VRAM cards; record the value actually used in `backend.compute_type` and in the fingerprint, since it changes RTF by ~2×. |
| Priors | `rtf_prior = 0.05`, `load_s_prior = 1.5` for `small`/`base` on a discrete card; these are priors only — the first three runs overwrite them. Do not hard-code per-card tables. |

### Variant C — AMD / ROCm or Intel Arc

| Aspect | Behaviour |
|---|---|
| Detection | `/sys/class/drm/card*/device/vendor` = `0x1002` (AMD) or `0x8086` with a `renderD*` node and non-i915 driver; `rocm-smi --showproductname --csv` if present. |
| Support level | `faster-whisper`/CTranslate2 on ROCm is build-dependent. Do **not** attempt to enable it here. Detect, record, and run CPU int8 exactly as Variant A. The predictor keys on `backend.device`, so a ROCm build later needs no schema change. |
| Gotchas | `/sys/class/drm/card0` is often the iGPU even when a dGPU exists; enumerate all `card*` and pick by `device/vendor` + `device/class`, not by index. Never assume `card0`. |

### Variant D — First runs (`calibrations_n < 3`)

| Aspect | Behaviour |
|---|---|
| API shape | `predict(...) -> Prediction(eta_s, confidence: "none"|"low"|"medium"|"high", basis: "prior"|"blended"|"calibrated")`. Never return a bare float — the confidence string is what the UI and tests assert on. |
| Behaviour | `n == 0` → prior only, `confidence="low"`, UI shows the phase word ("transcribing") and no number. `n == 1..2` → blend prior and observed with weight `n/(n+3)`, `confidence="low"`. `n >= 3` → calibrated, `confidence="medium"`; `n >= 10` and residual MAD < 25 % → `"high"`. |
| UI rule | Show `~Xs` only when `confidence != "none"` and `eta_remaining_s` is finite and `< 600`; otherwise keep the existing timer (`VoicePill.qml` already renders elapsed time). A wrong ETA is worse than no ETA. |
| Tests | Feed synthetic ledgers with `n = 0, 1, 2, 3, 10` and assert monotone decreasing ETA and the exact confidence transitions. |

### Variant E — Multi-chunk / long audio

| Aspect | Behaviour |
|---|---|
| Progress source | `info.duration` and `info.duration_after_vad` are available **before** the segment generator is consumed (verified: `transcribe.py:1012-1022` returns `info` eagerly). `segments_total` is therefore known up front — no guessing. |
| ETA model | Fit `total_s ≈ load_s + a + b * audio_s` on calibrated runs; fall back to `total_s ≈ load_s + audio_s / rtf` when `n < 3`. Locally the RTF after subtracting ~2.5 s of load is 0.217 / 0.232 / 0.246 / 0.241 at 30 / 60 / 115 / 180 s — near-linear with a small positive intercept, so a two-parameter fit is justified and a pure ratio is not. |
| Monotonicity | Track `max(eta_epoch)` seen; never let an updated estimate move *later* by more than 1 s without resetting `confidence` to `"low"`. Emit one status write per completed segment (`segments_done`), plus the 5 s heartbeat. |
| VAD asymmetry | If VAD trims 40 % of a file, the rate denominator must be `duration_after_vad`, not `duration`; store both and fit on the one that is populated. Otherwise long silences look like a slow model. |

### Variant F — `status.json` missing, stale, or from a dead PID

| Aspect | Behaviour |
|---|---|
| Reader | Treat `status.json` as advisory only. Existing PID file remains authoritative (`Voice.qml:166-209` unchanged). |
| Validity | Accept only if `schema == 1` **and** `pid == <PID from pid file>` **and** `time.time() < expires_at`. `expires_at = updated_at + 15` (3 missed 5 s heartbeats) is generous enough to survive a long single-segment decode, because the worker also refreshes `expires_at` before entering `model.transcribe()`. |
| Failure mode | Missing/corrupt/older-schema file → render exactly today's UI (state from PID + elapsed timer), no error toast. `json.JSONDecodeError` is expected during the atomic-replace window only if a reader opens the temp path — it will not, because the temp name is random and only the final path is watched. |
| Cleanup | Worker removes `status.json` in its `finally` block (same place the WAV is unlinked, `voice.py:1820-1824`), so a stale file cannot outlive a clean exit. Crash-leftover files are handled by `expires_at`. |

### Variant G — Older Quickshell (or no Quickshell)

| Aspect | Behaviour |
|---|---|
| Feature detection | `FileView.watchChanges` and `JsonAdapter` are present in 0.3.2 (verified in the installed tree and in `src/io/fileview.cpp`). On older builds, `watchChanges` may be absent or parent-dir watching may not re-add the path after `os.replace`. |
| Degradation | Keep the existing 1000–2500 ms `Timer` poll as the unconditional fallback. It is ~1 `stat` + occasional read; the cost is irrelevant next to the current 2.5 s poll. Do not require the watcher for correctness. |
| Non-Quickshell users | The Python side never assumes a consumer. `--report` and the JSONL ledger are the portable interface; the QML integration is one consumer among possible others (Waybar script, etc.). |

---

## Version Compatibility

| Component | Verified version | Constraint / note |
|---|---|---|
| Python | 3.12.12 (`.venv`) | Project declares `requires-python = ">=3.12"`; `statistics.linear_regression` needs 3.10+, `datetime.UTC` 3.11+. `os.process_cpu_count` is 3.13-only — use `len(os.sched_getaffinity(0))`. |
| `faster-whisper` | 1.2.1 | Keep `>=1.2.1`. Telemetry relies on `TranscriptionInfo.duration`, `.duration_after_vad`, `.language_probability`, `.transcription_options`, and `Segment.temperature` — all present in 1.2.x. Re-verify these attribute names on any 2.x bump. |
| `ctranslate2` | 4.8.2 (transitive) | `get_cuda_device_count()` and `get_supported_compute_types()` are the probe surface. The latter **raises** without a usable driver — always guard. |
| `numpy` | 2.5.3 | Not imported by the telemetry module. Only used where audio already needs it. Stays `>=2.0.2`. |
| `sounddevice` | 0.5.6 | Only needed by `Recorder`, `play_tone`, `--list-devices`; must be lazy-imported. |
| `kokoro-onnx` | 0.5.0 (extra `[kokoro]`) | Optional; TTS timings go in a separate event kind and must not pollute STT priors. |
| `edge-tts` | 7.2.8 (extra `[edge]`) | Optional; network-bound, different distribution — never pool with local TTS/STT stats. |
| `soundfile` | 0.14.0 (extra `[kokoro]`) | Unchanged. |
| `PyYAML` | 6.0.3 | Unchanged; used only for the Hermes config fallback. |
| Quickshell / Qt | 0.3.2 / Qt 6.12.0 | `FileView.watchChanges`, `JsonAdapter`, `Quickshell.execDetached`, `Quickshell.env` all present. QML `int` is 32-bit — epoch fields must be `real`. |
| `ruff` | project-configured | `line-length = 120`, `target-version = "py312"`. The new module must pass unchanged; no `# noqa` growth. |
| `unittest` / `pytest` | stdlib / dev | New tests use `unittest` (already the project's idiom) and are pytest-collectable. No fixture plugins, no `pytest-mock` — inject a fake clock/ledger path. |

**Pinning:** add no new entries to `dependencies` or `optional-dependencies`. If a pin is desired for reproducibility, pin nothing new — the surface is stdlib.

---

## Privacy & Portability Guardrails

These are stack-level constraints, not afterthoughts. Each is cheap to honour and expensive to retrofit.

**Privacy (the ledger is durable and may be backed up/synced):**

- Serialize an **allowlist**, never a denylist. One `_ledger_record()` function builds the dict explicitly; no `asdict(info)`, no `vars()`, no `**kwargs` passthrough.
- **Never** persist: `segment.text`, `segment.words`, `info.transcription_options` (it contains `initial_prompt`, `hotwords`, `prefix`), the WAV path, the audio bytes, clipboard contents, window titles, or the selected text that TTS read. Store `chars_out`, `words_out`, `audio_s` and numeric decode stats only.
- Enforce mechanically with a test: a key/type snapshot plus a regex scan of a synthesized record for `text|prompt|hotword|prefix|/tmp|\.wav|file` (keys and string values). This is the single most valuable test in the module.
- File modes: ledger dir `0700`, files `0600` (`os.open(..., 0o600)` / `os.makedirs(..., mode=0o700)`). `$XDG_STATE_HOME` may be on a synced filesystem; mode bits are the only local control, so document it in `--doctor`.
- `VOICE_TELEMETRY=0` disables all writes (reads still work for `--report`). Any write failure (read-only FS, ENOSPC, EACCES) disables telemetry for the rest of the process after one stderr warning — telemetry must never break dictation.
- No network, ever, in the telemetry path: no crash reporting, no usage pings, no remote font/image in `report.html`. The report is offline-openable by construction.

**Portability:**

- Resolve state with XDG fallbacks: `$XDG_STATE_HOME` → `~/.local/state`, `$XDG_RUNTIME_DIR` → `tempfile.gettempdir()`. Never hard-code `~/.local/state` or `/run/user/<uid>`.
- Timestamps in the ledger are **integer epoch milliseconds, UTC**; durations are **integer milliseconds** from `perf_counter_ns`. The exception is `status.json`, whose epoch fields (`started_at`, `updated_at`, `expires_at`, `eta_epoch`) are **epoch seconds as JSON numbers** so QML can hold them in a `real` without overflow. Never store local-time strings, and never store seconds in the ledger or milliseconds in `status.json`.
- Units in the key names: `_s`, `_ms`, `_mb`, `_gb`. No bare `duration`/`size`.
- Locale: parse `/proc` and vendor CSV with explicit ASCII expectations; never `locale`-format numbers into the ledger. CSV export of the model name is quoted by `csv.writer`, not by hand.
- Hardware probes are best-effort and must not raise: every read is `try/except (OSError, ValueError, IndexError)` returning `None`, and `None` keys are omitted (or emitted as `0`/`""` only in `status.json`, which forbids nulls).
- `schema` is an integer on every record and in `status.json`. Readers ignore unknown `schema` values; writers bump only on breaking key changes. Additive keys do not bump.
- Size caps: ledger rotation at 5 MB (keep one `.1`), `--report` reads at most the last 5 000 lines, `report.html` uses the last 200 runs. Caps are constants in the module, not env-tunable.

---

## Confidence Assessment

| Area | Confidence | Reason |
|---|---|---|
| Stdlib choices (`json`, `statistics`, `csv`, `html`, `string.Template`, `tempfile`, `fcntl`) | **HIGH** | Verified against the local 3.12.12 interpreter; APIs are stable and documented; empty-input behaviour (`StatisticsError`) checked directly. |
| "Zero new dependencies" | **HIGH** | Every required capability was exercised locally with the project venv; the only gap (charts) was closed with ~120 lines of SVG. |
| Version facts (`faster-whisper` 1.2.1, `ctranslate2` 4.8.2, Quickshell 0.3.2 / Qt 6.12.0, etc.) | **HIGH** | Read from the installed distributions (`importlib.metadata`) and the local Quickshell source, not from memory. |
| Lazy-import payoff (~0.5 s) | **HIGH** | Measured repeatedly (`python -X importtime`, wall-clock medians) in this venv; `from __future__ import annotations` already present, so annotations do not force imports. |
| faster-whisper instrumentation surface (`info` eager, `Segment.temperature`, options fields) | **HIGH** | Read in `faster_whisper/transcribe.py` at the cited lines (1012-1022, 981-984, 1432, 1844-1870). |
| Quickshell `FileView` semantics (parent-dir watch, re-add after rename) | **HIGH** | Installed 0.3.2 QML types present; `src/io/fileview.cpp` implements parent watching and path re-add. |
| Atomic-replace + append-only patterns | **HIGH** | Standard POSIX semantics; `os.replace` atomic within a filesystem, `O_APPEND` write of a single small buffer is atomic in practice on Linux. |
| Hardware probe on this machine (Intel i915, i5-13500, 20 usable CPUs) | **HIGH** | Read directly from `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `os.sched_getaffinity`. |
| NVIDIA / ROCm probe details | **MEDIUM** | Interfaces (`nvidia-smi --query-gpu`, `rocm-smi --csv`, sysfs vendor IDs) are documented and stable, but no such hardware was available to execute against. Parsing is defensive and the code path degrades to Variant A. |
| Predictor accuracy / seed priors | **LOW** | The 0.24 RTF and 2.5 s load priors come from a handful of runs on one machine. They are intentionally disposable: `calibrations_n` and the confidence ladder exist so the product never depends on them. |
| SVG/HTML report aesthetics | **MEDIUM** | Functionality is straightforward; visual quality is a design judgement to be validated against the UI-SPEC, not a technical risk. |

---

## Sources

| Source | What it established | Confidence |
|---|---|---|
| Project `.venv` (`python -c "import importlib.metadata as m; ..."`) | Exact installed versions of `faster-whisper`, `ctranslate2`, `numpy`, `sounddevice`, `kokoro-onnx`, `edge-tts`, `soundfile`, `PyYAML`; Python 3.12.12 | HIGH |
| `python -X importtime` / wall-clock timing runs in the venv | `import sounddevice` ≈ 250–320 ms; `from faster_whisper import WhisperModel` ≈ 245–260 ms; `import numpy` ≈ 50–90 ms; bare interpreter ≈ 76 ms; `import voice` ≈ 0.32–0.60 s | HIGH |
| `.venv/lib/python3.12/site-packages/faster_whisper/transcribe.py` (installed 1.2.1) | `info` returned eagerly at 1012-1022; VAD applied before return at 884-893; scalar `temperature` promoted to a list at 981-984; fallback loop at 1432; `restore_speech_timestamps` at 1844-1870; `TranscriptionOptions` carries `initial_prompt`/`hotwords`/`prefix` | HIGH |
| `ctranslate2` runtime probes | `get_cuda_device_count()` returns `0` safely; `get_supported_compute_types("cuda")` raises `RuntimeError` without a usable driver | HIGH |
| Local Quickshell 0.3.2 install + `src/io/fileview.cpp` (lines ~493-546) | `FileView.watchChanges`, `fileChanged`, `JsonAdapter`; parent-directory watching; path re-add after rename | HIGH |
| `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm/card1/device/*`, `os.sched_getaffinity(0)` | i5-13500; Intel `8086:4680` on i915; 20 usable CPUs; no `nvidia-smi` or `rocm-smi` on this host | HIGH |
| Python 3.12 docs — `statistics`, `tempfile`, `os.replace`, `fcntl`, `csv`, `string.Template`, `xml.sax.saxutils` | API availability/semantics; `statistics.linear_regression` since 3.10; `StatisticsError` on empty input | HIGH |
| `voice.py` (read at the cited line ranges) | Import sites (40-42), `Recorder` SD call sites, `load_model`/`transcribe`, `insert_text`, `background_argv`, `run_background_recording` cleanup, `print_status`, `main` | HIGH |
| `.planning/research/ARCHITECTURE.md`, `.planning/research/FEATURES.md` | Module boundary (`voicemode_telemetry.py`), `status.json` schema, `eta_epoch`/`expires_at` contract, PID-as-authority rule, feature IDs | HIGH (internal, peer-authored) |
| NVIDIA `nvidia-smi` docs; AMD `rocm-smi` docs; sysfs DRM vendor IDs | Vendor probe command shapes and vendor ID values, for variants that could not be executed here | MEDIUM |

---

*Stack research for: voicemode v1.1 — latency prediction, local telemetry, and Quickshell status integration*
*Researched: 2026-10-26*
