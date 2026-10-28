# Telemetry

VoiceMode records local, opt-out telemetry to help understand latency and reliability. **Nothing is sent over the network.**

## What is recorded
Schema v1 fields (every key present on each row):

| Field | Type | Description |
|---|---|---|
| schema | int | Always `1` |
| source | str | `"stt"` or `"tts"` |
| run_id | str | Per-run identifier (uuid hex) |
| install_id | str | Salted hash of machine-id (local only) |
| ts_start/ts_end | float | Unix timestamps |
| outcome | str | `success \| cancelled \| error \| watchdog_timeout \| abandoned` |
| error_stage | str|null | Stage where error occurred |
| actual | object | `{total_ms, finalize_ms, load_ms, decode_ms, insert_ms}` |
| predicted | object | ETA prediction metadata (shown values) |
| audio_s | float | Audio duration |
| chars_out | int | Transcript character count (count only) |
| chars_typed | int | Characters typed/inserted (count only) |
| fallback_used/insert_ok | bool | Fallback/insert flags |
| segments | array | Per-segment evidence (timings/probabilities, no text) |
| config | object | Fingerprint: `model, device, compute_type, beam_size, vad_filter, language, chunk_s` only |
| backend | str|null | Resolved backend (e.g., `cpu, int8`) |
| calibration_key | str|null | Portability key for calibration grouping |
| tts | object | Reserved fields (all null in this milestone) |

**Not recorded:** transcript text, words, prompts, hotwords, clipboard contents, argv, file paths, hostname, username, OS version, CPU/GPU identifiers.

## Where it lives
- Ledger: `${XDG_STATE_HOME:-~/.local/state}/voicemode/metrics.jsonl`
- Archives: `${XDG_STATE_HOME:-~/.local/state}/voicemode/metrics-*.jsonl` (created on rotation)
- Runtime status: `${XDG_RUNTIME_DIR:-/tmp/voice-stt-*}/voice-stt/status.json` (advisory, removed on exit)
- Install identity: `${XDG_RUNTIME_DIR}/voice-stt/install_id` and `install_salt` (salted hash, local only)
- Permissions: directories `0700`, files `0600`

**Clipboard caveat:** The transcript may be placed on the clipboard by design for insertion; the ledger never records clipboard contents or transcript text.

## Environment variables
| Variable | Default | Purpose |
|---|---|---|
| `VOICE_METRICS` | (unset → enabled) | Primary kill switch. Set to `off`, `0`, `false`, or `no` to disable all ledger/status writes. |
| `VOICE_TELEMETRY` | (unset) | Backward-compatible alias; consulted only if `VOICE_METRICS` is unset. |
| `VOICE_CAPTURE_OUTLIERS` | `off` | Reserved. Currently has no effect (Phase 10 will implement it). |

## Deletion procedure
To delete all telemetry data:
```bash
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/voicemode"
rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-stt/status.json"
rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-stt/install_id"
rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-stt/install_salt"
```
Nothing is sent over the network.
