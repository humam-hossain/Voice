# Telemetry

VoiceMode records local, opt-out telemetry to help understand latency, transcription performance, and system reliability. **Nothing is ever sent over the network.**

## What is recorded

### Schema v1 Fields

Every ledger record contains all standard Schema v1 fields:

| Field | Type | Description |
|---|---|---|
| `schema` | int | Always `1` |
| `source` | str | `"stt"` or `"tts"` |
| `run_id` | str | Per-run unique identifier (uuid hex) |
| `install_id` | str | Salted SHA-256 hash of machine-id (local only, never transmitted) |
| `ts_start` | float | Unix start timestamp |
| `ts_end` | float | Unix end timestamp |
| `outcome` | str | `success \| partial_success \| cancelled \| error \| watchdog_timeout \| abandoned` |
| `error_stage` | str\|null | Stage where error occurred (`load`, `decode`, `finalize`, `insert`, or null) |
| `actual` | object | `{total_ms, finalize_ms, load_ms, decode_ms, insert_ms}` |
| `audio_s` | float | Audio duration in seconds |
| `chars_out` | int | Transcript character count (count only) |
| `chars_typed` | int | Characters typed/inserted into focused application |
| `fallback_used` | bool | True if hardware/CPU fallback was triggered |
| `insert_ok` | bool | True if text insertion succeeded |
| `segments` | array | Per-segment timing and probability metadata (no text) |
| `config` | object | Fingerprint: `model, device, compute_type, beam_size, vad_filter, language, chunk_s` |
| `backend` | str\|null | Resolved backend (e.g. `cpu, int8`) |
| `tts` | object | Reserved fields for future TTS tracking (`predicted_ms, actual_ms, chars, voice, backend, synth_ms, play_ms` — all null for STT) |
| `outlier` | bool | True if run exceeded outlier thresholds (RTF > 1.0 or tail decode > 10.0s) |
| `outlier_reason` | str\|null | Reason string (`"rtf_exceeded"`, `"tail_decode_exceeded"`, or null) |
| `corpus_file` | str\|null | Relative path (`corpus/voice-*.wav`) to saved diagnostic audio if captured, else null |
| `cold_load` | bool | True if run was the first transcription session after system boot |
| `failed_chunks` | list\|null | Chunk indexes that failed or required fallback retry |
| `chunks` | list\|null | Multi-chunk breakdown: `[{idx, audio_s, decode_ms, rtf, outlier, retries, ok}]` |

**Strict Privacy Guarantee:** Transcript text, individual words, hotwords, prompts, clipboard contents, argv parameters, absolute file paths, hostnames, usernames, and OS versions are **never recorded**.

---

## Outlier Detection & Focus Safety

Outlier classification runs automatically on every transcription to track performance degradation and tail latency:

- **Criteria:** A run is classified as an outlier if:
  1. Real-Time Factor (RTF) exceeds threshold: $\text{RTF} = \frac{\text{decode\_ms} / 1000.0}{\text{audio\_s}} > 1.0$
  2. Tail decode duration exceeds cutoff: $\text{decode\_ms} > 10{,}000.0\text{ ms}$ (10.0 seconds).
- **Configuration:**
  - `VOICEMODE_OUTLIER_RTF_THRESHOLD` (float, default: `1.0`): Multiplier of audio duration.
  - `VOICEMODE_OUTLIER_TAIL_S` (float, default: `10.0`): Absolute decode ceiling in seconds.
- **Focus Safety Policy:** Outlier detection is **silent and non-intrusive**. It never emits desktop notifications (`notify-send`) or sound cues (`beep`) to ensure the focused application window retains focus for synthesized keystrokes. Outliers are surfaced exclusively via `voice --report` and `voice --doctor`.

---

## Opt-In Diagnostic Audio Corpus Capture

To diagnose acoustic failure modes or transcription accuracy issues, voicemode supports opt-in audio corpus retention:

- **Disabled by Default:** Corpus capture is completely disabled (`none`) out of the box. Audio is captured only when explicitly enabled via `--capture-corpus` or `VOICEMODE_CORPUS_CAPTURE`.
- **Modes:**
  - `none` (default): Audio files are temporary and immediately unlinked after transcription.
  - `outliers`: Only audio from runs classified as outliers is retained.
  - `all`: All recorded audio is saved.
- **Local Storage & Permissions:** Captured audio files are saved in:
  `${XDG_STATE_HOME:-~/.local/state}/voice-stt/corpus/`
  with strict POSIX permissions: directory `0700` (`rwx------`), files `0600` (`rw-------`).
- **Relative Path Privacy:** Telemetry ledger records store relative paths (e.g. `corpus/voice-abc.wav`), preventing developer usernames and host paths from being recorded.
- **Strict FIFO Bounds:** Corpus storage is strictly capped at **50 files** and **100 MB** total disk usage. Pruning runs on each write; files less than 60 seconds old are protected by a grace period.
- **Free Space Protection:** Capture aborts gracefully if the filesystem has less than **1 GB** free space.
- **Zero Network Access:** Captured corpus audio is 100% local and is never uploaded or transmitted.
- **Purge Command:** Run `voice --purge-corpus` at any time to permanently remove all saved corpus audio files and reclaim disk space.

---

## Degraded Durability Policies

VoiceMode is hardened against hostile environments and resource constraints:

1. **Fallback Runtime Directory:** If `$XDG_RUNTIME_DIR` is unset or unavailable, voicemode falls back to `/tmp/voice-stt-$UID/` with `0700` permissions.
2. **Read-Only State & Full Disk (`ENOSPC`):** If disk writes fail, the recorder retains audio in-memory as a `float32` numpy array and passes it directly to Faster-Whisper. Status publishing and ledger appends gracefully log warnings to stderr without breaking text insertion.
3. **Non-16kHz Hardware Resampling:** Audio captured at non-standard hardware rates (e.g. 44.1 kHz, 48 kHz) is automatically resampled in-memory to 16 kHz.
4. **Memory-Constrained Thread Clamping:** On CPU inference, Whisper thread count is clamped to `min(4, os.cpu_count() or 4)`, and resident pages are collected via `gc.collect()` to guarantee stability on 4 GB RAM systems.

---

## Hardware Backend Probing

Hardware probing inspects acceleration capabilities safely without instantiating heavy AI runtimes:

- **CPU Vector Extensions:** Inspects `/proc/cpuinfo` directly for AVX2 and AVX-512 flags without spawning subprocesses.
- **Guarded GPU Probing:** Checks CUDA device count via `ctranslate2.get_cuda_device_count()` and queries `nvidia-smi` with a strict **1.0s timeout**. Checks `/dev/kfd` (ROCm) and `/dev/dri` (Intel/Mesa).
- **Enforced Baseline:** Discrete GPUs are reported purely informatively in `voice --doctor`. Execution strictly defaults to `cpu, int8`.

---

## Stratified Latency Evaluation Protocol (ACC-06)

Transcription latency and estimator accuracy are evaluated across three clip duration strata:

| Stratum | Clip Duration | Description | Target RTF (CPU int8) |
|---|---|---|---|
| **Short** | $< 5.0\text{ s}$ | Short voice commands and quick phrases | $\le 0.35$ |
| **Medium** | $5.0\text{ s} - 30.0\text{ s}$ | Standard sentences and multi-phrase dictation | $\le 0.35$ |
| **Long** | $> 30.0\text{ s}$ | Long-form dictation and extended thought capture | $\le 0.35$ |

**Alder Lake CPU Baseline Target:** Across a 20-run reference benchmark on Intel Alder Lake CPU `int8`, the system achieves:
- Overall median RTF $\le 0.35$
- Outlier share $\le 5\%$ ($\le 1$ outlier per 20 runs).

---

## Where it lives

- **Telemetry Ledger:** `${XDG_STATE_HOME:-~/.local/state}/voicemode/metrics.jsonl`
- **Rotated Archives:** `${XDG_STATE_HOME:-~/.local/state}/voicemode/metrics-*.jsonl` (rotated at 50,000 rows or 25 MB)
- **Diagnostic Corpus:** `${XDG_STATE_HOME:-~/.local/state}/voice-stt/corpus/` (0700/0600)
- **Pre-rendered HTML Dashboard:** `${XDG_STATE_HOME:-~/.local/state}/voice-stt/report.html`
- **Runtime Status:** `${XDG_RUNTIME_DIR:-/tmp/voice-stt-$UID}/voice-stt/status.json` (removed on exit)
- **Permissions:** Directories `0700`, files `0600`.

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `VOICE_METRICS` | (unset $\to$ enabled) | Primary kill switch. Set to `off`, `0`, `false`, or `no` to disable all ledger/status writes. |
| `VOICE_TELEMETRY` | (unset) | Backward-compatible alias; consulted only if `VOICE_METRICS` is unset. |
| `VOICEMODE_CORPUS_CAPTURE` | `none` | Corpus capture mode: `none`, `outliers`, or `all`. |
| `VOICEMODE_OUTLIER_RTF_THRESHOLD` | `1.0` | Real-Time Factor cutoff above which runs are tagged as outliers. |
| `VOICEMODE_OUTLIER_TAIL_S` | `10.0` | Absolute decode latency ceiling in seconds for outlier detection. |

---

## Deletion & Purge Procedure

To delete all telemetry and diagnostic files:

```bash
# Purge diagnostic audio corpus files:
voice --purge-corpus

# Delete persistent ledger, archives, and install tokens:
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/voicemode"
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/voice-stt/corpus"
rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-stt/status.json"
rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-stt/install_id"
rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-stt/install_salt"
```

Nothing is sent over the network.
