# Architecture Research: v1.1 Latency Prediction & Telemetry

**Domain:** Desktop speech utility — single-file Python app, per-dictation detached worker, PID-file state machine, external Wayland status bar
**Researched:** 2026-10-25
**Confidence:** HIGH for integration points (read from source); MEDIUM for predictor priors (placeholders to tune from collected data); HIGH for persistence/contract design

## Executive Recommendation

Keep `voice.py` as the orchestration/OS layer and add **exactly one** pure companion module, `voicemode_telemetry.py`, that owns:
schema constants, atomic JSON writes, JSONL ledger append/read/rotation, the pure predictor, report formatters, and a `RunTelemetry` I/O adapter.

Do **not** add a daemon, model pre-warm, SQLite, or a new dependency. Do **not** change the PID-file state vocabulary. Treat the PID file as the **authority for state** and `status.json` as **advisory enrichment** (ETA, progress). Write `status.json` only from the recorder worker (single writer). Append exactly one ledger record per run in the worker's `finally:`.

This satisfies the milestone's hard constraints: no new daemon, no heavy dependency, one small clearly-justified split (pure logic out of a 3,154-line monolith), testable seams via explicit path/clock injection, and graceful degradation when the ledger, GPU probe, or status write is unavailable.

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│ PRESENTATION (external dotfiles repo, not this repo)                 │
│  Quickshell Voice.qml ── polls 100ms ──► recorder.pid  (AUTHORITY)   │
│         │                              ► tts.pid                     │
│         └────────────── polls ────────► status.json  (ADVISORY ETA)  │
│  VoicePill.qml renders state + countdown from status.eta_epoch       │
└───────────────────────────────▲──────────────────────────────────────┘
                                │ atomic file contract (schema 1)
┌───────────────────────────────┴──────────────────────────────────────┐
│ INTEGRATION LAYER — voice.py (modified)                              │
│  toggle_background_recording (1661-1706)  spawns worker, PID only   │
│  run_background_recording (1709-1865)     state transitions + timing │
│  transcription_watchdog_handler (923-952) timeout finalization       │
│  print_status / doctor / main / argparse  read + report CLI          │
└───────────────┬───────────────────────────────────┬──────────────────┘
                │ in-process calls                   │ paths injected
┌───────────────▼───────────────────┐   ┌───────────▼──────────────────┐
│ PURE/LOGIC — voicemode_telemetry.py│   │ PERSISTENCE                  │
│  RunTelemetry (I/O adapter)        │   │  runtime: status.json        │
│  predictor (pure functions)        │   │  state: metrics.jsonl(.1,.2) │
│  ledger reader/writer/rotation     │   │         corpus/<run_id>/     │
│  report formatters (txt/csv/html)  │   │  PID files unchanged         │
└────────────────────────────────────┘   └──────────────────────────────┘
                ▲
                │ existing OS/audio layer (UNCHANGED)
   Recorder (150-337) · load_model (631-643) · transcribe (646-680)
   insert_text (1168-1214) · PID helpers (799-859) · logs (46-50)
```

### Component Responsibilities

| Component | Responsibility | New / Modified |
|-----------|----------------|----------------|
| `voicemode_telemetry.py` | Schema v1, atomic JSON write, JSONL append/read/rotate, predictor, report formatters, `RunTelemetry` adapter | **NEW** |
| `RunTelemetry` | Per-run lifecycle: status writes, stage timings, segment events, ETA refresh, corpus decision, terminal ledger record | **NEW** |
| `run_background_recording` | Call `RunTelemetry` at every transition and in `finally`; no state-vocabulary change | **MODIFIED (major, 1709-1865)** |
| `transcription_watchdog_handler` | Best-effort timeout status + ledger + corpus before `os._exit(1)` | **MODIFIED (923-952)** |
| `toggle_background_recording` | Clean stale status temp files; still PID-only | **MODIFIED (small, 1661-1706)** |
| `parse_args` / `main` | `--report` family, optional `--capture-corpus`; dispatch before model work | **MODIFIED (2884-3085, 3088-3150)** |
| PID helpers | Unchanged; PID file remains state authority | **UNCHANGED (799-859)** |
| `Recorder` | Unchanged; segment audio duration derived with `wave` in telemetry module | **UNCHANGED (150-337)** |
| `load_model` / `transcribe` | Unchanged; caller times them and detects CPU fallback via returned `ModelState` | **UNCHANGED (631-680)** |
| `insert_text` | Unchanged; caller times it | **UNCHANGED (1168-1214)** |
| `pyproject.toml` | `py-modules = ["voice", "voicemode_telemetry"]`; no dependency changes | **MODIFIED** |
| `tests/test_telemetry.py` | Ledger/status/predictor/report/corpus unit tests | **NEW** |
| `tests/test_audio_chunking.py` | Patch `voice.RunTelemetry` in the two worker tests (98-223) to avoid real writes | **MODIFIED** |
| `tests/test_hyprland_daemon.py` | Extend watchdog test (374-394) for new optional args | **MODIFIED** |
| `Voice.qml` (external) | Add `status.json` FileView + parse ETA/progress; keep PID-derived state | **MODIFIED (external repo, 13-18, 54-67, 159-251)** |
| `VoicePill.qml` (external) | Show countdown for `transcribing` | **MODIFIED (external repo, 50-60)** |

---

## Recommended Project Structure

```
Voice/
├── voice.py                     # CLI, OS/audio, subprocess, PID state (existing; instrumented)
├── voicemode_telemetry.py       # NEW: schema, ledger I/O, predictor, reports, RunTelemetry
├── pyproject.toml               # add py-modules entry; no new deps
├── docs/
│   └── telemetry.md             # NEW: schema v1 contract, privacy, corpus opt-in
└── tests/
    ├── test_telemetry.py        # NEW: schema/atomicity/predictor/reports/corpus
    ├── test_audio_chunking.py   # update worker mocks
    └── test_hyprland_daemon.py  # update watchdog expectations
```

### Structure Rationale

- **`voice.py`:** keeps every OS-facing concern (PortAudio, subprocess, PID/signals, typing) exactly where the project convention expects it. The worker's try/finally is the only place that knows the real stage sequence.
- **`voicemode_telemetry.py`:** pure Python, stdlib only (`json`, `os`, `statistics`, `csv`, `html`, `pathlib`, `time`, `wave`). No `faster_whisper`/`sounddevice` import; tests run without audio/GPU. It has **no knowledge of `STATE_DIR`**; all paths are injected, mirroring the existing `read_pid_state(path=PID_FILE)` test seam.
- **Why one split is justified:** the new logic is ~600-900 LOC of pure computation and file formatting; inlining would grow the monolith ~25% and couple tests to heavy packages. One companion module is the minimum split that creates the required "predictor separate from I/O" boundary. A package (`voicemode/`) is *not* justified in this milestone.
- **Import direction is acyclic:** `voice.py → voicemode_telemetry.py`, never the reverse. The worker re-execs `Path(__file__)` (1624), so `sys.path[0]` is the script directory in repo mode and `site-packages` in installed mode; a sibling `py-modules` entry works in both. `voice.py` should import names explicitly (`from voicemode_telemetry import RunTelemetry, ...`) so existing tests can keep patching `voice.<name>`.

**Fallback if the split is rejected:** put the same functions at the end of `voice.py`, keeping identical signatures and explicit path/clock parameters. The design below does not depend on the file boundary; only test import speed and monolith growth do.

---

## Architectural Patterns

### Pattern 1: Authority + Enrichment split (PID file vs status.json)

**What:** The existing PID file remains the single source of truth for *what state the app is in and whether it is alive*. `status.json` adds ETA/progress and is ignored unless its `pid` matches the live PID file entry and it has not expired.
**When to use:** Any migration where existing consumers must not break.
**Trade-offs:** Two files to keep consistent; occasionally a stale advisory value — acceptable because it is cosmetic. Prevents a crash from leaving the bar stuck in "Transcribing…".
**Rule:** Never write a new PID state string (see Anti-Pattern 2). Never let `status.json` say "recording" while the PID file is gone in a way the consumer trusts.

### Pattern 2: Single-writer, append-only ledger with reader-side tolerance

**What:** One worker process appends one JSON object line per run. Readers skip malformed/partial lines and never mutate the ledger. Rotation is rename-based and writer-only.
**When to use:** Crash-safe local metrics with no database.
**Trade-offs:** A SIGKILL loses the run record; a partial last line is tolerated rather than repaired. No locking needed because there is at most one recorder and appends are single `write()` calls.
**Example:**
```python
line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
with path.open("a", encoding="utf-8") as fh:
    fh.write(line)          # one write, no embedded newlines
    fh.flush()
    os.fsync(fh.fileno())   # once per run; cheap
```

### Pattern 3: Atomic replace for the status contract

**What:** Write a temp file in the *same directory* as `status.json`, flush+fsync, then `os.replace(tmp, final)`. Readers see the old or new complete document, never a torn write.
**When to use:** Any file polled by another process at 100 ms.
**Trade-offs:** One extra file per transition; orphan temp files possible after SIGKILL (clean on next start / age > 60 s).
```python
fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status-", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, separators=(",", ":"))
    fh.flush(); os.fsync(fh.fileno())
os.replace(tmp, path)
```

### Pattern 4: Telemetry as a best-effort observer (never on the hot path)

**What:** `RunTelemetry` methods are called from the worker's control flow, never from `Recorder._callback` (audio thread). Every public method wraps I/O in `try/except OSError` and flips an internal `enabled=False` after the first hard failure.
**When to use:** Instrumentation in a latency-sensitive utility.
**Trade-offs:** Failures are silent apart from one stderr line (which lands in `voice.log`). Correct trade: dictation must never fail because metrics did.

### Pattern 5: Pure predictor, injected I/O

**What:** `predict(...)` takes a list of records, config, progress and clocks; returns a prediction. It performs no I/O. `RunTelemetry` reads records once at run start and passes them in; after each segment it calls the same pure function with updated progress.
**When to use:** Statistics that must be unit-tested deterministically.
**Trade-offs:** Slightly more parameters; eliminates time/clock flakiness.

### Pattern 6: Stage timing accumulator

**What:** One mutable run object records monotonic timestamps at stage boundaries; the final record is assembled once in `finish()`. Avoid scattering ad-hoc `time.monotonic()` calls that are hard to test.
**When to use:** Multi-stage pipelines (finalize → load → N segments → insert).
**Trade-offs:** One more object threaded through the worker; far lower risk than parallel bookkeeping.

### Pattern 7: Fail-open contract versioning

**What:** Every persisted object carries `"schema": 1`. Readers ignore unknown fields and unknown schema versions (or read the known subset); writers only add fields. Breaking changes get schema 2 with dual-read support for one milestone.
**When to use:** A file another repo (dotfiles) consumes.
**Trade-offs:** Slightly larger payloads; enables independent deployment of app and bar.

---

## Data Flow

### Dictation Run Lifecycle (new instrumentation in bold)

```
Hotkey / `voice --toggle`
  └─ toggle_background_recording (1661-1706)
       ├─ reads PID state (authority)
       ├─ stop_tts (1689-1690)
       ├─ Popen background worker (1695-1703)
       └─ write_pid_state(proc.pid, "starting") (1704)     [unchanged]

Worker: run_background_recording (1709)
  ├─ **RunTelemetry.start()** → status.json {state:"starting", pid, run_id}
  ├─ build Recorder, install SIGUSR1/SIGTERM/SIGINT (1730-1738)
  ├─ write_pid_state(pid, "recording") (1739)
  ├─ **status {state:"recording", phase:"recording"}**
  ├─ recorder.start() (1743)
  ├─ loop (1757-1768): **heartbeat status every 5s** with elapsed duration
  ├─ SIGUSR1 → stop_requested
  ├─ write_pid_state(pid, "transcribing") (1774)
  ├─ **status {state:"transcribing", phase:"finalizing"}**
  ├─ recorder.stop_to_wav() (1776) → paths, wall duration
  ├─ **derive audio_s per segment (wave); predict initial ETA**
  ├─ **status {phase:"model_load", eta_epoch}**
  ├─ load_model(args) (1784)                      [cold load preserved]
  ├─ **telemetry.model_loaded(seconds, actual_backend) → refreshed ETA**
  ├─ for each segment (1791-1824):
  │    ├─ **status {phase:"segment", i/n, eta_epoch}; start timer**
  │    ├─ transcribe(...) (1805-1810)             [may fall back CPU]
  │    ├─ **segment_finished(decode_s); maybe corpus copy**
  │    ├─ **re-predict remaining → new eta_epoch**
  │    └─ finally: unlink temp WAV (1820-1824)     [after corpus copy]
  ├─ write_pid_state(pid, "typing") (1832)
  ├─ **status {state:"typing", phase:"inserting"}**
  ├─ insert_text(...) (1833)
  ├─ return 0
  ├─ except STTStageFailure / Exception (1843-1852) → **run.outcome="error", error_stage**
  └─ finally (1853-1865)
       ├─ **cleanup existing** (stop recorder, delete WAVs)
       ├─ remove_pid(pid) (1865)
       └─ **RunTelemetry.finish(outcome) → status idle + append ledger line**
```

**Ordering decision:** `finish()` runs last in `finally`, after cleanup and `remove_pid`, so the process can never advertise "idle" while it is still doing work; if `finish()` itself crashes, the missing PID file already makes the bar idle. `finish()` has its own `try/except` and cannot raise.

**Cancel path:** `cancel_requested` returns at 1770-1772; the same `finally` writes outcome `"cancelled"` and status idle, so a SIGTERM cancel leaves a ledger row (duration + no transcription) rather than a gap.

### Status Transition Table (PID file vocabulary unchanged)

| PID file `state` | status.json `phase` | When written | ETA present |
|---|---|---|---|
| `starting` (parent) | — (child not yet up) | parent after Popen (1704) | no |
| `starting` (child) | `setup` | worker entry, before mic init | no |
| `recording` | `recording` | after `recorder.start()` | no |
| `recording` | `recording` (heartbeat) | every ~5 s in loop | no |
| `transcribing` | `finalizing` | immediately after stop signal | no |
| `transcribing` | `model_load` | after `stop_to_wav`, before `load_model` | **yes** |
| `transcribing` | `segment` | before/after each segment | **yes** |
| `transcribing` | `inserting` | after last segment | **yes (short)** |
| `typing` | `inserting` | before `insert_text` | optional |
| *(removed)* | `done` / `error` | final status write | no |

`error` is expressed as `phase:"error"` with `state:"idle"` in the final write. Do **not** introduce `error` as a PID state.

### Prediction Data Flow

```
metrics.jsonl(.2,.1,active)
      │ read once at worker start (bounded tail, e.g. 500 records / 1 MB)
      ▼
load_recent_records() ──► list[dict]  (skip malformed lines, count skips)
      │
      ▼
predict_plan(records, config, recording_audio_s, now) ──► Prediction
      │   hierarchical key: full → minus chunk → (model,device,compute)
      │                     → (model,device) → (model,) → global prior
      │   components: model_load_s + rate_s_per_audio_s * audio_s
      │               + insert_s + finalize_s
      ▼
RunTelemetry.status(eta_epoch=now_wall + remaining_p75, eta_remaining_s, confidence)
      │
      ▼  after each segment
predict_remaining(prediction, progress, observed_segment_rates, now) ──► new ETA
```

### Status Bar Consumption (contract, external repo)

```
Voice.qml poll() [100 ms active / 2500 ms idle — 253-259]
  1. read recorder.pid  → state authority (existing logic 166-209 unchanged)
  2. read status.json   → if status.schema == 1
                           and status.pid == pid from recorder.pid
                           and status.state == pidState
                           and now < status.expires_at
                         then expose etaEpoch, etaRemainingS, progressText, confidence
                         else ignore status (fall back to existing behavior)
  3. VoicePill displayText:
       transcribing → "Transcribing 2/3 · 0:14" (countdown from eta_epoch)
       if eta_epoch already past → "Transcribing…" (clamp, never negative)
```

The bar must remain fully functional if `status.json` never appears (old app) or is stale (crash). This is the compatibility guarantee.

---

## State Machine Changes

**No changes to the PID state alphabet:** `starting → recording → transcribing → typing → idle`. This is mandatory, not stylistic:

- `toggle_background_recording` only special-cases `starting`, `transcribing`, and `recording` (1665-1684). Any new state falls through to `if pid: remove_pid(pid)` (1686-1687) and **spawns a second worker**, corrupting the mutual-exclusion guarantee.
- `Voice.qml` assigns unknown raw states directly to `sttState` (191-193) and its color/text switches have no default case (37-60), so a new state renders blank with default color.
- `check_daemon_pid_health` (2260-2277) and `--status` (1991-1999) assume the five states.

**What changes instead:** status.json adds a `phase` axis (`setup|recording|finalizing|model_load|segment|inserting|done|error`). The bar can show richer text without the state machine knowing about it.

**Sub-state additions are observational only:** they must never gate control flow in `voice.py` except where explicitly noted (e.g. watchdog telemetry). The worker's control flow continues to be driven by signals and exceptions, not by `status.json`.

---

## Persistence Boundaries

| Data | Location | Lifetime | Owner / writer | Notes |
|---|---|---|---|---|
| PID state | `$XDG_RUNTIME_DIR/voice-stt/recorder.pid` | login session | parent + worker (existing) | **authority**; unchanged |
| TTS PID | `$XDG_RUNTIME_DIR/voice-stt/tts.pid` | login session | TTS worker | unchanged |
| Logs | `$XDG_RUNTIME_DIR/voice-stt/{voice,tts}.log` | login session | existing | telemetry warnings land here via stderr |
| **status.json** | `$XDG_RUNTIME_DIR/voice-stt/status.json` | login session | **recorder worker only** | advisory; atomic replace; safe to delete |
| **metrics.jsonl** | `$XDG_STATE_HOME/voicemode/metrics.jsonl` (default `~/.local/state/voicemode/`) | persistent | recorder worker | append-only, schema 1 |
| **rotated ledger** | `.../metrics.jsonl.1`, `.2` | persistent | recorder worker | rename rotation at ~5 MB / ~20k lines |
| **outlier corpus** | `.../voicemode/corpus/<run_id>/` | persistent, capped | recorder worker (opt-in) | 0700; WAVs + `meta.json` |
| Temp WAVs / TTS text | `$XDG_RUNTIME_DIR/voice-stt/` or `tempfile` | until run ends | existing | corpus copies happen **before** deletion |

**Why this boundary:** `XDG_RUNTIME_DIR` is wiped on logout/reboot by spec and must not hold durable history; `XDG_STATE_HOME` is explicitly for state that persists across restarts (logs, history). The spec also requires creating missing destination directories with mode `0700`. `status.json` must stay in the runtime dir because the bar already derives that path from `XDG_RUNTIME_DIR` (Voice.qml 13-16).

**Directory permissions:** create `~/.local/state/voicemode` and `corpus/` with `0o700` (the fallback `/tmp/voice-stt-{uid}` risk noted in `.planning/codebase/CONCERNS.md` applies equally to metrics). Ledger and status contain timing/config/paths, not transcript text; corpus WAVs do contain speech and are opt-in.

**Configuration surface (env-first, matching existing patterns):**

| Variable | Default | Effect |
|---|---|---|
| `VOICE_METRICS` | `1` | `0` disables ledger writes (status still works) |
| `VOICE_STATUS` | `1` | `0` disables status.json writes |
| `VOICE_METRICS_DIR` | XDG state path | test/advanced override |
| `VOICE_CORPUS_CAPTURE` | `0` | opt-in outlier WAV copying |
| `VOICE_CORPUS_MAX_FILES` / `_MAX_MB` | `20` / `250` | per-run cap |
| `VOICE_PREDICT_PRIOR_RTF` | unset | override the placeholder prior |

The hotkey path (`voice --toggle`) cannot pass CLI flags, so worker behavior must be env-driven. CLI flags are for interactive use/reporting (`--report`, `--capture-corpus`), and only those explicitly forwarded by `background_argv` (1623-1658) reach the worker.

---

## Integration Points

### Consolidated Map

| # | Integration point | File:lines | New/Modified | Purpose |
|---|---|---|---|---|
| 1 | Path constants | `voice.py:44-88` | MOD | `STATUS_FILE`, `METRICS_DIR`, `METRICS_FILE`, `CORPUS_DIR`; reuse `STATE_DIR` |
| 2 | `ModelState` | `voice.py:90-94` | UNCHANGED | detect fallback by comparing final `requested_device`/`requested_compute_type` |
| 3 | `Recorder` | `voice.py:150-337` | UNCHANGED | segment audio duration read via `wave` in telemetry |
| 4 | `load_model` | `voice.py:631-643` | UNCHANGED | caller times; actual backend from `ModelState` |
| 5 | `transcribe` | `voice.py:646-680` | UNCHANGED | caller times; CPU fallback visible in returned state |
| 6 | `report_stt_failure` | `voice.py:712-796` | UNCHANGED | existing failure logging/notification |
| 7 | PID helpers | `voice.py:799-859` | UNCHANGED | authority |
| 8 | `transcription_watchdog_handler` | `voice.py:923-952` | MOD | optional run context; timeout status/ledger/corpus before `os._exit` |
| 9 | `insert_text` | `voice.py:1168-1214` | UNCHANGED | caller times insertion |
| 10 | `background_argv` | `voice.py:1623-1658` | MOD (small) | forward `--capture-corpus` / `--no-metrics` when explicitly passed |
| 11 | `toggle_background_recording` | `voice.py:1661-1706` | MOD (small) | clean stale `.status-*.tmp`; keep PID-only semantics |
| 12 | `run_background_recording` | `voice.py:1709-1865` | MOD (major) | instantiate `RunTelemetry`; instrument transitions/segments/finally |
| 13 | `print_status` | `voice.py:1991-1999` | MOD (optional) | print progress/ETA alongside PID |
| 14 | `run_terminal_mode` | `voice.py:2044-2121` | MOD (optional) | emit `kind:"stt", mode:"terminal"` records; no status writes |
| 15 | `check_daemon_pid_health` | `voice.py:2260-2277` | MOD (optional) | report stale/mismatched status.json |
| 16 | `kill_all_daemons` | `voice.py:2280-2302` | MOD (optional) | unlink stale `status.json` |
| 17 | `run_doctor` | `voice.py:2305-2419` | MOD (optional) | ledger writability + corrupt-line count |
| 18 | `parse_args` | `voice.py:2884-3085` | MOD | `--report`, `--report-format`, `--report-since`, `--report-out`, `--capture-corpus` |
| 19 | `main` | `voice.py:3088-3150` | MOD | dispatch report before `--record-background`/model work |
| 20 | `pyproject.toml` | `pyproject.toml:49-50` area | MOD | add `voicemode_telemetry` to `py-modules` |
| 21 | New module | repo root | NEW | schema, atomic I/O, predictor, reports, `RunTelemetry` |
| 22 | Tests | `tests/test_telemetry.py` | NEW | all new seams |
| 23 | Worker tests | `tests/test_audio_chunking.py:98-223` | MOD | patch `voice.RunTelemetry` (see Test Seams) |
| 24 | Watchdog test | `tests/test_hyprland_daemon.py:374-394` | MOD | new optional args passed by `threading.Timer` |
| 25 | Bar service | `Voice.qml:13-18, 54-67, 159-251` (external) | MOD | status FileView + ETA parse, PID authority retained |
| 26 | Bar pill | `VoicePill.qml:50-60` (external) | MOD | countdown text |

### Detailed Touchpoints in `run_background_recording` (1709-1865)

| Line(s) | Existing code | Change |
|---|---|---|
| 1709-1714 | locals, `pid`, `active_stage` | create `run_id`, capture `config` (`model`, `device`, `compute_type`, `beam_size`, `vad_filter`, `chunk_s`), instantiate `RunTelemetry`, call `start()` |
| 1736-1739 | signal handlers, PID "recording" | after PID write: `telemetry.state("recording", phase="recording")` |
| 1757-1768 | recording loop | heartbeat status every ~5 s with elapsed wall duration (compute from `recorder.started_at`); no audio-thread work |
| 1770-1772 | cancel return | set `outcome="cancelled"`; `finally` finalizes |
| 1774-1776 | PID "transcribing", stop to WAV | `telemetry.state("transcribing", phase="finalizing")`; time the finalize span |
| 1777-1781 | paths, duration, segment count | compute per-segment `audio_s` from WAV headers; total `audio_s`; store in run object |
| 1783-1784 | model load | `telemetry.state(phase="model_load")` **before**; time; `telemetry.model_loaded()` after; this is the dominant cold-start component |
| 1791-1819 | segment loop | `segment_started(i, n, audio_s)` before; time; `segment_finished(decode_s, ok=...)` after; `segment_failed` in `except` (1814-1817) |
| 1818-1824 | `finally` unlink | corpus copy must happen in `segment_finished`/`segment_failed` **before** this unlink; existing unlink logic unchanged |
| 1804-1810 | prompt chaining, transcribe | after call, compare `model_state.requested_device` with the run config to detect CPU fallback; record `fallback=true` and re-key predictor |
| 1826-1832 | concatenation, PID "typing" | `telemetry.state("typing", phase="inserting")`; predicted insert time ~ `len(text)` / typing rate |
| 1833-1837 | `insert_text` | time it; record success |
| 1842 | `return 0` | default `outcome="ok"` |
| 1843-1852 | exception handlers | `outcome="error"`; `error_stage=exc.stage or active_stage`; capture error type; **re-raise/return unchanged** |
| 1853-1865 | `finally` cleanup | after cleanup + `remove_pid`: `telemetry.finish(outcome)` inside its own try/except |

### Watchdog Integration (923-952)

Current signature:
```python
def transcription_watchdog_handler(pid, args, wav_path, timeout_seconds, started_at, expired)
```
Extend with optional trailing parameters:
```python
def transcription_watchdog_handler(..., expired, telemetry=None, segment_index=None)
```
- `run_background_recording` passes the run object and index at 1796-1800.
- The handler calls `telemetry.timeout(segment_index, elapsed)` before `os._exit(1)`; that helper writes a timeout status, a ledger record with `outcome:"timeout"`, and (if enabled) copies the recovery WAV. All bounded and exception-swallowed.
- Keep the existing call shape valid when `telemetry=None`, so the current test (374-394) only needs its expected `args` tuple extended.
- **Known limitation:** `os._exit` bypasses the main thread's `finally`; this watchdog write is the only record for a timeout. If even that fails, the retained WAV path in `voice.log` remains the fallback evidence (as today).

### Parent-Side Changes (1661-1706)

- **Do not write status.json from the parent.** Two processes writing the same contract invites out-of-order regressions; the child writes within milliseconds. The parent's existing `write_pid_state(proc.pid, "starting")` (1704) already covers the double-tap window (1665-1674).
- Add stale temp cleanup (`glob(".status-*.tmp")`, unlink older than 60 s) next to `STATE_DIR.mkdir` (1662), best-effort.
- Optionally write a provisional `status.json` **only if** a `run_id` is generated in the parent and passed to the child via a hidden `--run-id` arg. This is not required; prefer the simpler single-writer child.

### CLI / Report Integration (2884-3085, 3088-3150)

Add flags near the diagnostics group (2887-2901):
```
--report                     # print/emit a report from the ledger, then exit
--report-format {terminal,csv,html}   default terminal
--report-since DURATION      # e.g. 24h, 7d, 30d (or ISO date)
--report-out PATH            # default stdout; required-sensible for html
--capture-corpus             # opt-in for the next/background run
```
Dispatch in `main()` **before** `--record-background` and model loading (after the existing `--doctor`/`--verify` block, 3091-3100). `--report` must never import/load Whisper. Keep the existing `--json` flag for doctor/verify; do not overload it.

**Doctor additions (optional, 2305-2419):** check that `METRICS_DIR` is creatable/writable, count corrupt ledger lines, and report a `status.pid`/PID-file mismatch. These are warnings, not critical failures (a read-only home must not make `--doctor` fail).

---

## Predictor Design

### Key hierarchy (explicit, testable)

The predictor uses **component-specific keys**, because model load does not depend on beam/VAD/chunk size while transcription rate does.

```
rate_key(config) levels (first with n >= MIN_N=3 wins):
  L0 ("exact"):  (model, device, compute_type, beam_size, vad_filter, chunk_s)
  L1:            (model, device, compute_type, beam_size, vad_filter)
  L2:            (model, device, compute_type)
  L3:            (model, device)
  L4:            (model,)
  L5 ("prior"):  global placeholder

load_key(config):
  (model, device, compute_type) → (model, device) → (model,) → prior
```

- `chunk_s` is dropped first because granularity changes are common and should not invalidate all history; it still affects the *segment-overhead* term.
- `vad_filter` is dropped next, then `beam_size`.
- Device/compute are kept high in the hierarchy because CPU-int8 vs CUDA-fp16 is a 5-20× difference; never average across them.
- The chosen level, sample count, and key tuple go into both the prediction object and the final record (`prediction.key_level`, `prediction.n`).

### Statistical model

Predict **total post-stop latency**, not transcript time:

```
remaining = finalize_s + model_load_s + Σ(rate * segment_audio_s) + insert_s
```

- `rate` = seconds of decode per second of audio (RTF). This normalizes across recording lengths and segment counts.
- `model_load_s` is modeled separately; it is the cold-start spike the milestone specifically wants visible (keep the cold load, predict it).
- `insert_s` ≈ `len(text) / typing_rate`; a fixed conservative default is acceptable (the existing `--type-delay` default is 2 ms/char, 3030-3034, so insertion is usually small relative to decode).
- `finalize_s` ≈ small per-segment constant (WAV write/close), measured.

**Robust statistics:**
- Use `statistics.median` of per-record rates; reject `outcome != "ok"` records and records with nonsensical values.
- Winsorize the sample at the 10th/90th percentile before computing the median (or drop points beyond `3 × MAD` around the median).
- Require `n >= 3` at a hierarchy level; otherwise fall to the next level.
- Shrink toward the prior: `value = (n * median + k * prior) / (n + k)` with `k ≈ 4`. This prevents one fast run from producing an over-confident ETA.
- Clamp rates to a sane range (e.g. `0.02 … 20 s/audio-s`) so a corrupted record cannot produce a 3-hour ETA.
- `confidence`: `high` if `n >= 20` and `MAD/median < 0.25`; `medium` if `n >= 5`; else `low`.

**Priors (LOW confidence — placeholders to be replaced by measured data):**

| Model family | Prior RTF (CPU int8) | Prior load (s) |
|---|---|---|
| tiny | ~0.15 | ~1.5 |
| base | ~0.25 | ~2.5 |
| small | ~0.4 | ~5 |
| medium | ~0.8 | ~12 |
| large | ~1.6 | ~30 |

Device factors: `cpu=1.0`, `cuda=0.35`, `auto=1.0`. These are order-of-magnitude only; the first 5-10 runs should dominate quickly. Expose `VOICE_PREDICT_PRIOR_RTF` for manual tuning. Do not claim precision in docs.

**Why not a learned model:** the dataset is small, per-machine, and latency-sensitive; robust keyed medians with shrinkage are explainable, dependency-free, and degrade gracefully. No sklearn/numpy model training.

### Mid-run correction

After each segment completes:
```
observed_rate_i = decode_s / audio_s
run_weight      = done / (done + 2)                 # 0.33 after 1, 0.5 after 2, ...
blended_rate    = run_weight * median(observed_this_run) + (1-run_weight) * keyed_median
remaining_audio = Σ audio_s of not-yet-decoded segments
remaining       = 0 (load done) + blended_rate * remaining_audio + insert_est + finalize_est
eta_epoch       = wall_now + remaining_p75
```
- The current in-flight segment is included with its actual audio length; its decode time is not yet observed, so it uses the blended rate.
- Recompute at every `segment_started` and `segment_finished`.
- On GPU→CPU fallback (`transcribe` 666-680 returns a `cpu_state`), re-key to CPU and recompute immediately; record `fallback=true`.
- Use a **p75** (or median × 1.15) for the displayed `eta_epoch` so the countdown rarely reaches zero before completion; `eta_remaining_s` may carry the p50. The bar clamps at `0:00` anyway.

### Pure API (no I/O)

```python
@dataclass(frozen=True)
class Prediction:
    total_s: float
    remaining_s: float
    eta_epoch: float
    confidence: str          # low|medium|high
    source: str              # prior|calibrated|calibrated+midrun
    key_level: int
    n_samples: int
    components: dict[str, float]

def predict_plan(records, config, recording, now_mono, now_wall) -> Prediction: ...
def predict_remaining(prediction, progress, observed_rates, now_mono, now_wall) -> Prediction: ...
def record_observation(record) -> Observation: ...   # pure derivation for reports
```

`RunTelemetry` reads records once and calls these functions; it never embeds statistics.

---

## Report Generator Design

Shares the ledger reader (`load_records`) and the aggregation helpers used by the predictor.

**CLI:**
```
voice --report                          # terminal summary, last 50 runs
voice --report --report-format csv      # CSV to stdout
voice --report --report-format html --report-out ~/voice-report.html
voice --report --report-since 7d
```

**Terminal report:** overall counts (runs, ok/error/cancelled/timeout), success rate, p50/p90 absolute ETA error, p50/p90 RTF, cold-load p50, per-key table (model/device/compute/beam/vad/chunk, n, p50 RTF, p50 load, p90 total), recent runs (timestamp, duration, outcome, predicted vs actual), failure stages, outlier corpus count.

**CSV:** exactly one row per run, stable header order:
`run_id,started_at,outcome,mode,model,device,compute_type,beam_size,vad_filter,chunk_s,recording_s,audio_s,segments,model_load_s,transcribe_s,insert_s,total_s,predicted_total_s,abs_error_s,fallback`.
Use `csv.DictWriter`; escape via the module. This is the machine-readable contract for later analysis.

**HTML:** self-contained single file (inline CSS, no JS, no CDN). Escape every dynamic value with `html.escape`. Include the same tables plus a simple per-run latency bar (CSS width from `total_s / max_total`). Write atomically via the shared atomic-write helper (reuse the status helper with an explicit path) so a failed export does not clobber an existing report.

**Reader rules:** read rotated files oldest→newest, stop at `--report-since`, skip malformed lines, report `skipped_lines` and `unknown_schema` counts. Never raise on missing/corrupt ledger; print "no metrics recorded yet" with a hint.

---

## Outlier Corpus Design

**Opt-in only:** `VOICE_CORPUS_CAPTURE=1` (env) or `--capture-corpus` (forwarded to the worker). Off by default. Document privacy: WAVs contain speech.

**Capture decision** (in `segment_finished`/`segment_failed`, before the existing unlink at 1820-1824):
```
slow  = decode_s / audio_s > max(2.0 * keyed_p50_rate, keyed_p90_rate)
        or decode_s > 0.5 * stt_timeout_seconds()
        or watchdog/failure
```
- Copy with `shutil.copy2(wav_path, corpus/<run_id>/segNN.wav)`; if the user passed `--save-dir`, do **not** copy, just record the path.
- Write `corpus/<run_id>/meta.json` (schema 1): config, segment index/audio_s/decode_s, predicted rate, reason, run_id, timestamp. Atomic write.
- Caps: `VOICE_CORPUS_MAX_FILES` (20) and `_MAX_MB` (250) per run; prune oldest files/directories at run end; never fail the run if the cap or copy fails.
- Directory mode `0700`; no transcripts in meta (only char counts if useful).
- **Failure path:** corpus copy is attempted in `except` for a failed segment and in the watchdog helper. If the copy raises, log one line and continue to the normal unlink.

**Why before unlink:** the existing `finally` at 1818-1824 deletes the temp WAV whenever `should_delete` is true (the default with no `--save-dir`). Any copy after that would find nothing. The corpus hook must be inside the segment lifecycle, not in the final cleanup.

---

## Failure Modes

| # | Failure | Detection | Behavior | Mitigation / design rule |
|---|---|---|---|---|
| 1 | Partial ledger line after crash/power loss | `json.loads` fails for last line | Reader skips it; report counts `skipped_lines` | Single `write()` + fsync; never repair/rewrite in readers |
| 2 | Disk full / read-only home / permissions | `OSError` on append/status | One stderr warning; `RunTelemetry.enabled=False` for the rest of the run; dictation continues | All telemetry I/O wrapped; never raise from `finish()` |
| 3 | Status write interrupted | `os.replace` semantics | Reader sees old or new complete doc | Temp file in same dir; fsync before replace |
| 4 | Orphan `.status-*.tmp` after SIGKILL | glob on startup | Best-effort unlink if mtime > 60 s | `toggle_background_recording` cleanup |
| 5 | Process crash / SIGKILL leaves stale status | PID missing/dead, `status.pid` mismatch, `now > expires_at` | Bar falls back to PID authority → idle | Contract rule: status is advisory; `expires_at` per phase |
| 6 | Watchdog `os._exit(1)` skips `finally` | Timer fires (923-952) | Best-effort timeout record + status + corpus copy before exit | Extend handler with run context; bounded work; log fallback |
| 7 | Cancel (SIGTERM) | `cancel_requested` (1770) | `outcome:"cancelled"`, status idle | Flags read in `finally` |
| 8 | Old and new worker overlap during rapid cancel/restart | Two status writers | New writer's file may be overwritten by old writer | Consumers require `status.pid == pid_file.pid`; unique `run_id`; append-only ledger tolerates both |
| 9 | Wall-clock jump (NTP) | ETA drifts | Countdown off by the jump | Durations use `monotonic`; `eta_epoch` uses wall; also emit `eta_remaining_s` and `expires_at` |
| 10 | GPU→CPU fallback mid-run | Returned `ModelState.requested_device` changed (666-680) | Re-key predictor to CPU, ETA jumps, record `fallback=true` | Handled inside the segment loop; no special-case in `transcribe` |
| 11 | First run / empty ledger | `len(records)==0` | Prior-only ETA, `confidence:"low"`, `n_samples:0` | Never omit `eta_epoch` during `model_load`/`segment`; null only during recording |
| 12 | Corrupt/absurd historical record | Rate outside clamp range | Winsorized/dropped | Clamp + median + MAD |
| 13 | Unreadable WAV header | `wave.Error`/`OSError` | Fall back to `chunk_s` for that segment | `wav_duration_s` catches and returns estimate |
| 14 | `nvidia-smi` absent / no GPU | `shutil.which` is None | Do not probe; host block omitted; `device` in config is enough | **No required GPU probe**; optional host block behind an env flag |
| 15 | Corpus copy fails or caps exceeded | `OSError`, counters | Log, skip copy, still delete temp | Caps + per-run counters; never block dictation |
| 16 | Bar shows old app / no status.json | FileView empty | Existing PID-derived UI unchanged | Backward-compatible contract; no bar state-machine rewrite required |
| 17 | `XDG_RUNTIME_DIR` unset (fallback `/tmp/voice-stt-uid`) | env check | status written to fallback dir; bar may not find it | Pre-existing mismatch; document; bar simply falls back to PID behavior |
| 18 | Metrics schema v2 encountered by old reader | `schema > 1` | Ignore record or read known subset | Version field on every line; reader never asserts equality |

---

## Test Seams

1. **Path injection everywhere** (mirrors `read_pid_state(path=PID_FILE)` at 799): `append_record(record, path=...)`, `load_records(paths=..., limit=...)`, `write_status(payload, path=...)`, `atomic_write_json(path, payload)`, `copy_outlier(src, dest_dir=...)`. No function should read a module global path internally.
2. **Clock injection:** `RunTelemetry(..., mono=time.monotonic, wall=time.time)`; pure predictor takes `now_mono`/`now_wall`. Tests use a fake clock; no `sleep`.
3. **`RunTelemetry` constructor performs no I/O.** Methods write. This lets `run_background_recording` tests patch `voice.RunTelemetry` with a `MagicMock` in one line (see update list).
4. **Pure formatters:** `format_terminal(records, ...) -> str`, `format_csv(records) -> str`, `format_html(records) -> str`. Assert on substrings/CSV rows without file I/O.
5. **Atomicity test:** monkeypatch `os.replace` to raise; assert the old status file is intact and no exception escapes.
6. **Crash-safety test:** write a valid line, then a truncated JSON fragment; assert the reader returns one record and one skipped line.
7. **Rotation test:** lower the threshold via a parameter; append N records; assert `.1`/`.2` contents and chronological read order.
8. **Key-hierarchy test:** construct synthetic records at each level; assert the predictor picks the exact level when `n>=3`, then falls back, then uses the prior.
9. **Mid-run test:** fake `predict_plan`, feed observed segment rates, assert ETA decreases and honors the p75 rule.
10. **Watchdog test:** call the handler with a fake telemetry object; assert timeout status/record attempted before `os._exit` (which is already patched at `tests/test_hyprland_daemon.py:381`).

**Existing tests that will otherwise write to real directories:** `tests/test_audio_chunking.py:98-162` and `:163-223` patch `voice.write_pid_state`/`voice.remove_pid` but not new telemetry writers. Update them to patch `voice.RunTelemetry` (preferred) or `voice.append_record`/`voice.write_status`. This is mandatory in the phase that wires instrumentation, not an afterthought. `tests/test_hyprland_daemon.py:374-394` asserts the watchdog args tuple; extend its expectation for the new trailing args (or leave defaults and assert `None`). `tests/test_hyprland_daemon.py:396-438` asserts `mock_timer_factory.call_args.kwargs["args"][:4]`; trailing additions are safe.

**New test file layout:** `tests/test_telemetry.py` with classes `TestLedger`, `TestStatusContract`, `TestAtomicWrite`, `TestPredictor`, `TestReports`, `TestCorpus`, `TestRunTelemetryLifecycle`.

---

## Build Order

Dependencies are strictly left-to-right; phases 5 and 6 can overlap after phase 4.

### Phase 1 — Telemetry foundation (pure module, no wiring)

- Create `voicemode_telemetry.py`: schema constants (v1), `atomic_write_json`, `append_record`, `load_records`, rotation, `wav_duration_s`, `parse_duration`.
- Add `py-modules` entry.
- Tests: round-trip, partial line, rotation, atomic replace, permissions failure.
- **No runtime behavior change; ledger is not yet written.**
- Enables: everything else.

### Phase 2 — Status contract + `RunTelemetry` + worker instrumentation

- Define status schema v1 (fields below) and `RunTelemetry` (start/state/heartbeat/segment/finish; constructor no I/O).
- Wire `run_background_recording` (12 touchpoints above), including cancel/error/`finally`.
- Extend `transcription_watchdog_handler` with optional telemetry; update its test.
- Add path constants + env toggles in `voice.py:44-88`.
- **Do not touch PID states.** PID file writes remain exactly as today.
- Freeze the contract document `docs/telemetry.md` (or a section in README) so the dotfiles/bar work can start in parallel.
- Tests: transition sequence, atomic status, cancel outcome, no-write on disabled, existing worker tests patched.
- **Deliverable:** the bar can read `status.json` today; `eta_epoch` may be `null` until Phase 3. To avoid contract churn, include a **prior-only** ETA here (small `predict_prior`), so the field is always populated during `model_load`/`segment`.

### Phase 3 — Predictor (calibrated + mid-run)

- Pure predictor with key hierarchy, robust stats, shrinkage, confidence, priors.
- Read records once at worker start; compute initial ETA after `stop_to_wav`; refresh at model load and each segment; record prediction error.
- Detect CPU fallback and re-key.
- Tests: hierarchy, shrinkage, outliers, empty ledger, mitigation, mid-run monotonicity, p75.
- Depends on Phase 2 data flow and Phase 1 reader.

### Phase 4 — Report generator + CLI

- `--report` family in `parse_args`/`main`; terminal/CSV/HTML formatters sharing the reader.
- Tests for each format including empty/corrupt ledgers; dispatch test that `--report` never calls `load_model`.
- Depends on Phases 1 and 3 (uses prediction-error and aggregate helpers).

### Phase 5 — Outlier corpus capture

- Opt-in env/flag; segment decision; copy before unlink; caps; meta.json; watchdog/failure copies.
- Tests with temp WAVs: slow vs fast, cap, copy failure, `--save-dir` skip, watchdog path.
- Depends on Phase 2 (segment lifecycle) and Phase 3 (threshold uses keyed rate; a prior-only threshold is acceptable).
- Touches the hot path last, after instrumentation is stable.

### Phase 6 — Hardening, doctor, external bar

- `--doctor` telemetry/ledger checks; stale status cleanup; `--kill` status removal; docs/privacy.
- External dotfiles change: `Voice.qml` status FileView + `VoicePill.qml` countdown (contract already frozen in Phase 2). Keep PID fallback.
- Full suite, ruff, `voice --verify`; manual multi-minute dictation to validate ETA and timeout path.
- **Note:** the external bar change is in a separate repo; this project ships the contract and sample QML snippet, not the dotfiles commit.

**Parallelization:** Phase 4 (reports) and Phase 5 (corpus) are independent once Phase 3 lands. Phase 6's bar work can start after Phase 2's contract freeze. Do **not** start Phase 3 before Phase 2: a predictor without collected data and a status consumer is untestable in situ.

---

## Status / Ledger Schemas (v1, frozen at Phase 2)

### status.json (runtime, advisory)

```json
{
  "schema": 1,
  "run_id": "8b1c0f5e-...",
  "pid": 48213,
  "state": "transcribing",
  "phase": "segment",
  "updated_at": 1790000042.31,
  "expires_at": 1790000345.00,
  "recording": {"duration_s": 421.5, "chunk_s": 180.0, "segments": 3, "audio_s": 421.0},
  "progress": {"segment_index": 2, "segments_total": 3, "segments_done": 1, "segments_failed": 0},
  "eta_epoch": 1790000061.0,
  "eta_remaining_s": 18.7,
  "eta_confidence": "medium",
  "eta_source": "calibrated+midrun",
  "message": "Transcribing 2/3"
}
```

- `state` mirrors the PID vocabulary exactly.
- `phase` is the finer axis.
- `eta_epoch` is **Unix epoch seconds (float)** — the contract the bar counts down from.
- `expires_at` covers long blocking segments (set to segment start + watchdog timeout + margin); consumers ignore the file after it.
- `eta_*` may be `null` when not applicable (recording), never absent.
- No transcript text, ever.

### metrics.jsonl (state, one record per run)

```json
{
  "schema": 1, "kind": "stt", "mode": "background",
  "run_id": "8b1c0f5e-...", "started_at": 1790000000.0, "ended_at": 1790000061.4,
  "outcome": "ok", "error_stage": null, "error_type": null,
  "config": {"model": "medium.en", "device": "cpu", "compute_type": "int8",
             "beam_size": 1, "vad_filter": true, "language": "en"},
  "backend": {"requested": "cpu/int8", "actual": "cpu,int8", "fallback": false},
  "recording": {"duration_s": 421.5, "chunk_s": 180.0, "segments": 3,
                "sample_rate": 16000, "audio_s": 421.0},
  "timings": {"finalize_s": 0.8, "model_load_s": 14.2, "transcribe_s": 42.1,
              "insert_s": 1.3, "total_s": 61.4},
  "segments": [{"i": 1, "audio_s": 180.0, "decode_s": 17.2, "ok": true, "chars": 412, "watchdog": false}],
  "prediction": {"total_s": 58.0, "error_s": 3.4, "source": "calibrated+midrun",
                 "key_level": 0, "n_samples": 12, "confidence": "medium"},
  "corpus": [{"i": 2, "reason": "slow_outlier", "path": "corpus/8b1c0f5e.../seg02.wav"}],
  "host": {"cpu": "Intel ...", "gpu": null}
}
```

- `schema` is mandatory on every line. Additive fields are allowed within v1; readers ignore unknown keys.
- `host` is optional and must not require `nvidia-smi`; `cpu` can come from `/proc/cpuinfo` or be omitted.
- No text content; `chars` only. Document this explicitly in `docs/telemetry.md`.

---

## Scaling Considerations

| Volume | Adjustment |
|---|---|
| Typical use (~20-100 dictations/day) | One JSONL record (~0.5-1 KB) per run ≈ 7-35 MB/year; rotation at 5 MB keeps 2 backups (~15 MB cap). Tail read of 500 records is < 5 ms. |
| Heavy use (~500/day) | Rotation cap still bounds disk; predictor reads a bounded tail, not the whole ledger. Reports stream the full rotation set but are user-invoked. |
| Corpus enabled | Per-run caps (20 files / 250 MB) and oldest-first pruning; a 3-min 16 kHz mono WAV is ~5.5 MB, so 20 files ≈ 110 MB. |

**First bottleneck:** ledger growth, solved by rotation + tail reads. **Second:** corpus disk, solved by caps + pruning. There is no multi-user scaling concern (local desktop app).

---

## Anti-Patterns

### Anti-Pattern 1: Making `status.json` the state authority

**What people do:** Replace PID polling with status polling because it is richer.
**Why it's wrong:** A crash/`SIGKILL`/watchdog `os._exit` leaves a stale "transcribing" file and the bar hangs; the PID file's existence + `/proc` check is the only reliable liveness signal already implemented (Voice.qml 174-186).
**Do this instead:** PID file authoritative, status advisory with `pid`, `state`, and `expires_at` cross-checks.

### Anti-Pattern 2: Adding new PID state strings

**What people do:** Add `"finalizing"` or `"loading"` to the PID file for clarity.
**Why it's wrong:** `toggle_background_recording` only special-cases three states (1665-1684) and otherwise **spawns a second worker**; the bar's switches have no default (Voice.qml 37-60).
**Do this instead:** Add `phase` to status.json; leave the PID alphabet untouched.

### Anti-Pattern 3: Predicting with the mean of all runs

**What people do:** Average all durations, or mix CPU and CUDA runs.
**Why it's wrong:** One 5-minute outlier or a GPU run destroys the estimate; cold model load and steady-state rate have different shapes.
**Do this instead:** Component split + keyed medians + winsorization + shrinkage; separate load from rate.

### Anti-Pattern 4: Writing telemetry from the audio callback

**What people do:** Update status/metrics inside `Recorder._callback` (214-235).
**Why it's wrong:** Disk I/O and JSON serialization in the PortAudio callback cause dropouts; the callback already takes a lock.
**Do this instead:** The main worker loop samples elapsed time and writes at ~5 s intervals; segment writes happen between decodes.

### Anti-Pattern 5: Storing transcript text "for debugging"

**What people do:** Add `text` to the ledger or corpus meta.
**Why it's wrong:** Silent exfiltration of dictated passwords/messages into a persistent file; contradicts the project's local-privacy posture.
**Do this instead:** Character counts, flags, and opt-in WAVs only.

### Anti-Pattern 6: Re-reading the full ledger on every segment

**What people do:** `load_records()` inside `predict_remaining`.
**Why it's wrong:** O(history) per segment; grows without bound; adds latency exactly when the user is waiting.
**Do this instead:** Load once at run start; keep aggregates in memory; pure mid-run math.

### Anti-Pattern 7: Blocking shutdown on telemetry

**What people do:** fsync the ledger and status, then copy a 100 MB corpus, inside `finally` or the watchdog.
**Why it's wrong:** The user is waiting and the watchdog is trying to die; a slow/network home directory can hang the process.
**Do this instead:** Bound corpus copies, swallow errors, accept best-effort timeout records.

### Anti-Pattern 8: A second persistent daemon / model pre-warm

**What people do:** Introduce a resident process to avoid cold loads.
**Why it's wrong:** Explicitly out of scope; changes the whole lifecycle and failure model.
**Do this instead:** Keep the cold load and predict it; the ETA makes the wait legible.

---

## Sources

- `voice.py` (this repo): constants 44-88; `Recorder` 150-337; `load_model`/`transcribe` 631-680; failure reporting 712-796; PID helpers 799-859; watchdog 923-952; `insert_text` 1168-1214; `background_argv` 1623-1658; toggle 1661-1706; `run_background_recording` 1709-1865; `print_status` 1991-1999; terminal mode 2044-2121; doctor 2305-2419; `parse_args` 2884-3085; `main` 3088-3150.
- `tests/test_audio_chunking.py:98-223` — worker mocking pattern to extend.
- `tests/test_hyprland_daemon.py:190-438` — PID/signal/watchdog expectations.
- `tests/test_verification_doctor.py:20-75` — CLI dispatch test pattern.
- `.planning/codebase/CONCERNS.md` — monolith debt, cold-start bottleneck, `/tmp` permissions, missing daemon.
- `.planning/codebase/ARCHITECTURE.md` — detached worker and single-file patterns.
- `.planning/debug/long-stt-timeout-no-notification.md` — watchdog `os._exit` evidence and the 300 s timeout.
- `/home/pera/.config/quickshell/ii/services/Voice.qml` — polling cadence (253-259), PID authority (159-209), state mapping (20-30).
- `/home/pera/.config/quickshell/ii/modules/ii/bar/VoicePill.qml:31-60` — display state machine to extend.
- XDG Base Directory Specification v0.8 — `$XDG_STATE_HOME` default `$HOME/.local/state`, persistence, 0700 directory creation: https://specifications.freedesktop.org/basedir-spec/latest/
- Python `os.replace` atomic rename semantics: https://docs.python.org/3/library/os.html#os.replace

---

*Architecture research for: voicemode v1.1 Latency Prediction & Telemetry*
*Researched: 2026-10-25*

