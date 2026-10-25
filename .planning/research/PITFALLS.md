# Pitfalls Research

**Domain:** Latency prediction, local telemetry, and desktop status-bar countdowns for a local ML dictation pipeline (voicemode v1.1)
**Researched:** 2026-10-26
**Confidence:** HIGH for codebase/library behavior (verified against installed `faster-whisper` 1.2.1, CTranslate2 4.8.2, Quickshell 0.3.2 source and `voice.py`); MEDIUM for cross-hardware magnitudes and QML runtime edge cases; LOW for performance on hardware not tested.

This file is deliberately specific to this pipeline. Generic advice ("write tests", "handle errors") is omitted unless the pipeline makes it non-obvious.

---

## Scope and Phase Map

Phase numbering continues after v1.0's five phases. The roadmap may rename them; the ordering rationale is what matters.

| Phase | Name | Why it must come here |
|-------|------|-----------------------|
| **6** | Telemetry Ledger & Status Contract | You cannot predict or report what you did not define and timestamp. The ledger schema, clock domains, session identity, outcome enum, and atomic `status.json` contract must exist before any calibration or UI work. Getting these wrong invalidates all history collected later. |
| **7** | ETA Engine & Calibration | The predictor can only be built after real, correctly bounded samples exist. Outlier exclusion, cold/warm classification, config fingerprints, and chunk math belong here. |
| **8** | Quickshell ETA Integration | The bar consumes the contract; it must not invent timing, poll subprocesses, or own calibration. Depends on 6 (fields) and 7 (numbers). |
| **9** | Accuracy Report & Anomaly Capture | Needs a body of real sessions to be meaningful. Privacy, retention, report generation, and `xdg-open` behavior are separable from the live path. |
| **10** | Portability & Hardening | Cross-hardware/CUDA/model matrix and soak testing need the whole loop working. Also reserves the contract for TTS. |
| **v1.2** | TTS ETA | Explicitly out of scope now, but the Phase 6 contract must reserve a separate `tts` source so v1.2 does not break QML or the ledger. |

**Ordering rationale:** contract → predictor → consumer → report/capture → portability. Reversing 6 and 7 produces a predictor fitted to ambiguous numbers. Reversing 7 and 8 produces a UI that "feels" calibrated while the underlying data is wrong. Doing 9 before 7 produces a pretty report of poisoned data. Doing 10 last is deliberate: portability is verified by replaying the complete loop on other hardware, not by guessing at detection code.

---

## Evidence Base

These facts drive several pitfalls below. They were measured or read from the installed sources on the development machine on 2026-10-26.

| Evidence | Value | Consequence |
|----------|-------|-------------|
| User's clean samples | 30 s → 9.0 s; 60 s → 16.4 s; 115 s → 30.8 s; 180 s → 45.9 s; load 2.2–3.0 s | Affine relationship is real (slope ≈ 0.247, intercept ≈ 1.73 on a naive fit) |
| One pathological sample | 15 s → 47–65 s (temperature fallback) | One outlier can destroy a naive fit; see Critical 4 |
| Peak RSS | 2,129 MB | Low-memory machines swap/OOM; ETA assumptions break |
| `voice --status` | 0.44 s wall, 2.21 s user, 523 % CPU on this machine; user reports 1.15 s | A status subprocess is never a polling primitive; see Critical 11 |
| `voice` import breakdown | `sounddevice` 344 ms, `faster_whisper` 209 ms, `av` 140 ms; total import ≈ 757 ms | Heavy top-level imports in `voice.py:40-42` |
| CLOCK domains | `/proc/uptime` 31,947.66 s vs `time.monotonic()` 31,943.27 s (4.39 s delta after suspend) | QML boot-time math and Python monotonic math disagree; see Critical 2 |
| `faster-whisper` 1.2.1 | `transcribe()` runs VAD + feature extraction eagerly, returns `(segments_generator, info)`; decode happens during iteration | Timing the call times almost nothing; see Critical 1 |
| Temperature fallback | Default list `[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]`; chosen value exposed as `Segment.temperature` | Fallback is detectable per segment without storing text |
| CTranslate2 4.8.2 | `intra_threads=0` means "use a default", not "use all cores" | Core-count-based ETA is invalid; see Critical 18 |
| Quickshell 0.3.2 `FileView` | `watchChanges` defaults to **false**; `text()` with `blockLoading: true` performs a synchronous read when reloaded | Manual 100 ms reload is doing real I/O on the GUI thread; see Critical 12 |
| Quickshell `FileView` watcher | Watches both the file and its parent directory | Atomic `os.replace` is observable **if** `watchChanges: true` is set |

---

## Critical Pitfalls

### Pitfall 1: Timing the `transcribe()` call instead of the lazy decode

**What goes wrong:**
You add `t0 = perf_counter(); segments, info = model.transcribe(...); decode_ms = perf_counter() - t0`. This measures only VAD and feature extraction. The expensive work — the 9–46 s of encoder/decoder inference and temperature retries — happens while `segments` is iterated. The ledger records ~0.1–0.3 s of "decode" for every session, the ETA model learns a near-zero RTF, and every prediction is minutes too low.

**Why it happens:**
The public API looks synchronous (`segments, info = model.transcribe(...)`), and `transcribe()` itself is eager enough (VAD runs, features are built) that a stopwatch around it returns a plausible-looking non-zero number. Nothing errors, so the mistake survives review.

**How to avoid:**
- Time the *entire* consumption: `text = " ".join(seg.text.strip() for seg in segments)`. In this codebase that is already bundled at `voice.py:662-665`; put the marks outside that block, not inside it.
- Emit stage marks: `vad_features_ms` (around the `transcribe()` call), `decode_ms` (around the join), `load_ms` (around `load_model`), `finalize_ms` (around `stop_to_wav`).
- Add a unit test with a fake generator that sleeps between yields; assert the measured interval covers the sum, not just the first call.
- If you refactor for progress (needed for mid-flight ETA revision), iterate segments explicitly and record per-segment `end`, `temperature`, `avg_logprob`, `no_speech_prob` — never `text`.

**Warning signs:**
- `decode_ms` is suspiciously constant (~100–300 ms) across 30 s and 180 s clips.
- Predicted ETA for 180 s is seconds, while the log says 45 s.
- `sum(segment.end)` is 180 s but `decode_ms` is 0.2 s.

**Phase to address:**
**Phase 6.** The ledger must carry the stage marks from the first session; adding them later invalidates all prior samples and forces a re-baseline. Phase 7 consumes the marks.

---

### Pitfall 2: Mixing five incompatible clocks

**What goes wrong:**
The pipeline already touches at least five time sources:
1. `time.perf_counter()` / `time.monotonic()` in the worker (`voice.py:1795`, `275`, `292`).
2. `time.strftime('%Y-%m-%d %H:%M:%S')` wall-clock log headers (`voice.py:1693`, `1426`) — one-second resolution, **no UTC offset**.
3. `Date.now()` in QML (`Voice.qml:133`, `147`).
4. `/proc/uptime` + `/proc/<pid>/stat` start ticks in QML (`Voice.qml:119-139`), which is boot-time and includes suspend.
5. Persisted wall-clock timestamps in the new JSONL ledger.

Subtracting a Python `monotonic()` value from a QML `Date.now()` value, or sorting local timestamps across a DST boundary, produces durations that are wrong by seconds to an hour. On this machine `/proc/uptime` and `time.monotonic()` already differ by 4.39 s after a suspend, so the recording duration shown by the pill can disagree with `stop_to_wav()`'s duration.

**Why it happens:**
Every clock looks like "seconds since something" and works in isolation on a developer machine that never suspends, never changes timezone, and never runs NTP steps.

**How to avoid:**
- **Producer computes all durations.** `status.json` carries `recording_ms`, `elapsed_ms`, `eta_ms`, `updated_epoch_ms`; QML never subtracts a Python timestamp from its own clock to derive a duration.
- **Use `time.monotonic()`/`perf_counter()` for all in-process durations.** Never `time.time()` for elapsed math.
- **Persist wall time as ISO 8601 with a numeric offset** (`datetime.now().astimezone().isoformat()` → `2026-10-26T00:02:50.635357+06:00`) plus `epoch_ms` and `boot_id`. Keep numeric durations alongside; they are the source of truth.
- **`time.monotonic()` is system-wide on Linux** (same epoch across processes on one boot), so a stop-request timestamp written by the `--toggle` process *can* be subtracted by the worker. It is **not** comparable across reboots and QML cannot read it. Use it only for in-boot cross-process math; persist durations and wall time.
- For suspend-inclusive elapsed, use `time.CLOCK_BOOTTIME` deliberately and label it; do not mix it with `CLOCK_MONOTONIC` silently.
- Log headers should use the same ISO+offset helper as the ledger. Keep the human-readable header if desired, but never parse it for telemetry.

**Warning signs:**
- QML's displayed recording duration is 1–5 s longer than the worker's `duration` in the log.
- After resuming a suspended laptop, the pill's timer jumps.
- Report sorting looks wrong around a DST change; two rows have the same local time.
- A duration is off by exactly the UTC offset.

**Phase to address:**
**Phase 6** (clock domain and schema), **Phase 8** (QML must consume durations, not timestamps). Deferring this to the UI phase guarantees a rewrite of the contract.

---

### Pitfall 3: Measuring the wrong boundary (keypress vs SIGUSR1 vs typing vs PID removal)

**What goes wrong:**
"Actual latency" is ambiguous in this architecture, and each candidate boundary gives a different number:
- Hyprland keypress → `voice --toggle` **process start** → Python imports (`numpy`, `sounddevice`, `faster_whisper`) → read PID → `os.kill(SIGUSR1)`.
- Worker receives SIGUSR1 → `write_pid_state("transcribing")` (`voice.py:1774`) → `stop_to_wav` joins writer threads → model load (`voice.py:1784`) → decode → `insert_text`.
- `insert_text` always copies to the clipboard, then types with `type_delay` (default 2 ms/char, `voice.py:1052`); a 500-character transcript spends ~1–2 s in `wtype` *after* the text is ready.
- PID removal (`voice.py:1865`) happens after insertion.

If the ledger uses PID disappearance as "actual", it measures typing and insertion, not transcription. If it uses SIGUSR1 receipt as `t0` while the pill appears after that, the user's perceived wait includes the 0.4–1.1 s `--toggle` startup that nobody measured. The report then shows a systematic error that is not the predictor's fault, and calibration absorbs it.

**Why it happens:**
There is no single timestamp at the user's keypress inside the worker. POSIX signals carry no payload, and the obvious end-of-process signal (PID file removal) is after the UI work.

**How to avoid:**
- Define and document two metrics:
  - `text_ready_ms`: worker SIGUSR1 receipt → decode fully consumed. This is what the ETA predicts.
  - `e2e_ms`: `--toggle` monotonic stop timestamp (written to a sidecar file or the status contract) → decode done. This is what the user feels.
- Record `stop_dispatch_ms` separately: toggle process start → SIGUSR1 sent. It will be ~0.4–1.1 s today because `--toggle` imports the heavy module; do not silently blame the ETA for it. (Lazy imports are a separate optimization; measure first.)
- Record `insert_ms` and `insert_ok` separately; exclude insertion from decode calibration, but include it in the user-facing breakdown.
- Have the worker write a terminal status *before* PID removal so the bar and ledger agree.
- In the report, compare the ETA to `text_ready_ms` for the same `t0` definition used when the ETA was shown.

**Warning signs:**
- Report error is consistently +1 to +3 s across all sessions, roughly equal to typing time.
- Two teams of numbers disagree: log "Stopped ... Transcribing" vs the pill's countdown.
- Adding `--type-delay 0` changes "ETA accuracy" without changing decode time.

**Phase to address:**
**Phase 6.** This is a definition problem, not a UI problem. The ledger must record all stage marks from day one; Phase 7 chooses which one the headline metric uses, and Phase 8 labels the phases honestly.

---

### Pitfall 4: One temperature-fallback outlier destroys calibration

**What goes wrong:**
The four clean samples fit `eta ≈ 1.73 + 0.2472 × audio_s`. Add the measured pathological sample (15 s → 55 s) and a naive least-squares fit becomes `eta ≈ 25.7 + 0.0717 × audio_s`: it predicts **27.8 s for a 30 s clip that actually takes 9.0 s**, and **38.6 s for 180 s that actually takes 45.9 s**. The predictor is now wrong in both directions. If the anomalous session is also used for evaluation, the report can look acceptable on average while every ordinary dictation is badly mispredicted.

The mechanism is real in this pipeline: `faster-whisper` 1.2.1 retries each 30 s window over `[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]` when compression ratio > 2.4 or average logprob < −1.0. Music, noise, long pauses, and hallucination loops trigger it. `beam_size=1` reduces the cost per attempt but does not prevent six attempts.

**Why it happens:**
Least squares is the default, four points look like "enough", and the outlier is a *real* observation, so dropping it feels like cheating. The outlier is also rare, so it hides in a small sample until it dominates the slope.

**How to avoid:**
- **Separate "what happened" from "what calibrates".** Record every session with an `outcome` (`ok`, `no_speech`, `timeout`, `cancelled`, `insert_failed`, `gpu_fallback`, `anomaly`) and an `anomaly_reason`. Calibration uses only `ok` + `warm` + matching config.
- **Use a robust estimator, not OLS.** The simplest defensible model is: `load_ms = median(recent load_ms)`; `rtf = median(decode_ms / audio_s)`; `eta = load + rtf × audio`. On the clean data with a measured 2.4 s load, per-sample RTF is `[0.220, 0.233, 0.247, 0.242]`, median **0.2375**; the 15 s/55 s sample has RTF ≈ 3.5 and is ignored by the median.
- Detect fallback at the segment level: `Segment.temperature > 0` means at least one retry won; `compression_ratio` and `avg_logprob` corroborate. Store the count of fallback segments and the maximum temperature, never the text.
- Keep anomalies in the ledger and show them in the report as distinct points; do not silently delete them.
- Do not "winsorize" and then evaluate on the winsorized data; report raw error too.

**Warning signs:**
- Fitted slope changes by >20 % when one session is added.
- `actual / predicted` is bimodal; one cluster around 1.0, another around 3–10.
- The report's average error is acceptable but ordinary sessions are consistently late/early.
- `Segment.temperature` distribution has a spike at 1.0.

**Phase to address:**
**Phase 6** records `outcome` and per-segment fallback evidence; **Phase 7** owns the estimator and exclusion policy. Phase 7 cannot recover data Phase 6 failed to record.

---

### Pitfall 5: Folding model load into the slope, then extrapolating below the calibration range

**What goes wrong:**
A two-parameter fit on 30–180 s samples puts the fixed load into the intercept (1.73 s on the clean data), while the actual measured load is 2.2–3.0 s. For 180 s the error is hidden in the slope; for a 5 s clip the prediction is ~3 s when the true cost is load + decode ≈ 3.6–4.2 s. Short clips are common (single words, corrections), so the ETA is systematically optimistic exactly where the user is most likely to notice. Extrapolating the same line to a 0.3 s accidental tap can produce a negative or sub-second ETA.

**Why it happens:**
The data range is narrow relative to the intercept, so the fit trades intercept against slope and still looks excellent (four points, two parameters, near-perfect R²). R² on four points is not evidence.

**How to avoid:**
- Measure `load_ms` explicitly around `load_model()` and use the measured value (median of matching sessions), not the fitted intercept.
- Model `eta = max(load_floor, load_median) + rtf_median × audio_s + per_chunk_overhead × n_chunks`.
- Clamp: `eta >= 1.0 s` while working; `eta <= watchdog_remaining`; never negative.
- Treat sub-2 s audio as a special short-clip bucket, or show "a few seconds" rather than a precise integer.
- Keep a separate `finalize_ms` term; it is near-zero at 16 kHz but seconds at 44.1 kHz (see Critical 13).
- Validate with leave-one-out on the four clean points; with n=4, report the errors, not a confidence interval.

**Warning signs:**
- 180 s predictions are good but 5–15 s predictions are consistently 30–50 % low.
- A 0.3 s clip shows a 0 s or negative ETA.
- Fitted intercept is far from measured `load_ms`.

**Phase to address:**
**Phase 7.** This is the predictor's structure. Phase 6 must record `load_ms`/`finalize_ms` so the structure is possible.

---

### Pitfall 6: Calibration contamination across configs and hardware

**What goes wrong:**
CPU int8 `medium.en`, CUDA float16 `large-v3`, `beam_size=1` vs `5`, VAD on/off, and `chunk_seconds=180` vs `60` are different performance regimes. Pooling them produces a number that is wrong for all of them. A specific trap in this code: `ModelState.requested_device` stores `args.device`, so `device="auto"` (which CTranslate2 resolves to CUDA when available) is recorded as `"auto"`, not as `"cuda"`. Calibration then mixes CPU and GPU sessions. The existing `actual_backend(model)` (`voice.py:621-628`) already knows how to read the resolved device and compute type — use it, not the requested values.

**Why it happens:**
The user-visible setting is the natural key, and `"auto"` feels like a hardware-independent label. In practice it is the most hardware-dependent setting in the app.

**How to avoid:**
Fingerprint every session with, at minimum:
- `model_arg` (name or path) **and** resolved model path basename + file size + mtime (do not hash 1.5 GB in the hot path).
- Resolved `device` and `compute_type` from `model.model.device` / `actual_backend()`, not `args`.
- `beam_size`, `vad_filter`, `language`, `condition_on_previous_text`, `initial_prompt` presence (boolean only).
- `chunk_seconds`, effective `cpu_threads` / `OMP_NUM_THREADS`, `num_workers`.
- `faster-whisper` and `ctranslate2` versions, kernel/arch, logical CPUs, affinity, cgroup CPU quota.
- Load class: `loadavg` and `MemAvailable` at session start (for exclusion, not necessarily for the bucket key).

Only calibrate within an exact fingerprint match. If no bucket exists, use the prior (Critical 19), not another bucket's median. Version the predictor (`eta_model_version`) so a formula change does not mix with old observations.

**Warning signs:**
- Scatter plot shows two distinct clouds (CPU vs CUDA) in one bucket.
- Deleting one env var (`OMP_NUM_THREADS`) shifts accuracy by 30 %.
- A model swap (medium.en → small.en) leaves the ETA unchanged.
- Two sessions with the same audio duration differ by 5×.

**Phase to address:**
**Phase 6** records the fields; **Phase 7** implements bucketing and the no-bucket fallback; **Phase 10** validates the matrix on other machines/models.

---

### Pitfall 7: Cold page cache and CUDA first-call costs

**What goes wrong:**
Load is 2.2–3.0 s with the model warm in page cache. On the first run after boot, on a spinning disk or a network home, or after memory pressure evicted the pages, load can be 5–20 s. On CUDA, the first decode also pays context creation and cuDNN autotuning, which is not in `load_model()` at all. The ETA shown immediately is therefore optimistic on exactly the runs where the user is most likely to be watching (first session of the day), and the ledger's "warm" calibration absorbs a 10 s load as if it were decode.

**Why it happens:**
Development machines have the model cached and the GPU warm; the measurement loop rarely sees a cold start. `load_model()` timing looks stable, so the variation is attributed to "noise".

**How to avoid:**
- Record `load_ms` separately and classify `cold` (first session since boot, or `load_ms > 2 ×` the fingerprint median). Keep cold sessions in the report but out of warm calibration.
- On CUDA, record a `first_decode` flag and exclude the first decode of a newly loaded model from RTF calibration, or add a fixed warmup term to the ETA.
- For the first-run bootstrap, use a conservative prior (e.g., load prior 3.0 s CPU / 8 s CUDA, RTF prior by model class) with a 1.2× margin for the first few sessions.
- Do not claim a warm ETA on a cold machine; the report's "cold start" rows explain the early overruns.
- If `MemAvailable` is below ~2.5 GB (peak RSS measured 2,129 MB), warn and add margin; an OOM kill leaves stale state (Pitfall 10).

**Warning signs:**
- `load_ms` histogram has two modes (e.g., 2.5 s and 12 s).
- The first session of the day is 2–5× slower; subsequent ones are normal.
- CUDA sessions show a huge first `decode_ms` followed by fast ones.
- An OOM-killed session has no terminal record.

**Phase to address:**
**Phase 7** (classification and priors); **Phase 6** must record `load_ms`, `first_decode`, and memory/load context. **Phase 10** verifies cold-start on other machines.

---

### Pitfall 8: Non-atomic `status.json` plus two sources of truth

**What goes wrong:**
`write_pid_state()` uses `Path.write_text()` (`voice.py:819-821`), which truncates then writes. A 100 ms poller can read an empty or partially written file. If `status.json` is written the same way, QML occasionally sees invalid JSON and falls back to idle or keeps a stale ETA. The existing PID file and the new `status.json` are two sources of truth: they will disagree during transitions (e.g., PID says `transcribing`, status says `typing`), and readers will implement different precedence rules.

**Why it happens:**
`write_text` is the obvious Python API; the reader "handles" empty content by returning idle, which masks the race on the write side. Adding a second file feels additive, but it creates a consistency problem.

**How to avoid:**
- Write `status.json` to a temp file **in the same directory**, `fsync` on state transitions (not every heartbeat), then `os.replace()`. Same directory avoids `EXDEV`. Keep it mode `0600`.
- One writer per session (the worker). The launcher may write an initial `starting` record only if no live session exists; the worker owns all subsequent writes.
- Version the contract (`schema_version: 1`), include `session_id`, `pid`, `pid_start_ticks`, `state`, `phase`, `updated_epoch_ms`, durations, and an `error` object. Keep it under ~600 bytes.
- Define precedence explicitly: `status.json` wins **only if** its `session_id` matches a live PID/cmdline and `updated_epoch_ms` is fresh; otherwise fall back to the PID file, then idle.
- During migration, keep the PID file for signals and backward compatibility, but have the bar read the new contract. Remove the dual read in a later phase.
- Do not write `NaN`/`Infinity`: `json.dumps` emits `NaN` by default, which `JSON.parse` rejects. Use `allow_nan=False` and sanitize.

**Warning signs:**
- Occasional one-frame "idle" flicker at state transitions.
- QML logs `Unexpected token` / `JSON.parse` errors.
- PID file and status file disagree in a captured snapshot.
- A `.tmp` file is left behind after a crash.

**Phase to address:**
**Phase 6.** This is the contract phase. **Phase 8** implements the consumer's precedence and malformed-JSON fallback.

---

### Pitfall 9: Duplicate/orphan workers overwrite each other's state

**What goes wrong:**
There is a real race in `toggle_background_recording()` today (`voice.py:1661-1706`):
1. The launcher writes PID state `"starting"` for the child.
2. On a second keypress, if the state is still `"starting"`, it waits 300 ms (`voice.py:1667`).
3. The child must import `numpy`, `sounddevice`, `faster_whisper` before it can write `"recording"` — measured ~0.4–0.8 s on this machine, longer on a cold cache or loaded system.
4. After 300 ms, neither the `"transcribing"` nor `"recording"` branch matches; execution falls through to `remove_pid(pid)` and spawns a **second** worker (`voice.py:1686-1705`).
5. Both workers write the same PID file and (after this milestone) the same `status.json`. The first worker is now unstoppable and its later `"recording"` write can clobber the second's PID. Its ETA/status can overwrite the second session's.

This is a pre-existing lifecycle bug, but telemetry makes it visible and dangerous: two sessions, one PID, interleaved ledger lines, and an ETA that resets or points at the wrong process.

**Why it happens:**
The 300 ms mitigation assumes the child becomes `"recording"` quickly; the actual cold-start cost is dominated by module imports and is larger than the timeout.

**How to avoid:**
- Never `remove_pid()` a live `"starting"` process whose cmdline matches. Extend/loop the wait, or return "still starting, please wait" instead of spawning.
- Introduce a state lock (`flock` on `$XDG_RUNTIME_DIR/voice-stt/state.lock`) around read-decide-spawn; the loser exits.
- Give every session a `session_id` (`uuid4`, not a second-resolution timestamp) and `pid_start_ticks`. Writers include it; readers ignore a status whose `session_id` does not match the live PID.
- In the worker, before writing `"recording"`, verify that the PID file still contains *its own* PID; if not, exit quietly rather than clobber.
- Clean orphan test: force a double-tap during cold start and assert exactly one `voice --record-background` survives.

**Warning signs:**
- `pgrep -af 'voice.*record-background'` shows two processes.
- PID file flaps between two PIDs.
- ETA resets to a larger number mid-session.
- Two ledger rows with overlapping `started_at` and the same `session_id` prefix.

**Phase to address:**
**Phase 6** (session identity, single-writer rule, status validation) and **Phase 8** (consumer ignores mismatched sessions). The lifecycle fix itself can be a small Phase 6 hardening task; do not let it leak into the predictor.

---

### Pitfall 10: Stale state after crash, watchdog, cancel, or SIGKILL — and failures that look like success

**What goes wrong:**
Several exit paths leave no honest terminal state:
- The watchdog calls `remove_pid(pid)` then `os._exit(1)` (`voice.py:923-951`), bypassing `finally` and writing no failed status.
- Cancel returns early (`voice.py:1770-1772`) and the `finally` removes the PID but does not write a terminal `cancelled` record.
- SIGKILL/OOM leaves both the PID file and `status.json` frozen at `transcribing`.
- QML interprets any PID disappearance while `transcribing` as `typing` (`Voice.qml:181-185`, `202-204`), so a timeout, crash, or failed insertion is displayed as "Typing..." and then a success wrap-up.

The ETA can count down, the process can die, and the bar can show "done". The ledger may have no row at all, so the report silently omits failures.

**Why it happens:**
The existing lifecycle was designed around "PID gone = finished", with a typing linger for UX. Extending it with a second state file makes every abnormal exit a stale-state hazard.

**How to avoid:**
- Write a terminal status (`done`, `error`, `cancelled`, `timeout`, `no_speech`) **before** removing the PID, including `error.stage` and `error.type` (no transcript).
- In the watchdog, write the terminal status before `os._exit(1)`; if the write fails, still remove the PID.
- In `finally`, if no terminal status was written, write `error` with the active stage.
- Give `status.json` a TTL (`updated_epoch_ms`) and have QML require `state != transcribing || age < ~5 s`; after that, show an error/idle, not typing.
- On worker start, if an existing status has a dead PID or is older than the TTL, replace it; if it has a live PID, do not touch it (see Pitfall 9).
- Test: SIGKILL mid-transcription, SIGTERM mid-recording, watchdog timeout, `insert_text` failure — assert the bar ends in an error, not a wrap-up.

**Warning signs:**
- Bar shows "Typing..." after a crash.
- A stale `status.json` survives a reboot/login.
- Report row count is much lower than the number of keypresses.
- `voice --status` says idle while the bar shows transcribing (or vice versa).

**Phase to address:**
**Phase 6** (terminal writes, TTL, session identity) and **Phase 8** (QML error states and debounce). This must be fixed before the report is trusted.

---

### Pitfall 11: Polling `voice --status` from the status bar

**What goes wrong:**
`voice.py` imports `numpy`, `sounddevice`, and `faster_whisper` at module top (`voice.py:40-42`). Measured `voice --status` on this machine: **0.44 s wall, 2.21 s user CPU, 523 % CPU**. The user reports 1.15 s. Calling it every 100 ms is impossible (it would need 4.4 wall-seconds per second and ~22 CPU-seconds per second); even at the idle 2.5 s cadence it consumes ~18 % of wall time and ~88 % of one core, per bar instance. On a laptop this is a battery and fan issue, and it competes with the very transcription the ETA is predicting.

**Why it happens:**
The CLI is the existing interface and `--status` looks cheap. The cost is hidden in imports, not in the status logic. `sounddevice` alone is ~344 ms because importing it initializes PortAudio; `faster_whisper`/`av` add ~350 ms.

**How to avoid:**
- **Never spawn a process from the bar.** Read files with `FileView`, or read `status.json` directly.
- If a CLI status is still needed for humans, make it a separate stdlib-only entry point (e.g., `voice-status`) or move heavy imports inside the functions that need them. Do not import `sounddevice`/`faster_whisper` for a state read.
- Add an import-time regression check to CI (`python -X importtime -c "import voice"` or a wall-clock budget on the status command). The current 0.4–1.1 s is already a UX problem for `--toggle` (Pitfall 3).
- Measure the status path on battery and with a cold cache, not just on the dev machine.

**Warning signs:**
- `ps`/`htop` shows a Python process spawning every 100 ms or every few seconds.
- Shell fans spin up when the bar is idle.
- `voice --status` wall time > 100 ms in any environment.
- Battery life drops after the status integration.

**Phase to address:**
**Phase 6** (module/CLI split and import budget) and **Phase 8** (no subprocess in QML). Adding telemetry to the existing `voice.py` without this split will make the problem worse.

---

### Pitfall 12: 10 Hz file I/O and QML layout churn

**What goes wrong:**
`Voice.qml` polls every 100 ms while active and calls `reload()` on the PID file, TTS PID, two `/proc/<pid>/cmdline` files, `/proc/<pid>/stat`, and `/proc/uptime` (`Voice.qml:159-259`). With `blockLoading: true`, `FileView.text()` performs a **synchronous** read when reloaded (verified in Quickshell's `FileView` source: `shouldBlockRead()` → `loadSync()`), so this is real GUI-thread I/O, not just a property read. Add a 1–2 KB `status.json` read and a JSON parse at 10 Hz, then bind `eta` into `displayText`, `implicitWidth`, and the bar layout: every tick can relayout the bar and shift other items.

**Why it happens:**
The existing 100 ms loop is already there and works on tmpfs. `FileView` looks reactive, so it is easy to assume it caches; the `watchChanges` property defaults to **false** (Quickshell 0.3.2 source: "defaule false"), so the current code is manually reloading precisely because auto-watch is off.

**How to avoid:**
- Keep `status.json` in `XDG_RUNTIME_DIR` (tmpfs), never on a disk-backed path; it is ephemeral by design.
- Set `watchChanges: true` on the status `FileView` and `onFileChanged: reload()`; add a slow fallback poll (1 s) for inotify limits/network FS.
- Stop calling `reload()` on the status file every 100 ms. Keep the 100 ms timer only for local countdown interpolation if needed, or update the integer once per second.
- Update the ETA string at 1 Hz, not 10 Hz. Use a fixed/minimum label width and tabular figures; do not let `implicitWidth` change every second.
- Do not add the ledger, report, or per-segment history to `status.json`; the file must stay tiny.
- Debounce malformed reads: keep the last good state for 2–3 consecutive failures before falling back to PID/idle. A single empty read during `os.replace` must not blank the pill.
- Keep `printErrors: false` but log once on a parse failure; do not `console.warn` every tick.

**Warning signs:**
- The whole bar jitters or other modules shift when the ETA appears.
- Quickshell CPU usage rises from ~0 % to several percent while transcribing.
- Journal spam from `FileView`/`console.warn`.
- The ETA label changes width every second (e.g., 9s → 10s → 9s).

**Phase to address:**
**Phase 8.** The contract (Phase 6) should already be small and tmpfs-resident.

---

### Pitfall 13: Chunk-boundary and finalization math

**What goes wrong:**
`Recorder` splits by sample count at `actual_sample_rate` (`voice.py:169`, `223-235`), then resamples to 16 kHz in the writer thread (`voice.py:184-203`). Consequences:
- The final chunk is a partial (e.g., 180 s + 37 s); a `ceil(total/180) × per_chunk` estimate overcounts the last chunk.
- On devices that fall back to 44.1 kHz (`voice.py:255-272`), `np.interp` resampling of ~8 M samples per chunk runs in the writer thread and `stop_to_wav` joins those threads (up to 10 s, `voice.py:311-312`). Finalization can add seconds before the model even starts; a 16 kHz-calibrated ETA misses it.
- `stop_to_wav` can return fewer chunks than expected if a writer thread times out or the disk is full; `total_chunks` is only authoritative after finalization.
- `duration` from `stop_to_wav` is recording wall time (`voice.py:292`), not audio duration; PortAudio xruns (`Recorder.statuses`) can drop frames.
- `VOICE_CHUNK_SECONDS` / `--chunk-seconds` can change the chunk size, invalidating a 180 s calibration.
- `initial_prompt` chaining and `condition_on_previous_text` change later-chunk behavior.

**Why it happens:**
The clean measurements are all single chunks at 16 kHz, so chunk overhead and resampling are invisible. The code's unit tests use 0.1 s chunks and mocked streams (`tests/test_audio_chunking.py:66-96`), not 44.1 kHz real audio.

**How to avoid:**
- Use the actual WAV duration (`nframes / framerate`) once finalized; before that, use the recorded wall duration as a provisional estimate and mark it `provisional`.
- Compute expected chunks from the provisional duration for the *initial* ETA, then refine with actual chunk durations after `stop_to_wav`; record `chunks_expected` vs `chunks_transcribed`.
- Record `finalize_ms`, `input_sample_rate`, `resampled` (bool), and per-chunk `audio_ms` / `decode_ms`.
- Add a per-chunk overhead term and key calibration on `chunk_seconds`.
- Because VAD runs eagerly inside `model.transcribe()`, `info.duration_after_vad` is available *before* decoding. Refactor the wrapper to expose it (or compute the refined ETA inside `transcribe`) so silence-heavy clips can revise the ETA downward early. Do not run a second VAD pass just for telemetry.
- Test the 44.1 kHz path and a multi-chunk session explicitly; assert the ETA includes finalization.

**Warning signs:**
- Predictions are excellent at exactly 180 s and poor at 185 s.
- 44.1 kHz machines report a 2–5 s unexplained gap before "Loading faster-whisper".
- The ETA is low by roughly one chunk on long recordings.
- `chunks_transcribed < chunks_expected` in the ledger.

**Phase to address:**
**Phase 7** (model and refinement); **Phase 6** records per-chunk and finalization fields; **Phase 10** validates the 44.1 kHz and multi-chunk paths.

---

### Pitfall 14: Anomaly capture changes the latency it is measuring

**What goes wrong:**
"Opt-in capture of anomalously slow segments" tempts you to copy each 5.76 MB WAV (180 s × 16 kHz × 16-bit mono) into a capture directory inside the timed path, or before the `finally` unlink (`voice.py:1818-1824`). The copy adds I/O and CPU to the exact latency you are measuring; enabling capture makes sessions slower and can create the anomaly it is supposed to record. If the temp WAV is on tmpfs and the capture directory is on disk, `os.rename`/`os.link` fails with `EXDEV`, forcing a slow copy. The `finally` unlink can race with the copy.

**Why it happens:**
The chunk is deleted immediately after transcription, so "save it" feels like it must happen before deletion. Copying is the obvious implementation.

**How to avoid:**
- Record `t1` (decode done) **before** any capture I/O; never include capture time in `decode_ms`/`actual_ms`.
- If the temp directory and capture directory are on the same filesystem, `os.link` (hardlink) or `os.rename` is effectively free; do it before the unlink. If not, copy *after* the timestamp, asynchronously, with a size cap.
- Or opt in to a "quarantine" directory at session start and keep only anomalous chunks; discard the rest after the session. This retains audio during transcription only when explicitly enabled.
- Default off; require an explicit flag/env (`--capture-anomalies`, `VOICE_CAPTURE_ANOMALIES=1`); print the destination; check `statvfs` free space; cap size/count; retention (e.g., 7 days / 100 files); provide `voice --purge-captures`.
- Name captures by `session_id` + `chunk_idx` + reason; never by transcript content.
- If `--save-dir` is already preserving chunks, do not duplicate them.

**Warning signs:**
- Enabling capture increases measured decode time by a noticeable amount.
- Anomalies appear only when capture is on.
- `.part`/duplicate WAVs accumulate; disk fills.
- The capture directory is group/world-readable.

**Phase to address:**
**Phase 9** (capture policy and retention) with a small hook in **Phase 6** (timestamp ordering). Do not implement capture in the middle of Phase 7 calibration; it will bias the data.

---

### Pitfall 15: Privacy leakage beyond "no transcript text"

**What goes wrong:**
The user decision says no transcript text is stored. That is necessary but not sufficient. A ledger row can still contain:
- Absolute WAV paths (`/home/<user>/...`), `--save-dir` paths, model paths.
- `initial_prompt` (the last 200 characters of the previous transcript) if a debug field or exception dump is logged.
- `args`/environment dumps with usernames, hostnames, model cache paths.
- Session timestamps that reveal when the user was at the computer.
- Anomaly WAVs, which are speech by definition.
- The report itself, which may embed hardware/host info and be shared.
- The clipboard: `insert_text()` unconditionally copies the transcript to the clipboard (`voice.py:1174`), so "voicemode stores no transcript" is not true at the app level, only for the new telemetry. The docs must not overclaim.

**Why it happens:**
"No transcript" is interpreted as "only numbers", but paths and prompts are strings derived from the transcript or the user's identity. Debug helpers (`repr(args)`, tracebacks) are added late and bypass the allowlist.

**How to avoid:**
- **Explicit schema allowlist.** The ledger writer serializes a fixed set of fields; a schema test asserts no key matching `text|transcript|prompt|selection|clipboard|content` exists.
- Never log `initial_prompt`, `segment.text`, `wav_path` (store `save_dir_enabled: true` and a basename/hash instead), `platform.node()`, or raw env.
- Redact `$HOME` to `~` and omit hostnames/IPs in error strings.
- Store the ledger under `$XDG_STATE_HOME/voicemode/telem/v1/` with directory `0700`, file `0600`. Status goes to `$XDG_RUNTIME_DIR/voice-stt/` (tmpfs, `0700`). Do not use `/tmp/voice-stt-{uid}` for persistent data; chmod it `0700` if it must exist.
- Anomaly capture: default off, explicit, `0700`, retention, purge command, never uploaded, never embedded in the report.
- Report: self-contained HTML with inline CSS/SVG, no external fonts/scripts/images, no `fetch()` (CORS/`file://` issues), no absolute paths, optional `--redact-times` for sharing. Add a CSP meta tag (`default-src 'none'; style-src 'unsafe-inline'; img-src data:`) as defense in depth.
- Document the clipboard behavior separately so the privacy claim is precise.
- No network code in telemetry or the report, ever. "Local-only" should be verifiable by grepping for `urllib`/`requests` in the telemetry module.

**Warning signs:**
- `grep -i 'hello\|the \|and ' telemetry.jsonl` finds transcript fragments.
- A row contains `/home/` or `@hostname`.
- `initial_prompt` appears in a traceback or debug field.
- The anomaly directory is `0755`.
- The report loads a font or script from a CDN.

**Phase to address:**
**Phase 6** (schema allowlist, paths/permissions) and **Phase 9** (capture and report). A privacy bug found in Phase 9 may require deleting collected history; get it right in Phase 6.

---

### Pitfall 16: Python/QML path mismatch on other users' machines

**What goes wrong:**
`Voice.qml` computes `runtimeDir` from `XDG_RUNTIME_DIR` but falls back to a hardcoded `/run/user/1000` (`Voice.qml:13-15`). Python falls back to `/tmp/voice-stt-{uid}` (`voice.py:46`). On UID 1001, or when Quickshell is started by systemd without `XDG_RUNTIME_DIR`, the two halves look in different directories: Python writes `status.json`, QML reads nothing and shows idle forever. The same class of bug applies to `XDG_STATE_HOME` (ledger/report) if one side uses `~/.local/state` and the other uses a hardcoded path.

**Why it happens:**
The dev machine is UID 1000 and `XDG_RUNTIME_DIR` is always set in an interactive Hyprland session, so the fallback never runs. The two languages duplicate the path logic instead of sharing one definition.

**How to avoid:**
- One path resolution rule, documented in the contract: `status` = `${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-stt`; `state` = `${XDG_STATE_HOME:-$HOME/.local/state}/voicemode`.
- Remove the `/run/user/1000` literal. QML cannot cheaply call `id -u` or reliably read a UID env var, so the robust option is to make the bar read only `$XDG_RUNTIME_DIR` and fail closed with a one-time debug line if it is unset; the worker already has `os.getuid()` and can create the directory.
- Do not compute paths twice: generate a small `paths.json`/env file at install time, or pass the status path to Quickshell via an environment variable in the bar's launch configuration.
- Test as a second user (`useradd`/container) and with `XDG_RUNTIME_DIR` unset; assert the bar finds the file.
- Keep `status.json` in runtime and the ledger in state; never mix them.

**Warning signs:**
- Works on the dev machine, "idle" forever on a friend's machine.
- `find /run/user -name status.json` shows the file under a different UID/path than QML reads.
- Ledger and report appear in different directories depending on how the app was launched.

**Phase to address:**
**Phase 8** (QML path resolution) and **Phase 10** (second-user/UID test). Phase 6 defines the canonical paths.

---

### Pitfall 17: Countdown UX that destroys trust (zero, backwards, jumping)

**What goes wrong:**
A single ETA number is a promise. If it reaches `0s` and the bar keeps saying "Transcribing..." for another 20 s (temperature retry, second chunk, slow finalization), users stop believing it. If it jumps from `8s` to `14s` without explanation, it looks broken. If the provisional estimate (from recorded wall time) is `12s` and the refined estimate is `9s`, the countdown either jumps backward or stalls. If the first run on new hardware is wildly optimistic, the first impression is permanently bad.

**Why it happens:**
Countdowns are usually implemented as `deadline - now`, which inevitably hits zero before work finishes. The predictor is probabilistic, but the UI presents it as deterministic. The user explicitly chose one number (not a range), so the UI has less room to hedge.

**How to avoid:**
- Never render a negative or zero value while work continues. Clamp at `1s` and switch to `Finishing…` (or `Almost done…`) when the estimate is exhausted; keep the state `transcribing` until the terminal status.
- Allow upward revision, but mark it: change the color/icon or append `+` (still one number) when the estimate is revised upward; do not silently jump.
- Smooth the provisional→refined transition (e.g., only revise downward by a bounded amount per second, or show the refined number immediately but do not reset the visual countdown).
- Use `~` for an uncalibrated/uncertain estimate; keep a single number.
- On the first N sessions, bias the estimate high (under-promise) rather than low; the report shows the calibration curve.
- Do not show an ETA during `starting` or when the audio is too short/no-speech; those phases should be immediate or show a different label.
- Do not encode confidence as two numbers in the pill; put the error distribution in the report.

**Warning signs:**
- The pill shows `0s` for more than a second.
- ETA jumps upward repeatedly on ordinary sessions.
- Users report "it always says 5 seconds and takes 30".
- The first session on a new machine is the worst.

**Phase to address:**
**Phase 8** (display policy) informed by **Phase 7** (revision triggers). The clamp/finishing state is a UI requirement, not a model feature.

---

### Pitfall 18: Hardware detection that lies

**What goes wrong:**
The tempting fingerprint is `os.cpu_count()` and a GPU name. Both mislead:
- `os.cpu_count()` is logical CPUs, ignores `sched_getaffinity`, cgroup CPU quota, and hybrid P/E cores. A 32-thread machine may run CTranslate2 on 4 E-cores.
- `WhisperModel(..., cpu_threads=0)` passes `intra_threads=0` to CTranslate2, which means "use a default value" (typically OpenMP/environment-dependent), not "use all cores" and not necessarily 4. The app never sets `cpu_threads`.
- `device="auto"` resolves to CUDA when available; the resolved device/compute type is what matters (use `actual_backend()`).
- `nvidia-smi` may be absent, slow, or hang on a wedged driver. Calling it per session or per poll is a hang risk.
- Thermal throttling, battery/powersave governors, background load, and memory pressure change RTF by 2–5× on the same hardware.
- Peak RSS 2,129 MB means a 4 GB machine may swap; the ETA is then off by an order of magnitude, or the process is OOM-killed.

**Why it happens:**
Hardware detection feels like a static property, and core count feels proportional to throughput. In practice, the effective thread count, memory bandwidth, and sustained clocks dominate, and they are not visible from `os.cpu_count()`.

**How to avoid:**
- Record cheap, cached facts at session start: `/proc/cpuinfo` model name, `len(os.sched_getaffinity(0))`, cgroup CPU quota (if readable), `MemAvailable`, `loadavg`, arch, kernel, CTranslate2/faster-whisper versions, resolved device/compute type. Cache them; do not shell out in the hot path.
- Do not derive RTF from core count. Learn it empirically per fingerprint; use core count only as a weak prior for the no-data case.
- Probe GPU only once per session, with a timeout, after the model is loaded (`model.model.device` is authoritative); never call `nvidia-smi` from QML or a 100 ms poll.
- Use a rolling median/window (last N matching sessions) rather than all-time, so thermal/power changes adapt; include `loadavg`/`MemAvailable` to mark contended sessions and exclude them from calibration.
- On low-memory machines, warn before loading and add margin; handle OOM (stale state, Pitfall 10).
- Treat `compute_type="auto"` as unresolved until the model reports it; key calibration on the resolved value.

**Warning signs:**
- ETA is 3× off on a high-core machine but fine on the dev machine.
- Changing `OMP_NUM_THREADS` changes speed but not the ETA bucket.
- First CUDA session is much slower than the rest.
- Laptop accuracy degrades in the afternoon / on battery.
- `nvidia-smi` hangs when the driver is reloaded.

**Phase to address:**
**Phase 7** (fingerprint and adaptive estimator) and **Phase 10** (cross-hardware validation, CUDA/CPU, low-memory). Detection code must not block the live path.

---

### Pitfall 19: "ETA visible immediately" with zero calibration data

**What goes wrong:**
On first install, there is no history. If the UI waits for calibration, the user's explicit requirement ("ETA visible immediately") is violated. If it guesses from the dev machine's numbers, it is wrong on other hardware (especially CUDA, where decode is 10–50× faster but load is different). If it says "calculating…", the single-number UX is broken.

**Why it happens:**
The requirement and the data availability conflict. The natural implementations are "show nothing until n≥5" or "ship the developer's constants"; both fail the requirement or the portability requirement.

**How to avoid:**
- Ship a small **prior table** keyed by model class × resolved device class (e.g., CPU int8 small/medium/large; CUDA float16 small/medium/large): a conservative `load_ms` and `rtf`. Keep it in code/config, versioned.
- Apply a **safety margin** for the first `N` sessions (e.g., 1.2×), tapering as the bucket fills. Show `~` to signal estimate.
- Calibrate after the first successful session; do not wait for 5. Show the prior-derived number in the meantime.
- If the model/device fingerprint has no prior and no history (e.g., an exotic model), fall back to the nearest prior by model size and label it low-confidence in the report; still show a number.
- Never block the first ETA on a benchmark; if a microbenchmark is ever added, make it opt-in and one-time, not in the stop path.
- Make the first-run report row explain "prior used" so the early error is not mistaken for a regression.

**Warning signs:**
- The first session shows "calculating..." or no ETA.
- The first ETA is 10× low on CUDA/Apple/high-core hardware.
- The prior table has only the developer's machine values.
- Users disable the feature after the first bad estimate.

**Phase to address:**
**Phase 7** (prior + margin), with the contract fields from **Phase 6**. **Phase 10** validates the priors across hardware.

---
## Moderate Pitfalls

### Moderate 1: VAD and no-speech audio invalidate the duration the ETA was based on

**What goes wrong:**
The initial ETA is computed from recorded duration. `faster-whisper` then runs VAD **eagerly** inside `model.transcribe()` and exposes `info.duration_after_vad` before any decoding. For a 45 s recording with 4 s of speech, the ETA promises ~13 s and the decode finishes in ~1 s. Conversely, if `vad_filter=False` (or VAD keeps noise), decode is much slower than the speech duration suggests. Empty transcripts (`no_speech_prob` high, zero segments) still show a countdown and then a "done" state, which reads as a failure of the predictor.

**Why it happens:**
Duration is the only number available at keypress time, so it becomes the model input. VAD is treated as an internal detail rather than an ETA signal, even though its output is free.

**Prevention:**
- Record `audio_ms`, `vad_ms`, `duration_after_vad_ms`, `vad_ratio`, `no_speech_prob_max`, and `speech_ms`.
- After `transcribe()` returns (and before consuming segments), recompute the ETA from `duration_after_vad` and revise it *downward* using the same squashing rule as Critical 17.
- Classify `outcome = "no_speech"` when there are zero segments or `no_speech_prob_max` is high and `duration_after_vad` is tiny; exclude from calibration; show "No speech detected" rather than "Done".
- If `vad_ratio < 0.2`, do not display a long ETA; display the short-clip form ("a few seconds").
- Never run a second VAD pass for telemetry.

**Warning signs:**
- `decode_ms` is under 1 s on long recordings with plenty of silence.
- The pill counts down from 13 s and finishes at 1 s, then shows nothing typed.
- `duration_after_vad_ms` is 5–10 % of `audio_ms` on most sessions.

**Phase to address:**
**Phase 6** records the VAD fields; **Phase 7** uses them for revision and the no-speech bucket; **Phase 8** owns the "no speech" label. `duration_after_vad` is only available if the Phase 6 wrapper preserves `info`.

---

### Moderate 2: Local timestamps still break day grouping across DST and offset changes

**What goes wrong:**
Storing ISO 8601 with a numeric offset (the user's decision) fixes *instant* ordering, but not *grouping*. Grouping sessions into "today" by the local date string produces a 23-hour or 25-hour day at a DST transition, and a session at 01:30 occurs twice with different offsets. If any code parses the local string and re-localizes it, or sorts by the displayed string, rows move. If the machine's timezone changes (travel, `timedatectl set-timezone`), historical rows keep their old offset but "today" is computed with the new one, so the report's day boundary shifts mid-history.

**Why it happens:**
"ISO with offset" is treated as fully solved. Offset-preserving timestamps are unambiguous instants but ambiguous *local labels*, which is exactly what daily aggregation uses.

**Prevention:**
- Store `epoch_ms` as the canonical sort/group key and `local_iso` + `utc_offset_min` + `tz_name` for display only.
- Define "day" in the report explicitly: group by local date **as recorded**, not by converting historical instants to the current zone. Document the choice in the report footer.
- Never parse `local_iso` back into a datetime; read `epoch_ms`.
- Test with `TZ=America/New_York` around both DST transitions and with a mid-history `TZ` change; assert the day buckets contain the expected session ids.
- Keep log headers ISO+offset too, but never parse them for telemetry (Critical 2).

**Warning signs:**
- A daily bucket has 23 or 25 hourly rows.
- Two rows show `01:30` with different offsets and the report sums them into different days.
- "Today" excludes a session the user just made after changing timezone.

**Phase to address:**
**Phase 6** (schema and canonical key) and **Phase 9** (aggregation rule). This is cheap to fix in the schema and expensive to fix after history exists.

---

### Moderate 3: JSONL append, partial lines, and rotation

**What goes wrong:**
A JSONL ledger looks crash-safe because appends are line-oriented, but:
- Python's buffered text I/O can split a line across two `write()` calls; a crash between them leaves a partial line.
- Two writers (the duplicate-worker race in Critical 9, or a diagnostic run) interleave; a single `write` under `O_APPEND` is atomic only up to the filesystem's limit and only if it is one syscall.
- Size-based rotation via truncate or rename while a writer holds the old fd silently sends later rows to the rotated file or a deleted inode.
- A reader that does `[json.loads(l) for l in f]` crashes on the last partial line and loses the entire report.

**Why it happens:**
JSONL is marketed as append-only and simple; the failure modes are at the syscall and rotation boundaries, not in the serialization.

**Prevention:**
- Serialize the line, encode it, and write it with **one** `os.write()` on an fd opened `O_APPEND | O_CREAT | O_WRONLY`, mode `0600`. Do not use `print(..., file=...)` or buffered `TextIOWrapper` for the ledger.
- `fsync` only on terminal/error rows (or every N rows); a lost final heartbeat is acceptable, a corrupt file is not.
- Reader: parse line by line, `try/except JSONDecodeError`, skip a trailing incomplete line, and count skipped lines. Never rewrite the file to "fix" it.
- Rotate by **monthly file** (`2026-10.jsonl`) or by whole-file archival under a lock; do not truncate a file a live writer may hold. Record the ledger path in the session record so a mid-session upgrade does not split a row set.
- Enforce one writer per session (session id + PID check) and take an `flock` for rotation/prune only.
- Test: kill -9 during a burst of writes; assert all complete lines parse and at most one is dropped.

**Warning signs:**
- `JSONDecodeError` on the last line after a crash.
- Two JSON objects on one line.
- Sessions missing around midnight of a rotation.
- Ledger size does not grow although dictation works (writer appending to a rotated inode).

**Phase to address:**
**Phase 6.** The writer and reader live here; Phase 9 only consumes.

---

### Moderate 4: Schema evolution, `NaN`, and unknown states break old readers

**What goes wrong:**
Three independent versioning failures:
1. **Additive fields**: an old report/fit reads a new row missing `vad_ratio` and substitutes `0`, silently poisoning calibration.
2. **`NaN`/`Infinity`**: `json.dumps` emits bare `NaN` by default; Python accepts it, QML's `JSON.parse` and strict JSON readers reject the whole file. A single `rtf = decode/0` blanks the pill.
3. **New enum values**: `Voice.qml` matches known states; a new `finalizing` or `warming` falls through to idle, so the bar goes blank while the worker is busy. Renaming `transcribing` breaks every old QML deployment and every old ledger row.

**Why it happens:**
The ledger is treated as a private format with one consumer written at the same time. Quickshell configs and report files outlive the code that wrote them.

**Prevention:**
- `schema_version: 1` in every row and in `status.json`; additive-only changes within a version; a breaking change bumps the version and the reader ignores unknown major versions explicitly (with a one-line notice, not a crash).
- Validate on write: `json.dumps(..., allow_nan=False)`, coerce non-finite to `null`, and validate enums against a constant set. A rejected row is dropped with a counter, not written malformed.
- `status.json` always carries `busy: true/false` alongside `state`; QML renders unknown `state` as busy with the generic label, not idle.
- Readers default missing numeric fields to `null` and skip that metric, never to `0`.
- Keep a `decode` fixture of v1 rows in tests; assert the current report still reads them.
- Never put the schema version only in the filename.

**Warning signs:**
- The report crashes or shows zeros after a field rename.
- QML logs `JSON.parse` once and then shows idle permanently.
- A fit includes rows where `audio_ms` is `0`.
- An old `report.html` opens fine but a new one does not (or vice versa).

**Phase to address:**
**Phase 6** (writer validation and version) and **Phase 8** (tolerant state rendering). Phase 9 must read old rows by design.

---

### Moderate 5: `xdg-open` and report-path assumptions

**What goes wrong:**
"Click the pill to open the report" is one line of QML and several environment assumptions:
- `xdg-open` may not be installed; it may exit 0 without opening anything; it may open a text editor because no browser is the default for `text/html`.
- Quickshell launched from Hyprland/systemd may lack `DISPLAY`/`WAYLAND_DISPLAY`/`DBUS_SESSION_BUS_ADDRESS`, so the opener fails silently.
- A path with spaces, `#`, `?`, or non-ASCII must be passed as a proper `file://` URI (`Path.as_uri()`), not string-concatenated. A `#` in the filename truncates the URL.
- The report may not exist yet; generating it synchronously on click freezes the bar, and opening a stale report is worse than no report.
- `Quickshell.execDetached` / `Process` quoting differs from shell quoting; joining arguments into one string is a classic breakage.

**Why it happens:**
It works on the dev machine where a browser is default and the path is ASCII under `$HOME`.

**Prevention:**
- One helper: `report_uri = Path(report_path).resolve().as_uri()`; open with an argument list, not a shell string. `Quickshell.execDetached` takes a list in 0.3.2 (`quickshell-core.qmltypes`), so call `Quickshell.execDetached(["xdg-open", uri])`.
- `shutil.which("xdg-open")`; if absent or the spawn fails, fall back to `notify-send` with the absolute path and print it to the log.
- Do not wait for the opener; `start_new_session=True`, close fds, short timeout for the spawn only. Treat exit code as advisory.
- Generate the report **before** the click (on terminal status, in a detached process) or on click in a detached process with a "Preparing report…" toast. Never block the GUI thread.
- Test as a user with no default browser, with a space in `$HOME`, and from a systemd-started bar.
- Do not auto-open the report; only on explicit click.

**Warning signs:**
- Click does nothing from the bar but works from a terminal.
- Report opens in a text editor.
- A `file:///home/.../report` opens truncated at a `#`.
- The bar freezes for ~1 s on click.

**Phase to address:**
**Phase 9.** The report path and generation belong there; Phase 8 only emits the click intent.

---

### Moderate 6: Accuracy metrics that flatter the predictor

**What goes wrong:**
A single "accuracy" number is easy to make look good and hard to make honest:
- MAPE is dominated by short sessions (a 2 s error on a 5 s clip is 40 %; on a 180 s clip it is 1 %), so the headline improves as users dictate longer.
- Mean signed error cancels systematic over- and under-prediction; the predictor can be useless and average to zero.
- Evaluating on the same sessions used to fit is in-sample optimism, especially with a median and a small n.
- Excluding anomalies from the *metric* (not just the fit) hides exactly the sessions users remember.
- "Within 2 s" is an arbitrary threshold that flatters long sessions and is unattainable for short ones.
- Recomputing the ETA at report time (instead of using the displayed value) hides UI revision bugs.

**Why it happens:**
Everyone expects one percentage; the honest version is a small table.

**Prevention:**
- Report, per bucket: n, median absolute error, p90 absolute error, signed bias (median of `actual - predicted`), and the share of sessions where the ETA was exhausted before completion.
- Stratify by audio duration (short/medium/long), cold/warm, device class, and `outcome`; show anomalies as their own row, included in the raw error.
- Evaluate out-of-sample: fit on sessions before time T, score sessions after T (rolling origin), or at minimum leave-one-out. State which.
- Store `eta_shown_ms` and `eta_revised_ms` in the ledger; score the one that was displayed at the relevant moment and also report revision count.
- Never show a single "97 % accurate" headline; show n and the distribution.
- If the report must have a headline, use "median error 1.8 s (n=42, 8 anomalous)" with the caveat inline.

**Warning signs:**
- Accuracy looks great while the pill visibly expires on ordinary sessions.
- The metric improves after deleting short sessions.
- Report error is near zero but the scatter plot is bimodal.
- `eta_shown_ms` differs from the value the report scored.

**Phase to address:**
**Phase 7** (evaluation protocol) and **Phase 9** (presentation). Decide the metric before collecting, not after seeing the numbers.

---

### Moderate 7: Tests that cannot simulate clocks, sleeps, and the audio callback

**What goes wrong:**
The telemetry path is mostly time and I/O, which is exactly what the current test suite does not control:
- `Recorder._callback` runs on the PortAudio thread; any file write, logging, or lock acquisition there causes dropouts. Telemetry added in the callback would corrupt the audio it measures.
- Tests using real `time.sleep`/`perf_counter` are flaky on CI and cannot simulate suspend, DST, or a clock jump.
- `import voice` takes ~0.76 s and `import faster_whisper` pulls `av`/CTranslate2; tests that touch the module are slow even with a fake model.
- `tests/test_audio_chunking.py` uses 0.1 s chunks and mocked streams; it will not catch 44.1 kHz resampling or per-chunk overhead.
- If `format_eta` or the predictor reads `datetime.now()` directly, there is no seam to test the clamp or revision rules.

**Why it happens:**
The existing suite validates chunk math, not timing. Time is treated as ambient rather than an injected dependency.

**Prevention:**
- Inject `monotonic_fn`/`wall_clock_fn` (default `time.monotonic`/`datetime.now`) into the session recorder and predictor; tests advance a fake clock.
- Keep the audio callback allocation- and I/O-free: append frames to a preallocated buffer/queue; the writer thread does conversion and disk writes (already the design at `voice.py:184-203` — preserve it).
- Add a test that asserts the callback performs no `open`, no `json`, no `logging`, and no `datetime.now`.
- Test the predictor with synthetic ledgers: clean, one outlier, cold, no-speech, short clip, 44.1 kHz finalization, missing fields.
- Test the QML consumer logic by feeding fixture JSON through the same parsing path (or extract the state mapping into a testable JS function).
- Never require a GPU or a model download for the default test run; gate real-model tests behind an env var.

**Warning signs:**
- CI timing tests pass locally and fail on a loaded runner.
- A test needs `sleep(1)` to be reliable.
- No test covers `status.json` malformed/partial content.
- The 44.1 kHz path is only exercised manually.

**Phase to address:**
**Phase 6** (clock/writer seams) and **Phase 7** (predictor fixtures); **Phase 10** runs the soak/matrix tests.

---

### Moderate 8: Quickshell watcher storms and warning floods

**What goes wrong:**
Turning on `watchChanges: true` (recommended in Critical 12) introduces its own failure mode: Quickshell watches both the file and its parent directory, and an atomic `os.replace` generates multiple events (create temp, rename, directory change). If every event triggers `reload()` and every reload logs, a single status write produces a burst of reads and log lines. Inotify limits or a network-backed `$XDG_RUNTIME_DIR` (rare but possible) can drop events, leaving a stale pill with no error. `onFileChanged` can fire while the new file is not yet readable, yielding an empty read and an idle flicker.

**Why it happens:**
Watching is treated as strictly better than polling; the event semantics are not one-event-per-write.

**Prevention:**
- Debounce: on `onFileChanged`, start/restart a 50 ms timer; reload once when it fires. Ignore events while a read is in flight.
- Keep a 1 s fallback poll and a "last successful read" timestamp; after 3 s without a change while state is active, reload once and log at most once.
- Keep the last good parsed state across a single empty/invalid read (2–3 strikes), then fall back to PID/idle.
- `printErrors: false`; log the first occurrence of a distinct error and reset the flag on success.
- Verify `watchChanges` actually exists in the installed Quickshell version and feature-detect; do not assume the property is honored.
- Test with a loop that writes 200 status updates as fast as possible; assert reload count is bounded and no warnings flood.

**Warning signs:**
- Journal shows hundreds of identical parse warnings per session.
- CPU spikes exactly on status writes.
- Pill flickers to idle at each transition.
- Stale ETA after a suspend/resume (watcher lost).

**Phase to address:**
**Phase 8.**

---

### Moderate 9: Recording duration is not audio ground truth (xruns, dropped frames, writer timeout)

**What goes wrong:**
`Recorder.stop()` returns `duration` as recording wall time (`voice.py:292`), not the number of samples actually captured. Under load, PortAudio reports input overflow (`Recorder.statuses`), frames are dropped, and the WAV is shorter than the wall time. `stop_to_wav` joins writer threads with a timeout (`voice.py:311-312`); if a writer times out, the tail is missing but `duration` still includes it. Using wall time as the RTF denominator makes RTF look better on a loaded machine and worse on a fast one, and the "actual" latency in the report can exceed the audio that was transcribed. At 44.1 kHz, a slow `np.interp` in the writer thread makes this worse.

**Why it happens:**
Wall-clock duration is easy and usually close; the discrepancy only appears under exactly the load conditions where prediction matters.

**Prevention:**
- Use `audio_ms = 1000 * nframes / framerate` from the finalized WAV as the canonical audio length; keep `record_wall_ms` separately.
- Record `xruns`/`status_flags` from the `Recorder`, `writer_timeout` (bool), and `chunks_expected` vs `chunks_transcribed`.
- Classify `audio_incomplete` and exclude from RTF calibration; surface a subtle report marker.
- Add the `finalize_ms` term (Critical 13) instead of hiding it in wall duration.
- Test with a deliberately slow writer (sleep in the test double) and with xrun injection.

**Warning signs:**
- `audio_ms` is consistently 1–5 % below `record_wall_ms`.
- RTF spikes on sessions that coincide with compilation or a video call.
- Last words of long dictations are missing.
- `chunks_transcribed < chunks_expected`.

**Phase to address:**
**Phase 6** (fields) and **Phase 7** (denominator and exclusion). This changes the meaning of the headline metric, so decide it before calibrating.

---

### Moderate 10: Diagnostics, `--check`, and benchmarks poisoning the ledger

**What goes wrong:**
`voice --diagnostics` (and any future `--benchmark`/`--check`) loads the model and may transcribe a fixture. If it writes the same ledger, the calibration gets a 3 s synthetic sample with a known duration, or a benchmark sample with a different thread/device configuration. It also warms the page cache and CUDA context, so the next real session is classified "warm" when it is the user's cold start. Running diagnostics from the report's "verify" button would make the report mutate the data it reports.

**Why it happens:**
The diagnostic path reuses the transcription function, and the telemetry write is inside that function rather than in the session lifecycle.

**Prevention:**
- Write telemetry at the **session** layer, not inside `transcribe()`; diagnostics never create a session unless explicitly asked.
- If a diagnostic sample must be recorded for debugging, set `source: "diagnostic"`, `synthetic: true`, exclude it from all fits, and show it only in a separate section.
- Do not let diagnostics change the cold/warm classification: record `last_model_load_epoch_ms` and, if the load was diagnostic, mark the next real session `cache_warmed_by: "diagnostic"` (informational) rather than silently warm.
- Never let diagnostics write `status.json` as a fake session; use a separate `diag.json` or stdout.
- `voice --status` must never write anything.

**Warning signs:**
- Ledger rows at times with no corresponding keypress.
- `audio_ms` exactly matches a fixture length.
- The first real session after `--diagnostics` is classified warm and mispredicts.
- Report totals change after running a "verify" action.

**Phase to address:**
**Phase 6** (session-scoped writes) and **Phase 10** (diagnostic tooling).

---

### Moderate 11: Report generation interfering with the next session

**What goes wrong:**
Generating the report on every terminal status walks the whole ledger, computes buckets, and writes a large HTML. If this happens in the worker before the PID is removed, it adds latency after the text is already inserted (and can delay the next toggle, which sees a live PID). If it happens on click in the QML process, the bar freezes. Two sessions finishing close together can write the same report path concurrently, producing a truncated or mixed file. If the report embeds the current session and is generated before the ledger row is flushed, it is missing the session the user just made.

**Why it happens:**
"Generate on completion" is the simplest trigger and the completion path is already doing cleanup.

**Prevention:**
- Flush the terminal ledger row **first**, then write the terminal status, then remove the PID; report generation starts only after that, in a detached process.
- Single-flight: `flock` a report lock; if busy, skip (the next open regenerates) rather than queue.
- Cache: regenerate only if the ledger's size/mtime or max `session_id` changed.
- Atomic write to `report.html.tmp` then `os.replace`.
- Never generate in the audio callback, the decode loop, or the QML GUI thread.
- If generation is slow for large histories, cap the default window (e.g., last 90 days) with an explicit "all time" option.

**Warning signs:**
- `insert_ms` or PID removal time grows when the report feature is enabled.
- The just-finished session is missing from the report.
- A truncated `report.html` after two quick sessions.
- Bar freeze on click with a large ledger.

**Phase to address:**
**Phase 9**, with the ordering constraint established in **Phase 6** (terminal row before terminal status).

---

### Moderate 12: Unbounded retention and disk-full behavior

**What goes wrong:**
The JSONL itself is small (~600 B × 50 sessions/day ≈ 11 MB/year), but anomaly WAVs are ~5.76 MB each and accumulate quickly, and reports with embedded SVG/data can reach megabytes. Filling `$XDG_STATE_HOME` causes ledger writes to fail. If telemetry exceptions propagate, dictation breaks because a reporting feature could not write a file. Log files in `$XDG_RUNTIME_DIR` also grow if never rotated, and `--save-dir` may already be retaining every chunk.

**Why it happens:**
Telemetry is assumed to be "just text"; the audio capture option is the real disk consumer, and it is added later.

**Prevention:**
- Retention by age **and** count **and** total bytes, enforced on session terminal (cheap `scandir`, not a full walk every time) and by an explicit `voice --purge-telemetry`.
- Default: ledger kept indefinitely (tiny), captures kept 7 days / 100 files / 500 MB, reports keep the latest plus N archived.
- `statvfs` free-space check before writing a capture; skip with a single warning if below a threshold.
- Every telemetry write is best-effort: catch `OSError`, increment a failure counter, log once, and never fail the dictation. `status.json` write failure is also non-fatal for transcription (but should be visible in `--status`).
- Cap report size (limit sessions, downsample points, no raw per-segment arrays).
- Rotate/limit `voice.log`/`tts.log`; they live in runtime and should be per-boot.
- Test with a full tmpfs and a read-only state dir.

**Warning signs:**
- State directory grows without bound after enabling captures.
- A disk-full notification coincides with failed dictation.
- `voice.log` is hundreds of MB.
- Purge command does not exist or requires manual `rm`.

**Phase to address:**
**Phase 9** (retention/purge) and **Phase 10** (failure-mode hardening).

---

## Minor Pitfalls

### Minor 1: ETA string formatting churn and units

**What goes wrong:**
`9s` → `10s` changes the label width and shifts the bar; `92s` is harder to read than `1m 32s`; `0.4s` implies precision the model does not have. Mixing `9s` and `9 s` across the pill and the report looks sloppy, and a fixed-width assumption breaks when the ETA exceeds 59 s. Rounding `59.6` to `60s` and then to `1m` can make the number appear to jump backward.

**Prevention:** Format centrally (`format_eta(ms)`), integer seconds, `m:ss` only above 60 s, `~` prefix when using a prior, a minimum label width with tabular figures, and one decimal place nowhere. Test the boundary values 0, 999 ms, 59.5 s, 60 s, 3599 s.

**Warning signs:** The pill visibly changes width each second; the ETA shows `0.0s`; `60s` appears once and then `1m 0s`.

**Phase:** **Phase 8** (display), **Phase 9** (report uses the same helper).

---

### Minor 2: Color-only differentiation and contrast

**What goes wrong:**
The user asked for a color distinct from recording. A hue-only change (e.g., red → orange) fails for colorblind users and can be indistinguishable on a dimmed or transparent bar. Reusing the error/warning color for the ETA means a slow session looks like a failure. Hardcoded hex colors break in light themes or when the bar applies opacity.

**Prevention:** Distinct hue **and** a glyph/prefix (`~`, a clock icon) **and** the numeric text; use theme palette roles where possible; verify contrast against the actual bar background in both themes; never use the error color for a normal estimate; test with a grayscale screenshot.

**Warning signs:** A screenshot in grayscale shows no difference between recording and transcribing; the ETA is unreadable on a light theme.

**Phase:** **Phase 8.**

---

### Minor 3: Clickable pill breaks hover, drag, and neighboring widgets

**What goes wrong:**
Adding a `MouseArea` to open the report can swallow hover events used by the existing tooltip, trigger on drag/scroll, extend over adjacent bar modules, or open the report on a right-click. If the pill grows when the ETA appears, the click target moves under the cursor mid-press.

**Prevention:** Accept only left button and release-inside; set an explicit cursor shape; keep the hit area equal to the visible pill; do not consume wheel events; preserve hover; make the target stable in width (see Minor 1); open at most once per press; provide a keyboard/`Quickshell` alternative and a "copy path" fallback.

**Warning signs:** Tooltip stops working; clicking the neighboring workspace opens the report; a drag opens a browser.

**Phase:** **Phase 8.**

---

### Minor 4: Report filename collisions, browser caching, and stale tabs

**What goes wrong:**
A fixed `report.html` overwritten on every session means an already-open tab shows stale data until a manual reload, and two sessions can race on the same path. Timestamped filenames accumulate and make "open the report" ambiguous. `file://` caching is inconsistent across browsers; adding `?v=` sometimes works and sometimes reloads from cache anyway.

**Prevention:** Write a stable `latest.html` atomically; keep a small set of timestamped archives with retention; open the stable path; tell the user to reload if it looks stale; avoid relying on query-string cache busting for `file://`; never write the report into the repo or a synced folder.

**Warning signs:** The report opens with yesterday's sessions; multiple `report-*.html` files with no cleanup; two `.tmp` files.

**Phase:** **Phase 9.**

---

### Minor 5: Quickshell API drift across versions

**What goes wrong:**
The integration depends on `FileView.watchChanges`, `FileView.text()` blocking semantics, `Quickshell.execDetached`, and `Process` argument handling. These are version-sensitive, and the user's `illogical-impulse` config may be updated independently of this project. A property that silently does nothing (or a default that flips) makes the pill stop updating with no error.

**Prevention:** Do not try to feature-detect a QML property at runtime; instead keep the fallback poll functional regardless of whether watching works, document the tested Quickshell version, and add a startup debug line that prints the resolved status path and whether the last read succeeded. Avoid depending on `text()` being synchronous for correctness; treat it as a snapshot and tolerate empty reads.

**Warning signs:** Works until a system update; no status updates but no errors; the config's Quickshell version differs from the documented one.

**Phase:** **Phase 8** (defensive consumer), **Phase 10** (version matrix).

---

### Minor 6: `/proc/<pid>/stat` and start-time parsing fragility

**What goes wrong:**
The current QML reads `/proc/<pid>/stat` and derives process start time from field 22. The `comm` field is parenthesized and may contain spaces and `)` (thread names can), so naive `split()` shifts every subsequent field. Values are in clock ticks, not seconds, and PID reuse can make a dead session look alive.

**Prevention:** Parse after the **last** `)` on the line, then index from there; convert with `sysconf(_SC_CLK_TCK)`; combine PID + start ticks as the identity; validate with `cmdline` containing the expected script; treat a parse failure as "unknown", never as "alive".

**Warning signs:** Process appears to have started at epoch 0; identity check passes for a recycled PID; QML shows a session that does not exist.

**Phase:** **Phase 6** (identity fields), **Phase 8** (consumer).

---

### Minor 7: Inline report assets vs. CSP and `file://`

**What goes wrong:**
A self-contained report with inline CSS/SVG is the right call, but a strict CSP meta tag (`default-src 'none'`) blocks inline styles unless `style-src 'unsafe-inline'` is allowed, and some browsers block inline scripts entirely on `file://`. Conversely, loading a chart library or font from a CDN breaks offline use, leaks a request, and fails under a strict CSP. Embedding unescaped device names or error strings is an HTML injection vector even in a local file.

**Prevention:** Inline CSS with `style-src 'unsafe-inline'`; SVG generated server-side (Python) rather than by JS; no external requests; escape every interpolated string (`html.escape`); test in Firefox and Chromium from `file://` with no network; keep the CSP meta tag but verify it does not blank the page.

**Warning signs:** Blank report in one browser; a request to a CDN in devtools; a device name containing `<` breaks the layout.

**Phase:** **Phase 9.**

---

## Deferred: TTS ETA (v1.2) — pitfalls to design around now

TTS is explicitly out of scope for this milestone. These are recorded so the Phase 6 contract does not have to be broken later.

| Issue | Why it differs from STT | Contract/design implication |
|-------|--------------------------|-----------------------------|
| Per-invocation model load | `synthesize_kokoro_tts` runs in a fresh background process per utterance, so the ONNX model load is paid every time, not once per session | A `source: "tts"` row needs its own `load_ms`; do not fold it into the STT load prior |
| Character count ≠ audio duration | Kokoro/Edge duration depends on phonemes, punctuation, speaking rate, and `speed`; chars/sec is a weak feature | Predict **time to first audio** and **playback duration** separately; never derive one from the other |
| Network variance (Edge) | `edge-tts` is network-bound: DNS, TLS, first byte, throttling, 429s, offline failure | Separate `engine` bucket; a failed/offline session must not poison the Kokoro prior; ETA cannot be promised offline |
| Playback duration vs. synthesis latency | The user cares about when audio *starts*; `ffplay` then plays for the length of the clip | The pill must not count down to zero and sit at "Speaking" for 40 s; show `Speaking` with elapsed time after first audio |
| Interruption | `SIGUSR1` stops playback (`stop_tts`), so "actual" is shorter than synthesized | Classify `cancelled`; exclude from duration calibration but keep for first-audio latency |
| Content sensitivity | Selected text can be a password, a private message, or a document; the user decision forbids storing transcript text | Store `input_chars`, `voice`, `speed`, `engine`, `sample_rate` only; never the text, never a hash of short text (guessable) |
| First-run assets | Kokoro voice/weights are downloaded by `scripts/download-kokoro-assets.sh`; the first synthesis can be much slower or fail | `assets_ready` flag and a distinct `cold_assets` outcome |
| Extrapolating STT RTF | CTranslate2/Whisper RTF says nothing about ONNX Kokoro or Edge | Separate `eta_model_version` per source; QML must render `source` generically |

**Reserve now (Phase 6):** `source` (`stt`/`tts`), `engine`, `input_chars`, `first_audio_ms`, `playback_ms`, `cancelled`, and a nullable `eta_shown_ms`. Do not overload the STT `audio_ms`/`rtf` fields for TTS. QML should branch on `source`, not on a state name.

---

## Technical Debt Patterns

| Shortcut | Immediate benefit | Long-term cost | When acceptable |
|----------|-------------------|----------------|-----------------|
| Putting telemetry in `transcribe()` instead of the session layer | Fewer call sites; works for the CLI | Diagnostics and tests silently write calibration data (Moderate 10); the lowest layer now knows about JSONL and paths | Never |
| Keeping everything in `voice.py` | No package refactor; single entry point preserved | The module already imports `sounddevice`/`faster_whisper` at top (Critical 11); telemetry adds more import cost and makes the 3,154-line file harder to test | Only if a `voice_telemetry.py` with stdlib-only imports is extracted for status/ledger |
| A hand-written JSON contract duplicated in Python and QML | Fast to start | Field drift, unknown-state falls-through, NaN rejection (Critical 8, Moderate 4) | Never without a schema fixture test |
| Parsing `voice.log` for telemetry | No writer changes | Log format is human-oriented, one-second resolution, no offset, interleaved by two processes (Critical 2) | Never |
| Fitting with `numpy.polyfit` on all samples | One line | One outlier destroys it (Critical 4); in-sample accuracy misleads (Moderate 6) | Only as a diagnostic overlay, never as the predictor |
| Hardcoding the dev machine's priors | "ETA visible immediately" | Wrong by 10× on CUDA or high-core machines (Critical 19) | Only as a labeled fallback for an unknown fingerprint |
| PID file + status file with ad-hoc precedence | Backward compatible | Two truths disagree during transitions (Critical 8); stale status looks active (Critical 10) | During Phase 6 migration only, with explicit precedence |
| Fixed-name report with full history on every session | Simple mental model | Generation cost and races (Moderate 11); stale tabs (Minor 4) | Only if generation is detached and cached by ledger mtime |
| `datetime.now().isoformat()` everywhere | Readable | No offset, DST-ambiguous grouping (Critical 2, Moderate 2) | Never for persisted telemetry |
| Copying WAVs into a capture dir inside the timed path | Simple retention | Changes the measured latency (Critical 14) | Never |

---

## Integration Gotchas

| Integration point | Common mistake | Correct approach |
|-------------------|----------------|------------------|
| QML `FileView` → `status.json` | Assuming `watchChanges` is on by default (it is **false** in Quickshell 0.3.2) and reloading synchronously at 10 Hz | Enable watching if available, debounce `onFileChanged`, keep a 1 s fallback poll, tolerate empty reads |
| QML clock ↔ worker clock | Subtracting `time.monotonic()` from `Date.now()`; trusting `/proc/uptime` to match Python (4.39 s apart after suspend here) | Producer computes all durations and `updated_epoch_ms`; QML only displays |
| Hyprland keybind → `voice --toggle` | Measuring from SIGUSR1 and ignoring 0.4–1.1 s of `--toggle` imports | Record `stop_dispatch_ms`; report `text_ready_ms` and `e2e_ms` separately (Critical 3) |
| `insert_text` → focused window | Treating insertion as instant or as part of decode | Record `insert_ms` separately; note that `type_delay=2 ms` adds 1–2 s for long text; exclude from calibration |
| Clipboard | Claiming "no transcript stored" while `insert_text` copies it (`voice.py:1174`) | Document the clipboard behavior precisely; optionally add `--no-clipboard` |
| `xdg-open` from the bar | Joining args into a shell string; assuming `DISPLAY`/`WAYLAND_DISPLAY`/a default browser | Pass an argument list, use `Path.as_uri()`, detached + no wait, fall back to `notify-send` (Moderate 5) |
| `$XDG_RUNTIME_DIR` in QML | Hardcoded `/run/user/1000` fallback vs Python's `/tmp/voice-stt-{uid}` | One documented rule; remove the literal; test as UID ≠ 1000 (Critical 16) |
| CTranslate2 `device="auto"` | Recording `"auto"` as the calibration key | Record the resolved `model.model.device`/`actual_backend()` (Critical 6/18) |
| `/proc/<pid>/stat` | Naive `split()` shifted by a `comm` containing `)`; ticks treated as seconds | Parse after the last `)`, convert with `SC_CLK_TCK`, combine PID + start ticks (Minor 6) |
| `voice --status` | Calling it from the bar | File read only; make the CLI stdlib-only if it must exist (Critical 11) |
| JSON serialization | `json.dumps` default emits `NaN`; `JSON.parse` rejects it | `allow_nan=False`, sanitize, validate enums (Critical 8, Moderate 4) |
| Two sessions finishing at once | Same PID/status/report path | Single-writer session id + `flock`; atomic replace; last-writer-wins only if session ids match |

---

## Performance Traps

| Trap | Symptoms | Fix | Phase |
|------|----------|-----|-------|
| Spawning `voice --status` on a timer | 523 % CPU bursts, fan noise, ~0.44 s wall per call (user sees 1.15 s) | Never spawn; read the file; stdlib-only status entry point | 6, 8 |
| Synchronous `FileView` reloads at 10 Hz over several files | GUI-thread I/O, bar jank, CPU while transcribing | Watch + debounce + 1 Hz label update; tmpfs only | 8 |
| Copying/encoding a 5.76 MB WAV before the decode timestamp | Enabling capture slows sessions and creates anomalies | Timestamp first; hardlink/rename on the same fs; copy async or quarantine | 9 |
| Regenerating the full report on every terminal status | `insert_ms` and PID removal grow; races with the next session | Detached, cached by ledger mtime, atomic, single-flight | 9 |
| `fsync` on every heartbeat | Storage stalls in the stop path | `fsync` only terminal/error rows | 6 |
| Reading/parsing the whole ledger for the live pill | Growing CPU with history size | The pill reads only `status.json`; the report reads the ledger | 8, 9 |
| Calling `nvidia-smi` per session or in a poll | Hangs on a wedged driver; latency spikes | Probe once after load with a timeout, or trust `model.model.device` | 7, 10 |
| Deriving RTF from `os.cpu_count()` | 3× error on hybrid/cgroup-limited machines | Learn per fingerprint; core count only as a weak prior | 7, 10 |
| OLS on all samples | Slope flips with one anomaly | Median RTF/load + outcome filtering | 7 |
| Loading the model in `--status`/`--diagnostics` implicitly | Cache warming changes cold classification; 3 s + 2 GB RSS | Session-scoped writes; diagnostic flag; never load in status | 6, 10 |

---

## Security / Privacy Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging `initial_prompt` or any `Segment.text` in a debug field | Stores the previous transcript verbatim; the exact thing the user forbade | Schema allowlist; a test asserting no `text\|transcript\|prompt\|selection\|clipboard\|content` keys |
| Storing absolute WAV/save-dir/model paths | Reveals username, home layout, projects, mounted drives | Store `save_dir_enabled` + basename/hash; redact `$HOME` |
| Dumping `args`/env/tracebacks into the ledger | Hostname, user, tokens in env, paths | Fixed serializer; sanitize exceptions; no `repr(args)` |
| Predictable `/tmp/voice-stt-{uid}` with default perms | Another local user can pre-create the dir or a symlink; status/pid injection | Use `XDG_RUNTIME_DIR`; `0700`; `O_NOFOLLOW` where practical; never store persistent data there |
| Anomaly WAVs world-readable or never purged | Speech content retained indefinitely, readable by other users | Default off, `0700`, `0600`, retention + purge, explicit flag |
| Report with external fonts/scripts/analytics | Network leak, offline breakage, CSP issues | Inline everything, no network, CSP meta, escape interpolated strings |
| Claiming "no transcript stored" while the clipboard holds it | False privacy claim | Document clipboard behavior; offer `--no-clipboard` |
| Uploading telemetry "for improvement" | Violates local-only expectation | No network code in the telemetry module; grep-able guarantee |
| Unescaped device/error strings in HTML | HTML injection in a local file; broken report | `html.escape` on every interpolation; generate SVG in Python from numbers only |

---

## UX Pitfalls

| Pitfall | User impact | Better approach |
|---------|-------------|-----------------|
| Countdown reaches `0s` and keeps going | "It's broken"; users stop trusting every future estimate | Clamp at `1s` → `Finishing…`; keep state until terminal |
| ETA jumps upward silently | Looks like a glitch or a lie | Allow revision but mark it (`+`, color/icon change); keep one number |
| ETA shown during `starting` or for silence | Promise with no work behind it | Show `starting` with no ETA; no-speech shows "No speech" |
| "Calculating…" on first run | Violates "ETA visible immediately" | Ship priors + a safety margin, labeled `~` |
| Color-only differentiation from recording | Colorblind users and dim themes cannot tell states apart | Hue + glyph + text |
| Pill width changes every second | Bar shifts; neighboring modules move; click target moves | Fixed/minimum width, tabular figures, 1 Hz updates |
| Clicking the pill does nothing (no `xdg-open`/browser/display) | Feature appears broken | Fallback to notification + path; test headless/no-browser |
| Report is an empty page on day one | Feature looks broken | Explicit empty state with "dictate once to see data" |
| Anomalies hidden from the report | Users remember the 60 s outlier; the report says 98 % accurate | Show anomalies as their own row/points, included in raw error |
| Aggressive first-run pessimism | Every estimate says 60 s for a 10 s job | Conservative but bounded margin (1.2×), taper after N sessions |

---

## "Looks Done But Isn't" Checklist

- [ ] `decode_ms` covers **consumption** of the segment generator, not just the `transcribe()` call (Critical 1)
- [ ] A stopwatch test with a yielding fake generator proves it
- [ ] `load_ms` and `finalize_ms` are measured separately from decode (Critical 5, 13)
- [ ] `audio_ms` comes from the finalized WAV, not wall time (Moderate 9)
- [ ] `duration_after_vad_ms` is recorded and used to revise the ETA (Moderate 1)
- [ ] Every session has a terminal `outcome`, including watchdog/SIGKILL/cancel paths (Critical 10)
- [ ] `status.json` is written via temp + `os.replace`, mode `0600`, schema-versioned (Critical 8)
- [ ] QML renders an unknown `state` as busy, not idle (Moderate 4)
- [ ] QML never subtracts a Python timestamp from `Date.now()` (Critical 2)
- [ ] The bar does not spawn any process; `voice --status` is never polled (Critical 11)
- [ ] `watchChanges` behavior is verified on the installed Quickshell; a fallback poll exists (Critical 12, Moderate 8)
- [ ] A double-tap during cold start leaves exactly one worker (Critical 9)
- [ ] A SIGKILL mid-transcription ends in an error state, not "Typing…" (Critical 10)
- [ ] Two concurrent sessions cannot write the same ledger/report (Critical 9, Moderate 11)
- [ ] Calibration excludes anomalies, cold starts, diagnostics, and non-`ok` outcomes (Critical 4, 7, Moderate 10)
- [ ] The predictor uses the resolved device/compute type, not `"auto"` (Critical 6, 18)
- [ ] A first-run fresh state produces a visible ETA from priors (Critical 19)
- [ ] The ETA clamps at 1 s and shows `Finishing…`, never 0 or negative (Critical 17)
- [ ] JSON contains no `NaN`; QML parses every emitted `status.json` (Critical 8)
- [ ] The ledger schema contains no transcript/prompt/path fields, verified by a test (Critical 15)
- [ ] A UID ≠ 1000 test finds the status file (Critical 16)
- [ ] The 44.1 kHz + multi-chunk path is exercised and the ETA includes finalization (Critical 13)
- [ ] Cold cache/first-session-of-boot is tested, not assumed (Critical 7)
- [ ] Report generation is detached, cached, atomic, and does not delay PID removal (Moderate 11)
- [ ] `xdg-open` failure falls back to a notification/path, tested with no browser (Moderate 5)
- [ ] DST and timezone-change grouping is tested (Moderate 2)
- [ ] Retention and disk-full behavior are implemented and tested (Moderate 12)
- [ ] TTS fields (`source`, `engine`, `first_audio_ms`, `playback_ms`) are reserved and QML branches on `source` (Deferred)
- [ ] No TTS RTF is mixed into the STT prior (Deferred)

---

## Recovery Strategies

| Problem | Likely cause | Immediate fix | Prevention |
|---------|--------------|---------------|------------|
| ETA wildly low for every session | Timed `transcribe()` only (C1) | Re-collect after fixing the marks; keep old rows flagged `schema_version` | Stage-mark test |
| ETA degraded after one session | Outlier in the fit (C4) | Recompute with median RTF and `outcome=ok`; keep the anomaly visible | Robust estimator |
| Pill stuck at "Transcribing" | Stale status / missing terminal write (C10) | Delete the stale status, verify the PID is dead; restart the bar | TTL + terminal writes |
| Pill blank/idle during work | Unknown state or NaN JSON (M4) | Inspect the last `status.json`; validate with `json.loads(..., parse_constant=...)` | Enum validation + `allow_nan=False` |
| Two ETA resets in one dictation | Duplicate workers (C9) | `pkill -f record-background`, remove stale PID/status, retry | `flock` + session id |
| Report empty/partial | Report generated before the row flushed (M11) | Regenerate from the ledger | Terminal row before report |
| Report will not open | `xdg-open`/display/browser (M5) | Open the printed path manually; install a browser/`xdg-utils` | Fallback path + test |
| Calibration suddenly worse | Config/model/device change (C6) | Check fingerprint diff; start a new bucket | Exact fingerprint match |
| High CPU at idle | `--status` polling (C11) | Stop the poller; read the file | No subprocess rule |
| "Typing…" after a crash | PID disappearance mapped to typing (C10) | Clear status; fix the consumer state map | Terminal status + TTL |
| Report shows 99 % but user disagrees | In-sample/flattering metric (M6) | Switch to out-of-sample median/p90 + bias | Predefined evaluation |
| Capture directory huge | No retention (M12) | Purge; add limits | Retention + `statvfs` |

---

## Pitfall-to-Phase Mapping

| Phase | Pitfalls to close | Verification |
|-------|-------------------|--------------|
| **6 — Telemetry Ledger & Status Contract** | C1 (stage marks), C2 (clock domains), C3 (boundaries), C4 (outcome/fallback fields), C6 (fingerprint fields), C8 (atomic status/schema), C9 (session identity/single writer), C10 (terminal states/TTL), C11 (import/CLI split), C13 (per-chunk/finalize fields), C15 (schema allowlist), C16 (path rules), M1 (VAD fields), M2 (epoch + local), M3 (JSONL writer), M4 (version/NaN), M7 (clock seams), M9 (audio vs wall), M10 (session-scoped writes), Minor 6 (identity) | Schema fixture test; kill -9 test; double-tap test; import budget; JSON strictness |
| **7 — ETA Engine & Calibration** | C4 (robust estimator/exclusion), C5 (load term/clamp), C6 (buckets/priors), C7 (cold/CUDA), C13 (chunk math/refinement), C18 (empirical RTF), C19 (priors/margin), M1 (VAD revision), M6 (evaluation protocol), M9 (denominator) | Synthetic-ledger tests: clean, outlier, cold, no-speech, short, multi-chunk; leave-one-out |
| **8 — Quickshell ETA Integration** | C2 (display durations only), C8 (precedence/malformed), C9 (session match), C10 (error states), C12 (I/O/debounce), C16 (paths), C17 (clamp/revision), M4 (unknown state), M8 (watcher storms), Minor 1–3, Minor 5, Minor 6 | 200-write burst; malformed fixture; UID ≠ 1000; grayscale/contrast; click test |
| **9 — Accuracy Report & Anomaly Capture** | C14 (capture out of timed path), C15 (capture/report privacy), M5 (`xdg-open`), M6 (report metrics), M11 (generation), M12 (retention), Minor 4, Minor 7 | No-browser test; `$HOME` with spaces; capture timing delta; retention/purge; escaping test |
| **10 — Portability & Hardening** | C6, C7, C13, C18, C19 (cross-hardware), C16 (second user), M10 (diagnostics), M12 (disk-full) | CPU int8 / CUDA fp16 / small+large model; 44.1 kHz; 4 GB RAM; cold boot; read-only state dir |
| **v1.2 — TTS ETA** | Deferred section | Separate buckets; no text stored; first-audio vs playback |

---

## Sources

- `/home/pera/github_repo/Voice/voice.py` — imports `40-42`; `Recorder` `150-337`; `stop`/duration `275-317`; `load_model`/`transcribe` `616-680`; `insert_text`/`type_delay` `1040-1180`; TTS `1400-1544`; `toggle_background_recording` `1661-1706`; `run_background_recording` `1709-1865`; watchdog `923-951`; status `1991-1999`; diagnostics `2485-2629`.
- `/home/pera/github_repo/Voice/tests/test_audio_chunking.py` — chunk math and sequential transcription; 0.1 s chunks and mocked streams.
- `/home/pera/.config/quickshell/ii/services/Voice.qml` — 100 ms polling, `/proc/uptime` recovery, PID-disappearance → typing, `/run/user/1000` fallback.
- `/home/pera/.config/quickshell/ii/modules/ii/bar/VoicePill.qml` — label/colors/wrap-up timer/inert mouse area.
- `/usr/src/debug/illogical-impulse-quickshell-git/quickshell/src/io/fileview.{hpp,cpp}` and `/usr/lib/qt6/qml/Quickshell/Io/FileView.qml` — `watchChanges` default false; synchronous `loadSync()`; file + parent-directory watcher. Quickshell 0.3.2. Confidence: HIGH.
- `/home/pera/github_repo/Voice/.venv/lib/python3.12/site-packages/faster_whisper/transcribe.py` — eager VAD/features, lazy segment generator, temperature list `[0.0 … 1.0]`, `Segment.temperature/avg_logprob/compression_ratio/no_speech_prob`, `info.duration_after_vad`, `cpu_threads=0`. faster-whisper 1.2.1. Confidence: HIGH.
- CTranslate2 4.8.2 `Whisper` binding — `intra_threads=0` means default. Confidence: HIGH.
- Measured on the development machine (2026-10-26): `voice --status` 0.44 s wall / 2.21 s user / 523 % CPU; import breakdown `sounddevice` 344 ms, `faster_whisper` 209 ms, `av` 140 ms; peak RSS 2,129 MB; `/proc/uptime` vs `time.monotonic()` delta 4.39 s; clean fit `eta ≈ 1.73 + 0.2472 × audio_s`; outlier fit `25.7 + 0.0717 × audio_s`; median RTF 0.2375 after 2.4 s load. Confidence: HIGH for this machine, MEDIUM for magnitudes elsewhere, LOW for untested hardware.
- `/home/pera/github_repo/Voice/.planning/PROJECT.md` — user decisions: single ETA number, immediate visibility, distinct color, click opens report, no transcript text, local time with numeric offset, cross-hardware portability, TTS deferred.
- `/home/pera/.config/opencode/gsd-core/templates/research-project/PITFALLS.md` — required structure.
