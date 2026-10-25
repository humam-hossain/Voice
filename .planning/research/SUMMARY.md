# Project Research Summary

**Project:** voicemode (Arch Linux / Hyprland) — milestone v1.1 "Latency Prediction & Telemetry"
**Domain:** Local desktop ML utility — latency prediction, local telemetry ledger, external Wayland status-bar consumer (Quickshell/QML)
**Researched:** 2026-10-26
**Confidence:** HIGH for stack, integration points and pitfalls (verified against the project venv, installed `faster-whisper` 1.2.1 source, and Quickshell 0.3.2 source); MEDIUM for predictor accuracy on hardware other than this machine

---

## Milestone Goal

Show a trustworthy single-number ETA during transcription, and record prediction-vs-actual telemetry so the estimator improves over time and stays portable across CPU/CUDA hardware and model configurations.

**The milestone is not "show an ETA." It is "prove the ETA is honest."** A version without the ledger and the report cannot do that, and the ledger/report is the part most likely to be under-scoped. Terminal tools have printed ETAs for decades; the differentiator here is one glanceable number in a two-word-wide bar, plus the ability to prove afterwards how wrong it was.

## Locked Decisions (from the user — do not re-litigate)

| Decision | Consequence for the roadmap |
|---|---|
| ETA **replaces** the literal `"Transcribing..."` text in the Quickshell `VoicePill` | The QML phase must remove the hardcoded string, not add a second label beside it |
| ETA uses a **distinct color** from recording | Distinct hue **and** a glyph/`~` prefix **and** the number — never color-only, never the error color (PITFALLS Minor 2) |
| Clicking the pill opens the local **HTML report via `xdg-open`** | A clickable pill must not ship before a report exists to open; report precedes the bar |
| **Single number**, no range | No `8–14s`, no percent, no `±`, no confidence badge in the pill. Confidence lives in the ledger/report |
| **No transcript text** stored — character counts only | Allowlist serializer + a test that asserts no `text\|prompt\|hotword\|prefix\|wav` keys or values |
| **Cold model load stays** | No daemon, no model pre-warm, no resident process. The 2.2–3.0 s load is modeled and predicted, not removed |
| Live bar files are **symlinks into `/home/pera/github_repo/.dotfiles`** (`package restow quickshell/.config/quickshell`) | Bar edits commit in the dotfiles repo; vendored reference copies live under `integrations/quickshell/` in this repo |
| Phase numbering continues at **Phase 6** | v1.0 ended at Phase 5; this milestone occupies 6–10 |

---

## Executive Summary

This is a latency-prediction and measurement feature bolted onto an existing, working single-file dictation utility — not a new product. Experts build it the boring way: a **physical stage model** (`finalize + model_load + rate × voiced_audio + insert`) over a **robust, per-configuration calibration** read from a local append-only ledger, with the displayed number treated as a **cross-process file contract** consumed by a separate UI. Nobody in this space ships a learned model for it; the data volume is a few hundred runs, and a regression would be unexplainable and unportable.

The recommended approach adds **zero Python dependencies**. Everything needed is stdlib (`json`, `os.replace`, `statistics`, `csv`, `html`, `string.Template`, `xml.sax.saxutils`, `wave`, `hashlib`, `fcntl`, `resource`, `/proc`, `/sys`) plus Quickshell 0.3.2's `FileView` + `JsonAdapter`, verified present in the installed tree. One new stdlib-only module (`voicemode_telemetry.py`) owns schema, atomic writes, ledger I/O, the pure predictor, and the report formatters. `status.json` in `$XDG_RUNTIME_DIR/voice-stt/` is **advisory enrichment**; the existing PID file stays the **authority for state**. `metrics.jsonl` in `$XDG_STATE_HOME/voicemode/` gets exactly one record per run in the worker's `finally`. The bar reads files only — it never spawns a process.

The risks are concentrated and non-negotiable, and every one of them is cheaper to fix before data exists than after. Five must land **before any data is collected or the bar ships**: the duplicate-worker race, atomic status/PID writes, terminal states on watchdog/SIGKILL/cancel, the timing seam around `faster-whisper`'s lazy generator, and the import/CLI split. Get any of them wrong and the ledger records fiction that calibration then learns from — a bad history must be deleted, not migrated. Separately, **lazy imports are a larger perceived-latency win than the entire ETA feature** (≈0.5 s off every hotkey press, measured) and they shrink the startup window that triggers the duplicate-worker race, so they go first.

TTS ETA is explicitly out of scope, but the Phase 6 schema must reserve its fields now (`source`, `engine`, `input_chars`, `first_audio_ms`, `playback_ms`, `cancelled`, `eta_shown_ms`) so v1.2 does not break the ledger or every deployed QML config.

---

## Key Findings

### Recommended Stack

**Add nothing.** The stack research exercised every proposed capability in the project venv and closed the only gap (charts) with ~120 lines of inline SVG. No matplotlib (40 MB wheel), no pandas, no psutil, no sqlite3, no pydantic, no orjson, no jinja2 — each was rejected with a stated threshold at which it would become justified, and none of those thresholds are met at ~1 KB/run and one consumer.

**Core technologies:**

- **Python 3.12.12 (existing `.venv`)** — runtime; all APIs used exist here. `statistics.linear_regression` needs 3.10+, `datetime.UTC` 3.11+. `os.process_cpu_count` is 3.13-only — use `len(os.sched_getaffinity(0))`.
- **`time.perf_counter_ns` / `time.time_ns`** — all durations monotonic; wall clock only for `ts` / `eta_epoch` / `expires_at`. Never subtract `time.time()` for elapsed.
- **`tempfile.mkstemp` + `os.replace`** — atomic `status.json`; same-directory rename is atomic for the 100 ms reader. `Path.write_text()` is **not** atomic and is the current PID-write bug.
- **`statistics`** (median, `quantiles(n=10)`, `linear_regression`) + ~15 lines of MAD/log-EWMA — robust fit without numpy, so the module imports in ~30 ms and tests need no audio/GPU.
- **Append-only JSONL (`O_APPEND`, one `os.write`)** — ledger; `fcntl.flock` only around rotation, never on the hot path.
- **`json` with `allow_nan=False`** — a bare `NaN` blanks the QML consumer (`JSON.parse` rejects it).
- **Inline SVG + `string.Template` + `csv.writer` + `html.escape`/`xml.sax.saxutils`** — self-contained offline report, no JS, no CDN, no fonts.
- **`/proc` + `/sys` (+ optional `nvidia-smi`/`rocm-smi`)** — hardware fingerprint; probes are best-effort and never raise.
- **Quickshell 0.3.2 `FileView.watchChanges` + `JsonAdapter`** — parent-directory watching survives `os.replace` (verified in `src/io/fileview.cpp`). **QML `int` is 32-bit**: epoch fields must be `real`.
- **`unittest`** (existing suite style) with injected clock/paths — no `freezegun`, no `sleep`.

**Measured facts that drive ordering:** `import voice` ≈ 0.32–0.60 s, of which `sounddevice` ≈ 250–320 ms and `from faster_whisper import WhisperModel` ≈ 245–260 ms; bare interpreter ≈ 76 ms. `voice --status` measured 0.44 s wall / 523 % CPU (user reports 1.15 s). Model load is 2.2–3.0 s on this machine and is the dominant cold-start term. Clean decode RTF is ~0.217–0.247 after subtracting load; a near-linear fit with a small intercept is justified, a quadratic is not.

**Detail:** `STACK.md` (integration points are line-mapped to `voice.py`).

### Expected Features

The feature research separates the *number* from the *proof* and treats both as core. Feature IDs below are the roadmap's requirement handles.

**Must have (table stakes) — all P1, all in v1.1:**
- **Immediate single-number ETA at stop** (TS-1) — published within one frame of the `transcribing` transition, **before** `load_model()`; never `"Calculating…"`
- **Stage-aware estimate** (TS-2) — `load + decode + finalize`; load runs after stop on every run, so ignoring it makes short dictations wildly wrong
- **Formatting rules** (TS-3) — integer seconds, floor 1 s, `~7s` under a minute, `1:20` above, fixed width
- **Continuous across 180 s chunk boundaries** (TS-4) — global remaining, never restart per chunk
- **Graceful overrun** (TS-5) — floor at 1 s → short grace → indeterminate glyph; record `overrun`/`overrun_ms`
- **Fallback-aware correction** (TS-6) — a silent GPU→CPU retry is a 10–30× slowdown today
- **Transcribing visually distinct from recording** (TS-7), **no ETA while recording** (TS-8), **ETA failure never blocks transcription** (TS-9)
- **Click-through to report, scoped to transcribing/typing/wrap-up** (TS-10); inert during recording
- **CLI parity** (TS-11) — `--status` reports state + ETA, plus `--json`
- **Per-run ledger** (TS-17) with predicted vs actual, stages, audio/voiced seconds, both segment counts, char counts, no text; **durable storage** (TS-18) outside `/run`
- **Silent calibration** (TS-12), **cold start always yields a number** (TS-13), **config-keyed lookup with global fallback** (TS-14), **outlier-robust statistics** (TS-15), **reset/disable** (TS-16)
- **Report** (TS-19/20/23) — predicted vs actual, error over time, offline self-contained HTML opened by CLI and pill click; **CSV export** (TS-22); **retention + deletion** (TS-24); **privacy + schema stated in the report** (TS-25)
- **Privacy baseline** (TS-30/31/32/33) — allowlist only, zero network in the metrics path, kill switch, documented schema

**Should have (differentiators) — mostly in v1.1, some to v1.1.x:**
- **Mid-run correction from Whisper segment timestamps** (DF-1) — in scope; the only change to the inference hot path, and the highest-risk refactor in the milestone
- **Per-config self-calibration** (DF-2) and **provenance per run** (DF-3: `prior`/`mixed`/`calibrated` + `n`) — this is the clean resolution of "single number vs confidence UX": the pill stays a number, the report explains where it came from
- **Conservative bias** (DF-6) — p60–p75 capped at +15 %, not the mean
- **Convergence view** (DF-7), **drift downweighting** (DF-8), **accuracy on demand in `--doctor`** (DF-5), **warm start** (DF-4), **outlier detection** (DF-15)
- **Opt-in bounded outlier capture** (TS-26..29) — in scope but staged last; audio only, never text

**Defer (v1.1.x / v2+):**
- **Scatter + per-config tables** (TS-21, DF-10, DF-11) — need enough real data to be worth looking at
- **Replay harness** (DF-16), **benchmark seeding** (DF-9) — DF-9 only if cold-start error is measured to matter
- **TTS synthesis + playback ETA** (DF-20/21) — v1.2; the schema seams (TS-34/35/36) ship now

**Anti-features confirmed:** ranges, percent, tenths, `"Calculating…"`, ETA during recording, progress bars, `+12s` count-ups or red "SLOW", an ML/regression model, auto-opening the report or toasting on completion, a manual fudge-factor multiplier as primary UX, confidence labels in the pill, a calibration wizard, shared/global calibration, a live dashboard daemon, auto-refresh, storing argv/transcript text/cloud sync/hashed user IDs, an always-on rolling audio buffer, unbounded corpus growth.

**Detail:** `FEATURES.md` (numbered IDs, complexity, dependency graph, MVP split, competitor archetypes).

### Architecture Approach

Keep `voice.py` as the orchestration/OS layer and add **exactly one** pure companion module, `voicemode_telemetry.py`: schema constants, atomic JSON writes, JSONL append/read/rotation, the pure predictor, report formatters, and a `RunTelemetry` I/O adapter. Import direction is acyclic (`voice.py → voicemode_telemetry.py`), all paths and clocks are injected (mirroring the existing `read_pid_state(path=PID_FILE)` seam), and the module never imports `numpy`/`sounddevice`/`faster_whisper`, so its tests run without audio or GPU. Fallback if the split is rejected: the same functions at the end of `voice.py` with identical signatures — the design does not depend on the file boundary, only test speed and monolith growth do.

**Major components:**

1. **`voicemode_telemetry.py` (new)** — schema v1, `atomic_write_json`, `append_record`/`load_records`/rotation, `wav_duration_s`, pure predictor (`predict_plan`, `predict_remaining`), pure formatters (`format_terminal`/`csv`/`html`), `RunTelemetry`.
2. **`run_background_recording` (major modification)** — instantiate `RunTelemetry`, call it at every transition, heartbeat every 5 s while recording, per-segment events, one terminal ledger record last in `finally` after cleanup and `remove_pid`.
3. **`transcription_watchdog_handler` (modified)** — optional trailing `telemetry`/`segment_index` params; writes a timeout status + ledger row + corpus copy before `os._exit(1)`, all bounded and exception-swallowed.
4. **`toggle_background_recording` (small)** — stale `.status-*.tmp` cleanup; **never** writes `status.json`.
5. **`parse_args` / `main` (modified)** — `--report` family, `--capture-corpus`, dispatched before any model work; `--report` must never import Whisper.
6. **`Voice.qml` / `VoicePill.qml` (external, dotfiles)** — second `FileView` for the status contract, ETA binding, click handler; PID-derived state untouched.
7. **`Recorder`, `load_model`, `transcribe`, `insert_text`, PID helpers (`pid`/`state` format)** — unchanged in *behavior*; `transcribe`'s consumption loop is refactored for timing/progress.

**Key patterns to follow:** authority + enrichment split (PID file vs `status.json`); single-writer append-only ledger with reader-side tolerance; atomic replace for the polled contract; telemetry as a best-effort observer that flips `enabled=False` after one hard failure; pure predictor with injected I/O; stage-timing accumulator assembled once in `finish()`; fail-open contract versioning (`schema: 1` on every object, additive-only within a version).

**Non-negotiable architectural constraints:** no new PID state strings (any unknown state falls through `toggle_background_recording` and **spawns a second worker**; the bar's switches have no default case); no daemon or model pre-warm; `status.json` written only by the worker; no telemetry I/O from the audio callback; terminal ledger row **before** terminal status **before** `remove_pid`.

**Detail:** `ARCHITECTURE.md` (lifecycle diagram, transition table, persistence boundaries, predictor key hierarchy, failure modes, test seams).

### Critical Pitfalls

Six that will silently produce a plausible-looking wrong product. All six are Phase 6 work except where noted.

1. **Timing `transcribe()` instead of consuming the generator** — the call only runs VAD/feature extraction; the 9–46 s of decode happens during iteration. Measured symptom: `decode_ms` ≈ 0.1–0.3 s for every clip, ledger learns RTF ≈ 0, every ETA is minutes low. *Avoid:* time the consumption loop, emit `vad_features_ms`/`decode_ms`/`load_ms`/`finalize_ms` separately, and add a yielding-fake-generator test.
2. **Mixing five incompatible clocks** — `perf_counter`, `strftime` log headers, QML `Date.now()`, `/proc/uptime`, and persisted wall time. `/proc/uptime` and `time.monotonic()` differ by 4.39 s after suspend here. *Avoid:* the producer computes every duration; persist `epoch_ms` as the canonical key plus `local_iso`/`utc_offset_min`/`tz_name` for display; QML displays durations and never subtracts a Python timestamp from its own clock.
3. **Measuring the wrong boundary** — keypress → `--toggle` process start → SIGUSR1 → decode → typing → PID removal all give different "actuals"; `--toggle` alone costs 0.4–1.1 s today and typing adds 1–2 s. *Avoid:* define `text_ready_ms` (the ETA target: stop → text begins inserting) and `e2e_ms` and `insert_ms` separately, and record `stop_dispatch_ms` so the predictor is not blamed for import cost.
4. **One temperature-fallback outlier destroys calibration** — adding the measured 15 s → 55 s sample turns a clean fit (`1.73 + 0.2472×audio`) into `25.7 + 0.0717×audio`, wrong in both directions. *Avoid:* robust medians (median RTF 0.2375 on clean data), `outcome` + `anomaly_reason` per run, per-segment `Segment.temperature`/`compression_ratio`/`avg_logprob` as evidence (never text), keep anomalies in the ledger and show them in the report, never evaluate on winsorized data.
5. **Folding model load into the slope** — a 4-point fit puts load in a ~1.7 s intercept while real load is 2.2–3.0 s; 180 s looks fine, 5 s clips are 30–50 % low and a 0.3 s tap can go negative. *Avoid:* measured `load_ms` as its own term with a floor, clamp `eta ≥ 1 s`, a short-clip bucket, and leave-one-out validation reported as errors, not confidence intervals.
6. **Calibration contamination across configs and hardware** — `ModelState.requested_device` stores `args.device`, so `auto` (which resolves to CUDA) is recorded as `"auto"` and CPU/GPU sessions pool. *Avoid:* key on the **resolved** device/compute type via `actual_backend()` / `model.model.device`; exclude cold, fallback, timeout, diagnostic and contended runs from calibration; version the predictor (`eta_model_version`).

**Also critical, and all Phase 6:** non-atomic `status.json` plus two sources of truth (C8); the real duplicate-worker race at `voice.py:1661-1706` where a 300 ms wait is shorter than the child's 0.4–0.8 s import (C9); stale state after watchdog/`os._exit`/cancel/SIGKILL, where QML maps any PID disappearance during `transcribing` to "Typing…" so a crash looks like success (C10); polling `voice --status` from the bar at 523 % CPU (C11); and 10 Hz synchronous `FileView` reloads plus layout churn (C12, Phase 9).

**Detail:** `PITFALLS.md` (19 critical + 12 moderate + 7 minor, each with warning signs and a phase assignment, plus a "looks done but isn't" checklist and recovery table).

### Contracts to Freeze in Phase 6

Two files, both schema-versioned, both written only by the worker. Pick **one** env-var vocabulary now — the researchers proposed three different names for the same switches (`VOICE_METRICS`/`VOICE_TELEMETRY`, `VOICE_CORPUS_CAPTURE`/`VOICE_CAPTURE_OUTLIERS`/`VOICE_CAPTURE_ANOMALIES`); pick one, alias the losers, document it.

**`status.json`** (runtime, tmpfs, advisory, `0600`, atomic replace, no `null`s for adapter-typed fields): `schema, pid, run_id, pid_start_ticks, state (PID vocabulary only), phase (setup|recording|finalizing|model_load|segment|inserting|done|error), started_at, updated_at, expires_at, recording{...}, progress{...}, eta_epoch (epoch **seconds** as `real`), eta_remaining_s, eta_confidence, eta_source, busy, report_path, message`. Validity gate for consumers: `schema == 1 && pid == pid-from-pid-file && state matches && now < expires_at`. Under ~600 bytes. `eta_*` may be null only while recording.

**`metrics.jsonl`** (persistent, `0700`/`0600`, append-only, one record per run, rotate ~5 MB): `schema, kind, mode, run_id, started_at/ended_at (epoch_ms), outcome/enum, error_stage, error_type, config{model,device,compute_type,beam_size,vad_filter,language,chunk_s}, backend{requested,actual,fallback}, recording{duration_s,audio_s,chunk_s,segments,sample_rate,xruns}, timings{finalize_ms,model_load_ms,decode_ms,insert_ms,total_ms}, segments[{i,audio_s,decode_ms,ok,chars,watchdog}], decode{temperatures,temp_used,fallbacks,avg_logprob,max_compression_ratio,no_speech_prob,condition_on_previous_text,had_initial_prompt,initial_prompt_chars}, vad{duration_after_vad_ms,ratio,no_speech_prob_max}, prediction{total_s,shown_ms,revised_ms,error_s,source,key_level,n_samples,confidence,eta_model_version}, host{cpu,affinity,...}` plus the **TTS reservation**: `source (stt|tts), engine, input_chars, first_audio_ms, playback_ms, cancelled`.

**Never** serialize `segment.text`, `segment.words`, `info.transcription_options` (it *contains* `initial_prompt`/`hotwords`/`prefix`), WAV paths, argv, hostname, username, or clipboard contents. Enforce with a key/type snapshot test plus a regex scan of synthesized records for `text|prompt|hotword|prefix|/tmp|\.wav|file`.

---

## Implications for Roadmap

### Reconciling the Four Proposals

The researchers disagreed on phase count (3–6) and on the order of the last two. This is the recommended single ordering, with the tradeoffs stated.

| Source | Proposed shape | Taken | Changed, and why |
|---|---|---|---|
| **STACK.md** | No phase list; 13 line-mapped integration points; "lazy imports first" | Lazy-import-first ordering; module boundary; atomic/append-only mechanics; Quickshell `FileView`/`JsonAdapter` recipe | Nothing rejected — its integration points are distributed across Phases 6–9 as the *how* |
| **ARCHITECTURE.md** | 6 phases: pure module → contract + instrumentation → predictor → report + CLI → corpus → hardening + bar | Module split, authority/enrichment, predictor design, test seams, build order 1–4 | **(a)** Merged its phases 1 and 2: a ledger writer with no writer is not independently verifiable and the schema must freeze exactly once. **(b)** Moved corpus from 5 to last (measurement effect). **(c)** Bar last, not bundled into "hardening" |
| **FEATURES.md** | One MVP bundle, 7 feature groups, outlier lab explicitly "can be the last phase" | The MVP scope (all P1), empty-state report, the defer list | Made the implicit phasing explicit; kept its defer split (TS-21/DF-10/11 → v1.1.x) |
| **PITFALLS.md** | 5 phases (6–10): contract → predictor → bar → report/capture → portability | Phase numbers 6–10, the ordering *logic*, and the entire non-negotiable checklist | **Swapped 8 and 9** (report before bar) and **split capture out of the report phase into 10**. Reason: the user's "click the pill opens the report" makes a bar-without-report a visibly broken feature, and capture is opt-in, needs stable instrumentation, and belongs with portability work |

**Why five and not three or six.** Three collapses either contract+predictor (a predictor fitted to ambiguous numbers, untestable in situ) or predictor+bar (a UI that feels calibrated on poisoned data). Six would require splitting Phase 6 at the module/monolith seam — defensible, but the pieces are mutually dependent (session identity lives in the schema; terminal writes need the ledger writer), and the split does not produce an extra verifiable milestone state. Five phases = five end states you can actually check.

### Phase 6: Foundations, Ledger & Status Contract

**Rationale:** Every downstream phase is either a consumer of this contract or a statistic over this data, so this lands first and freezes once. It is also where every "silently produces fiction" pitfall lives. Lazy imports go first *within* the phase: they remove ~0.5 s from every hotkey press (a larger perceived-latency win than the ETA itself), make `--status` fast enough to be a real diagnostic, and shorten the child's startup window that currently trips the duplicate-worker race.

**Delivers:**
- Lazy `numpy`/`sounddevice`/`faster_whisper` imports (8 `sd.` sites, 1 `WhisperModel` site, `from __future__ import annotations` already present) + an import-budget test (`python -X importtime`, `--status` under 100 ms)
- `voicemode_telemetry.py` (stdlib only, ~600–900 LOC) + `py-modules` entry: schema constants, `atomic_write_json`, `append_record`/`load_records`/rotation, `wav_duration_s`, `parse_duration`, path/clock injection
- Frozen `status.json` v1 and `metrics.jsonl` v1 per the contracts above, **including the TTS reservations**
- Atomic **PID** writes too — same `mkstemp` + `os.replace`, format `pid state` unchanged. This deliberately modifies a component ARCHITECTURE marked "unchanged": PITFALLS verified `write_pid_state` uses `Path.write_text()`, which is the same torn-read bug
- Duplicate-worker fix: `flock` on `state.lock` around read-decide-spawn; never `remove_pid` a live `starting` process whose cmdline matches; the worker re-verifies the PID file still holds its own PID before writing `recording`; `uuid4` `session_id` + `pid_start_ticks`
- Terminal states on every exit path: `finally`, cancel, watchdog (before `os._exit(1)`), error — ledger row → terminal status → `remove_pid`, in that order; `expires_at` TTL
- The timing seam: `segments, info = model.transcribe(...)` then an explicit iteration with an `on_progress(segment.end, info.duration)` callback, covering **both** the happy path and the CPU-fallback branch; `info.duration_after_vad` captured before the first decode; per-segment evidence from `Segment.temperature/avg_logprob/compression_ratio/no_speech_prob`
- Prior-only ETA so `eta_epoch` is never null during `transcribing`, only during recording
- One documented path rule (`status` = `${XDG_RUNTIME_DIR:-…}/voice-stt`, `state` = `${XDG_STATE_HOME:-$HOME/.local/state}/voicemode`, `0700`/`0600`); the QML `/run/user/1000` literal gets deleted in Phase 9, not worked around
- Cheap hardware/config fingerprint (`/proc/cpuinfo`, `sched_getaffinity`, versions, resolved backend, `blake2b(digest_size=8)`, `FP_VERSION`)
- Test migration: patch `voice.RunTelemetry` in the two existing worker tests, extend the watchdog test's expected args

**Addresses:** TS-17, TS-18, TS-30–33, TS-34/35 (seam), DF-3 (fields), TS-9, half of TS-11
**Avoids:** Pitfalls 1, 2, 3, 8, 9, 10, 11, 15; Moderate 1, 3, 4, 7, 9, 10; Minor 6
**Uses:** `json`, `os.replace`, `tempfile`, `fcntl`, `wave`, `hashlib`, `resource`, `/proc`
**Note:** this is the largest phase — plan it as ~6 plans (imports → module primitives → atomic/single-writer/identity → terminal states → timing seam → prior-ETA wiring + test migration). If it exceeds one execution wave budget, split mechanically at module-vs-wiring and number it 6.1/6.2 without renumbering later phases.

### Phase 7: ETA Engine & Calibration

**Rationale:** The predictor can only be built once correctly shaped samples exist, and it is pure — so it can be developed and tested against synthetic ledgers with no hardware, no audio and no waiting. Building it before the contract would mean fitting to ambiguous numbers; building it after the bar would let the UI "feel" calibrated while the math is wrong.

**Delivers:**
- Pure predictor: `total = finalize + model_load + rate × Σ(audio_after_vad) + insert`, `rate = Σdecode/Σaudio` (**ratio of sums**, never mean of ratios)
- Key hierarchy with `MIN_N = 3` (rate: exact → drop `chunk_s` → drop `vad_filter` → drop `beam_size` → `(model,device,compute)` → `(model,device)` → `(model,)` → prior; load key shorter); chosen level and `n` recorded on the prediction
- Shrinkage `(n·median + k·prior)/(n+k)`, MAD-based confidence ladder, conservative `max(median, p60)` capped at +15 %, rate clamp `0.02…20`, `eta ≥ 1 s`, `eta ≤ watchdog remaining`
- Exclusion policy applied to **calibration only**, never deletion: `outcome != ok`, `fallback`, `timeout`, `cold`, `diagnostic`, `load1 > 0.7 × usable_cpus`, `rtf > 3 × median`; cold = first session since boot or `load > 2 ×` fingerprint median
- Resolved-backend keying via `actual_backend()` (the `device="auto"` trap), plus `chunks_expected` vs `chunks_transcribed`, `finalize_ms`, and 44.1 kHz resampling coverage
- Mid-run correction after each segment (weight `done/(done+2)` blended with the keyed median), VAD-based downward revision from `duration_after_vad`, monotone-non-increasing display with marked upward revisions at most once per 2 s
- Overrun state machine `counting → floor(1s) → grace(3s) → indeterminate(…)`; short-clip and `vad_ratio < 0.2` buckets; `no_speech` outcome
- Priors as labeled seeds (CPU int8: load 2.5 s, RTF 0.24 from measurement; ARCHITECTURE's per-family table as the *shape* only), 1.2× first-N-session margin, `~` prefix when prior-based
- `--status --json` with ETA/phase/calibration source; `--reset-calibration [--config KEY]`; `VOICE_ETA=off` / metrics kill switch
- **Evaluation protocol defined before collecting**: per-bucket n, median absolute error, p90 absolute error, median signed bias, share of runs where the ETA was exhausted, stratified short/medium/long × cold/warm × device × outcome, out-of-sample (rolling origin or at minimum leave-one-out), scoring `eta_shown_ms` (not a recomputed value)

**Addresses:** TS-1, TS-2, TS-3, TS-4, TS-5, TS-6, TS-8, TS-12, TS-13, TS-14, TS-15, TS-16, DF-1, DF-2, DF-3, DF-4, DF-6, TS-11
**Avoids:** Pitfalls 4, 5, 6, 7, 13, 17 (policy), 18, 19; Moderate 1, 6, 9
**Depends on:** Phase 6's fields. **Blocks:** everything user-visible.

### Phase 8: Accuracy Report & Click-Through

**Rationale:** The report is what makes the number falsifiable — without it v1.1 is "an ETA" with no way to prove it works — and it is also the click target the user explicitly asked for, so it must exist before the pill ships a click. It is pure Python and fully testable, unlike the QML consumer that follows.

**Delivers:**
- Pure formatters `format_terminal` / `format_csv` / `format_html` sharing the ledger reader and aggregation helpers
- `--report` family: `--report-format {terminal,csv,html}`, `--report-since`, `--report-last`, `--report-out`, `--report-open`; dispatched in `main()` before model work; **never imports Whisper**
- `report.html` generated at worker finish from the last 200 runs (≈1–5 ms) so the pill's click is instant, written atomically; `--report` reads the full bounded ledger on demand
- Charts as hand-written inline SVG: predicted vs actual, error % over time, stacked stage bars for the last 20 runs, residual histogram; `<title>` for native tooltips, no JS
- CSV export (one row per run, stable header), `--forget-metrics`, retention cap
- Visible privacy footer: schema version, what is stored, where, how to delete — plus the precise clipboard caveat (`insert_text` copies the transcript to the clipboard today, so "voicemode stores no transcript" is only true of the telemetry)
- `docs/telemetry.md` (schema contract, privacy, opt-in capture, deletion)
- `xdg-open` helper: `Path.as_uri()`, argument list (never a shell string), `shutil.which` guard, `notify-send` + printed path fallback, detached; single-flight `flock`; regenerate only if ledger mtime/size changed; never in the GUI thread
- Empty state for a fresh install ("dictate once to see data"), not a blank page
- **Tradeoff accepted:** the report ships before there is a body of real data, so its accuracy analytics are thin. That is why headline/deep analytics land in Phase 10 and Phase 8 ships the two headline charts + tables.

**Addresses:** TS-19, TS-20, TS-22, TS-23, TS-24, TS-25, DF-5 (basic), DF-12, DF-13
**Avoids:** Pitfall 15 (report), Moderate 5 (`xdg-open`), Moderate 11 (generation ordering/races), Moderate 12 (report side), Minor 4, Minor 7
**Uses:** `string.Template`, `csv`, `html`, `xml.sax.saxutils`, inline SVG

### Phase 9: Quickshell ETA Integration

**Rationale:** The consumer phase. The contract is frozen (6), the numbers exist (7), and the click target exists (8), so this is the one phase where "ETA replaces `Transcribing...`" becomes true. It is also the riskiest external integration: a separate repo behind stow symlinks, QML's 32-bit `int`, `watchChanges` defaulting to **false**, and a 100 ms poll that currently does synchronous GUI-thread I/O across five files.

**Delivers (bar, in `/home/pera/github_repo/.dotfiles` — `package restow quickshell/.config/quickshell`):**
- `Voice.qml`: `statusPath` from `XDG_RUNTIME_DIR` (delete the `/run/user/1000` literal), `FileView { watchChanges: true; onFileChanged: reload() }` + `JsonAdapter`, `real` for `eta_epoch`/`expires_at`/`started_at`, sentinels (`0`/`""`/`-1`) instead of nulls, validity gate (`schema==1 && pid==sttPid && state matches && now<expires_at`), PID-derived `overallState` **unchanged**, unknown state rendered as **busy**, not idle
- Cadence discipline: 50 ms debounce on `onFileChanged`, 1 s fallback poll, 1 Hz label updates, 2–3-strike tolerance for empty reads, `printErrors: false` with one-shot logging, no `reload()` of the status file every 100 ms, **no process spawn**
- `VoicePill.qml`: ETA text **replaces** `"Transcribing..."`; fixed/minimum width with tabular figures; distinct color from recording via theme palette roles **plus** a `~` glyph/prefix, never the error color, verified in light/dark and grayscale; clamp at `1s` then `Finishing…` on overrun, never `0s`/negative; no ETA during `starting`/`recording`
- Click: enabled only in `transcribing`/`typing`/`wrapup` (still inert during recording), `Qt.PointingHandCursor`, left-button release-inside only, validates `status.report_path.startsWith(stateDir)`, then `Quickshell.execDetached(["xdg-open", uri])`; no auto-open, no completion toast (v1.0 focus-safe policy)
- **Vendored copies** under `integrations/quickshell/` in this repo as the reviewed reference implementation + contract snippet

**Acceptance requires both artifacts:** the dotfiles commit (live) and the vendored copy (reference) updated in the same phase; document that the symlink target is authoritative and the repo copy is the checked-in reference.

**Addresses:** TS-7, TS-10, the user's ETA-text/color/click decisions, TS-36 (data-driven labels)
**Avoids:** Pitfalls 12, 16, 17; 8/9/10 (consumer side of the gates); Moderate 4, 8; Minor 1, 2, 3, 5

### Phase 10: Accuracy Loop, Portability & Hardening

**Rationale:** Everything here needs the full loop running and real sessions behind it — and outlier capture specifically must come after instrumentation is stable, because capture I/O inside the timed path changes the latency it is measuring.

**Delivers:**
- Always-on outlier **detection** (residual + absolute thresholds, `rtf > 3 ×` bucket median, fallback/watchdog flags); opt-in bounded **capture** only (`VOICE_CORPUS_CAPTURE`-style flag, default off): timestamp before any capture I/O, hardlink/rename when same filesystem else async copy after the decode timestamp, caps (20 files / 250 MB per run, 7-day retention), `0700`, `meta.json` with numeric evidence only, `--outliers list` / `clean`, `statvfs` free-space check, never uploaded, never embedded in the report
- Convergence view, drift downweighting, scatter, per-config calibration table, run table filters
- `--doctor`: telemetry/ledger health, resolved paths, fingerprint, accuracy block (median abs %, p90, n, last calibration), stale-status mismatches
- `--metrics --json`, `--metrics-schema`, `--export-csv --redact`
- Portability matrix: CPU int8 (verified here) / CUDA float16 (detect + record, never enable ROCm) / AMD & Intel Arc (detect, stay CPU int8, key on resolved backend); vendor probes (`nvidia-smi` once per session after load with a timeout, `rocm-smi` only when sysfs says AMD) — **no `get_supported_compute_types("cuda")` without a guard, it raises**
- Second-user (`UID != 1000`) and unset-`XDG_RUNTIME_DIR` tests; 44.1 kHz + multi-chunk resampling path; cold boot / cold page cache; 4 GB-RAM / OOM; read-only state dir and disk-full; Quickshell version-matrix note; diagnostics must not pollute the ledger or warm the cache silently
- TTS readiness verification: reserved fields present, QML branches on `source`, no TTS RTF in the STT prior, `cold_assets` outcome reserved
- Final scope decision on the deferred differentiators (replay harness DF-16, benchmark seeding DF-9) — recommend leaving both out of v1.1

**Addresses:** DF-5, DF-7, DF-8, DF-10, DF-11, DF-14, DF-15, DF-18, DF-19, TS-21, TS-26–29, TS-6 (cross-hardware validation)
**Avoids:** Pitfall 14; cross-hardware closures of 6, 7, 13, 18, 19; Pitfall 16; Moderate 10, 11, 12; Minor 5

### Phase Ordering Rationale

- **Contract before consumer — hard dependency.** `status.json`/`metrics.jsonl` v1, session identity, atomic writes and terminal states (Phase 6) must exist before anything reads or calibrates. Bad history is not migratable; it must be deleted, which is why the safety rails (race, atomicity, terminal states, timing seam, import split) precede the first collected record.
- **Report before bar** (divergence from PITFALLS). The user's click-opens-report decision makes a clickable pill without a report a broken feature in the phase that ships it. The cost is a thin-data report in Phase 8; the mitigations are an explicit empty state and deferring deep analytics to Phase 10.
- **Predictor before reports, capture after instrumentation.** Statistics need a defined shape; capture must not bias the numbers, so it lands after the timed path is stable and after the report can show what was excluded.
- **One new module, one new file contract, zero new dependencies.** The architecture keeps the monolith as the OS layer and puts pure logic behind an injectable boundary — that is what makes the predictor testable without audio, GPU, or a clock.
- **Nothing here introduces a daemon, model pre-warm, new PID state, or network call.** Each is explicitly an anti-pattern in at least two research files.

### Non-Negotiable Constraints → Phase Map

| Constraint (from PITFALLS) | Lands in | Why it cannot slip |
|---|---|---|
| Duplicate-worker race (`flock`, session id, no `remove_pid` on live `starting`) | 6 | Two writers per session corrupt state and the ledger |
| Atomic `status.json` **and** PID writes | 6 | Torn reads at 100 ms produce idle flicker and false states |
| Terminal states on watchdog / SIGKILL / cancel / error | 6 | A crash currently renders as "Typing…" success; failures vanish from the report |
| Timing seam around the lazy generator | 6 | Wrong `decode_ms` invalidates every sample ever collected |
| Import/CLI split (lazy imports, import budget test) | 6 | Enables `--status` as a diagnostic; no subprocess polling; shrinks the race window |
| TTS ledger/status fields reserved | 6 | Adding them later breaks the ledger and every deployed QML config |
| Single writer for `status.json` (worker only) | 6 | Out-of-order phase regressions |
| No text / no paths / no network in telemetry | 6 (+9 report, +10 capture) | A privacy bug requires deleting history |
| PID file stays the state authority; no new PID states | 6 + 9 | New state → second worker spawned; bar switch has no default |
| Cold model load stays; no daemon/pre-warm | 6 + 10 | Out of scope and changes the failure model |

### Research Flags

**Needs deeper research during planning:**
- **Phase 9 (Quickshell/QML)** — the highest-uncertainty phase and the only one entirely outside this repo. Needs: the theme's palette roles in illogical-impulse (which role resolves to a color distinct from recording in both themes, and whether the pill's `currentColor`/`tertiary` is the right hook), the exact stow/symlink layout for `quickshell/.config/quickshell`, `FileView`/`JsonAdapter` behavior after suspend/resume and under a not-yet-created directory, and `execDetached` argument semantics from a Hyprland-launched bar. Also needs a UI-SPEC (`/gsd-ui-phase`) before implementation — the color/width/glyph decisions are design decisions, not code decisions.
- **Phase 10 (cross-hardware, partially)** — CUDA/ROCm detection magnitudes and probe failure modes were never executed here (no such hardware). Plan the detection defensively and validate the matrix by replay, not assumption. Second-user/UID and unset-`XDG_RUNTIME_DIR` behavior also needs a live check.

**Standard patterns (skip research-phase):**
- **Phase 6** — every seam is verified and line-mapped; the mechanics are POSIX and stdlib. The only judgment call is how aggressively to refactor the monolith.
- **Phase 7** — `statistics` + robust medians + shrinkage are well-trodden; the design is fully specified and testable with synthetic ledgers.
- **Phase 8** — stdlib formatting + inline SVG; template and escaping rules are settled. Aesthetic quality is a design question answered by the UI-SPEC, not a research question.

---

## Confidence Assessment

| Area | Confidence | Notes |
|---|---|---|
| Stack | **HIGH** | Every stdlib capability exercised in the project venv; versions read from installed distributions; "zero new dependencies" proven by building the report with ~120 lines of SVG. Only gap is report aesthetics |
| Features | **MEDIUM-HIGH** | Codebase and `faster-whisper` claims read directly (HIGH); UX claims cross-checked against NN/G and others (MEDIUM); competitor archetypes not hands-on (LOW) |
| Architecture | **HIGH** | Integration points read from source with line numbers; persistence/contract design follows POSIX and XDG semantics; predictor priors explicitly MEDIUM/LOW placeholders |
| Pitfalls | **HIGH** | Verified against installed `faster-whisper` 1.2.1, CTranslate2 4.8.2, Quickshell 0.3.2 source and `voice.py`; magnitudes beyond this machine are MEDIUM/LOW |

**Overall confidence:** HIGH for the approach, module boundary, contracts and ordering. MEDIUM for predictor accuracy on non-local hardware and for QML runtime edge cases.

### Gaps to Address

- **Priors are unvalidated.** CPU-int8 on an i5-13500 is the only measured regime; CUDA and AMD numbers are documented-interface guesses. Ship them as clearly labeled seeds behind `calibrations_n`/confidence, never as truth, and validate in Phase 10.
- **Overrun copy vs "single number."** PITFALLS recommends `Finishing…` after the 1 s floor + 3 s grace; that is a word, not a second number or a range, but it should be confirmed during requirements so it is not read as a violation of the user's decision. Recommended: keep it, and document that `…` is a state, not a value.
- **ETA endpoint needs a one-line confirmation.** Research recommends "until text begins inserting" (decode + finalize inside; `typing` separate, recorded as `typing_ms`). The alternative ("last character typed") makes typing a first-class stage and changes the copy.
- **"Segment" is overloaded.** Confirm `chunk` (180 s WAV) vs `whisper_segment` (decoder output). The ledger stores both; the UI exposes neither.
- **Report generation trigger has three proposals** (at worker finish / on demand / cached on click). Recommended resolution: generate `report.html` at worker finish from the last 200 runs for instant click, plus `--report` for the full bounded ledger on demand, with `flock` single-flight and an mtime cache.
- **Env-var vocabulary is inconsistent across research files.** Pick one set in Phase 6 (`VOICE_METRICS`, `VOICE_STATUS`, `VOICE_ETA`, `VOICE_CAPTURE_OUTLIERS`, `VOICE_METRICS_DIR`, `VOICE_PREDICT_PRIOR_RTF`), alias or drop the others, and document them in `--doctor`.
- **No ETA color token exists yet.** This is a UI-SPEC/discuss decision, not something to invent in QML; verify contrast on the real bar background and in grayscale.
- **Vendored vs live QML ownership is a sync hazard.** The dotfiles symlink target is what runs; the repo copy under `integrations/quickshell/` is the reviewed reference. Both must be updated in Phase 9 and the pairing documented, or they will drift silently.
- **Peak RSS is 2,129 MB.** On a 4 GB machine the ETA can be off by an order of magnitude or the process gets OOM-killed. Not in scope to fix, but add a `MemAvailable` warning + margin and document the limitation.
- **`--save-dir` and v1.0's retained failure WAVs already exist.** The outlier capture feature must bound and reuse that behavior, not add a second parallel retention mechanism, and the privacy documentation must cover it.

---

## Sources

### Primary (HIGH confidence)
- Project `.venv` (`importlib.metadata`) — `faster-whisper 1.2.1`, `ctranslate2 4.8.2`, `numpy 2.5.3`, `sounddevice 0.5.6`, `kokoro-onnx 0.5.0`, `edge-tts 7.2.8`, `soundfile 0.14.0`, `PyYAML 6.0.3`, Python 3.12.12
- `.venv/lib/python3.12/site-packages/faster_whisper/transcribe.py` — `info` returned eagerly (1012-1022); VAD before return (884-893); scalar temperature promoted (981-984); fallback loop (1432); `restore_speech_timestamps` (1844-1870); `TranscriptionOptions` carries text-bearing prompt fields
- `/usr/src/debug/illogical-impulse-quickshell-git/quickshell/src/io/fileview.{hpp,cpp}` + `quickshell-io.qmltypes` — `watchChanges` defaults false, parent-directory watching with path re-add, synchronous read on reload, `JsonAdapter`, `execDetached` list arg
- `voice.py` — imports 40-42; `Recorder` 150-337; `load_model`/`transcribe` 616-680; `report_stt_failure` 712-796; PID helpers 799-859; watchdog 923-952; `insert_text` 1040-1180; TTS 1400-1544; `background_argv` 1623-1658; toggle 1661-1706; `run_background_recording` 1709-1865; `print_status` 1991-1999; doctor 2305-2419; `parse_args` 2884-3085; `main` 3088-3150
- `python -X importtime` measurements in the venv — `sounddevice` 250–344 ms, `faster_whisper` 209–260 ms, `av` 140 ms, bare interpreter 76 ms, `import voice` 0.32–0.60 s
- `ctranslate2` runtime probes — `get_cuda_device_count()` returns 0 safely; `get_supported_compute_types("cuda")` raises on driver mismatch
- Machine measurements — `voice --status` 0.44 s wall / 523 % CPU; peak RSS 2,129 MB; `/proc/uptime` vs `monotonic()` delta 4.39 s; clean fit `1.73 + 0.2472×audio`; outlier fit `25.7 + 0.0717×audio`; median RTF 0.2375 after 2.4 s load
- `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm/*`, `os.sched_getaffinity` — i5-13500, Intel 8086:4680/i915, 20 usable CPUs, no `nvidia-smi`/`rocm-smi`
- XDG Base Directory Specification v0.8; Python docs (`os.replace`, `statistics`, `tempfile`, `fcntl`)
- `.planning/PROJECT.md` — user decisions (single number, immediate, distinct color, click opens report, no transcript text, TTS deferred, cold load retained)
- `.planning/research/{STACK,FEATURES,ARCHITECTURE,PITFALLS}.md` — peer research synthesized here

### Secondary (MEDIUM confidence)
- NVIDIA `nvidia-smi` and AMD `rocm-smi` command shapes; sysfs DRM vendor IDs — documented and stable, not executed against hardware
- Nielsen Norman Group, "Progress Indicators Make a Slow System Less Insufferable" and "Response Times: The 3 Important Limits" — determinate feedback above ~10 s, never stall, allow extra time
- UX Tigers, "Progress Indicators Ease the Wait" — same conclusions with the "must not stall, lie, or reset" caveat
- Stack Overflow, "Smart progress bar ETA computation" — EWMA/rolling-rate smoothing
- Quickshell 0.3.0 docs (FileView, JsonAdapter) cross-checked against the installed 0.3.2 tree

### Tertiary (LOW confidence — needs validation)
- Predictor seed priors (RTF 0.24, load 2.5 s) and the per-model-family prior table — a handful of runs on one machine, intentionally disposable
- Competitor/archetype behavior (Buzz/MacWhisper, whisper.cpp/yt-dlp/ffmpeg) — characterized by pattern, not hands-on testing
- Cross-hardware RTF magnitudes (CUDA, AMD, low-memory) — inference from documented interfaces

---

*Research completed: 2026-10-26*
*Ready for roadmap: yes*

