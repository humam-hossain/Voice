# Feature Research

**Domain:** Local desktop dictation utility (Wayland/Hyprland) — latency prediction, telemetry, and status-bar ETA
**Researched:** 2026-10-25
**Confidence:** MEDIUM-HIGH overall — codebase dependency claims HIGH (read directly, plus `faster-whisper` API verified in the project venv); UX claims MEDIUM only where independently cross-checked (NN/G, UX Tigers, StackOverflow agree); competitor/archetype claims LOW (not hands-on tested).
**Scope:** v1.1 milestone "Latency Prediction & Telemetry". Existing v1.0 STT/TTS/keybind/daemon features are treated as fixed infrastructure, not re-researched.

---

## How to read this document

Features are numbered (`TS-` table stakes, `DF-` differentiator, `AF-` anti-feature) so roadmap phasing can reference them directly.

Complexity scale, calibrated to this repo (single 4.4k-LOC `voice.py`, 103 tests, no new runtime deps preferred):

| Rating | Meaning |
|---|---|
| **LOW** | ≤1 day; one file or one small function; no cross-process contract |
| **MEDIUM** | Multi-file or cross-process (Python ↔ Quickshell); needs new tests; touches the state machine |
| **HIGH** | New subsystem, cross-repo changes, or accuracy/robustness risk requiring a lab |

"Depends on (existing)" column cites the v1.0 code that must be reused or modified.

---

## 1. ETA display and overrun handling

### Table Stakes

| ID | Feature | Why Expected | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| TS-1 | **Immediate single-number ETA at stop** | User waits at the moment of highest uncertainty; the current static "Transcribing..." is exactly the anti-pattern for waits >2 s | LOW | `Recorder.stop_to_wav()` returns real recorded duration (`voice.py:277-337`); chunk paths/durations; `chunk_seconds()` (`voice.py:895-904`) | Estimate must render **before** model load starts. Recorded duration + WAV frame counts are available instantly. Never show "Calculating..." — that is a static indicator with extra steps |
| TS-2 | **Stage-aware estimate (model load + decode + finalize)** | `load_model()` runs *after* stop (`voice.py:1783-1784`) on every run (fresh child process). Ignoring it makes short dictations wildly wrong | MEDIUM | `load_model()` call site, `transcribe()` loop (`voice.py:1786-1824`), `recorder.stop_to_wav()` | Total = `model_load_prior + Σ(chunk_audio / RTF) + finalize`. Do not model this as "audio_seconds × one factor" |
| TS-3 | **Formatting rules: integer seconds, floor 1 s, never 0/negative, fixed width** | A number that says `0s` while still working destroys credibility; a width-jittering label shifts the whole bar | LOW | `VoicePill.qml` `displayText` (`:50-60`), `implicitWidth` (`:65-67`) | `≤59s` → `"~7s"`; `≥60s` → `"1:20"`. No tenths. Reserve width for the longest expected string |
| TS-4 | **Countdown continuous across 180 s chunk boundaries** | Multi-chunk runs (default `DEFAULT_CHUNK_SECONDS = 180`) currently print per-segment progress only to the log; a per-chunk ETA reset looks broken | MEDIUM | Per-chunk loop (`voice.py:1791-1824`), PID states `transcribing`/`typing` | Compute **global** remaining = remaining chunks × rate + current chunk remaining. Never restart the number at a chunk edge |
| TS-5 | **Graceful overrun: floor → short grace → indeterminate glyph** | Estimates are wrong sometimes; the failure mode must not be "0 s for 40 s" or "+12 s overdue" | LOW | Pill state mapping (`VoicePill.qml:31-60`) | Freeze at `1s` for a grace window (≈3 s), then show `…` in the transcribing color. Never negative, never a count-up. Record `overrun`/`overrun_ms` in the ledger |
| TS-6 | **Fallback-aware correction (GPU→CPU retry)** | `transcribe()` silently retries on CPU int8 on any exception (`voice.py:666-680`) — a 10-30× slowdown with no user-visible change today | MEDIUM | `transcribe()` fallback branch; `ModelState` | On fallback, re-key the predictor to the CPU config and immediately re-estimate (usually into overrun). Ledger records `fallback=true` and excludes the run from GPU calibration |
| TS-7 | **Transcribing visually distinct from recording** | Explicit user preference; also encodes "don't speak, system is working" | LOW | `currentColor` (`VoicePill.qml:37-47`), `pulseAnimation` (`:140-164`) | Recording = primary + breathing pulse; transcribing = tertiary (already) but must be confirmed distinguishable in every theme, and **not color-only** — the ETA text itself is the non-color cue |
| TS-8 | **No ETA while recording** | Recording duration is still changing; a transcription estimate during capture implies knowledge the system doesn't have and distracts from the duration readout | LOW | `formattedDuration` path (`Voice.qml:141-157`) | Do not pre-compute in the parent toggle process either |
| TS-9 | **ETA failure never blocks transcription** | A status nicety must not become a new failure mode | LOW | `run_background_recording()` finalize/except paths | Predictor wrapped in try/except; on any error write no progress file and let the pill fall back to static text. No exceptions may escape the instrumentation hook |
| TS-10 | **Click-through to report, scoped to transcribing/typing/wrap-up** | The pill is currently inert by design; a click target must not conflict with recording | LOW-MEDIUM | `inertMouseArea` (`VoicePill.qml:104-112`) swallows all buttons; new `voice --report`; `xdg-open` | Click during `recording` must stay inert (accidental clicks while talking). Click during `transcribing`/`typing`/`wrapup` opens the report. Cursor affordance only in those states |
| TS-11 | **CLI parity: `--status` reports state + ETA (and `--json`)** | The repo's diagnosis surface should not lag the GUI; scripts/tests need a machine-readable source of truth | LOW | `print_status()` (`voice.py:1991-1999`) currently prints `"recording pid"` whenever *any* worker is alive, ignoring `transcribing`/`typing` | Return state, ETA ms, stage, config key, and `calibration_source`. JSON mode already exists as a repo-wide convention for `--doctor`/`--verify` |

### Differentiators

| ID | Feature | Value Proposition | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| DF-1 | **Mid-run correction from Whisper segment timestamps** | Turns the ETA from a static guess into a live estimate; most dictation UIs never do this | MEDIUM | `transcribe()` (`voice.py:646-680`) currently does `" ".join(segment.text.strip() for segment in segments)` — it consumes the lazy generator without exposing progress; `faster-whisper` returns `info.duration_after_vad` and per-segment `.end` (verified in the project venv) | Refactor to iterate segments with a callback, keeping the CPU-fallback path and `initial_prompt` behavior identical. Progress denominator = `info.duration_after_vad` (fallback `info.duration` if VAD disabled). Correction cadence is one faster-whisper decode window (~30 s audio), so short dictations get no correction — document that honestly |
| DF-2 | **Per-config self-calibration (model × device × compute_type × beam × VAD × language)** | "Works on other people's hardware" only if the predictor keys on config; CPU int8 `small.en` and CUDA float16 `large-v3` are different universes | MEDIUM-HIGH | New ledger; `actual_backend()` / `ModelState`; `args` config | Robust estimator (median or EWMA with shrinkage toward prior) over the last N runs per key. Fall back to global median, then prior. Exclude download runs and GPU→CPU fallback runs from the rate estimate |
| DF-3 | **Calibration provenance recorded per run** (`prior` / `calibrated` / `mixed`, sample count) | Gives honest confidence without putting a range or a "low confidence" badge in the pill | LOW | Ledger schema | The pill stays a single number; the report and `--doctor` explain where it came from. This is the clean resolution of the "single number vs confidence UX" tension |
| DF-4 | **Warm start from recent history** | Avoids acting like a cold machine on the 50th run; first ETA of the session is as good as the last | LOW-MEDIUM | Ledger location/format | Read a small cached summary (per-key aggregates) rather than scanning the full JSONL at stop. Budget <10 ms in the child process |
| DF-5 | **Accuracy surfaced on demand** (`--doctor`: median abs % error, p90, sample count, last calibration) | Makes the ETA falsifiable; users can see it improving | LOW-MEDIUM | `--doctor` framework; ledger | No new UI surface, no notification |
| DF-6 | **Conservative-by-default bias (p60–p75, not mean)** | NN/G guidance: allow extra time; finishing early is a pleasant surprise, overrun is not | LOW | Predictor | Do not overcorrect into comedy lateness: cap the safety margin at ~15 % or 1 s, whichever is larger |

### Anti-Features

| ID | Anti-Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|---|
| AF-1 | Range display ("8–14 s") | Looks more "honest" statistically | Explicit user preference is a single number; a range is unparseable at a glance and wider than the pill | Single number from a conservative quantile (DF-6) |
| AF-2 | Percentage complete in the pill | Familiar from installers | Percent of *what* is undefined across load/decode/finalize/typing; implies precision the model lacks; stalls at 99 % | Seconds remaining (TS-3) |
| AF-3 | Tenths-of-second ticking (`7.9s`) | Feels "live" | Visual noise, false precision, unnecessary 10 Hz redraws in Quickshell | Whole seconds, update ≤2 Hz; recompute from a monotonic completion deadline, not by decrementing |
| AF-4 | `"Calculating…"` placeholder before the first estimate | Seems honest when cold | Violates "ETA immediately at stop"; static indicators are the documented worst option | Prior-based first estimate (TS-1, TS-13) |
| AF-5 | ETA during recording | "Nice to know in advance" | Prediction target is still growing; distracts from the duration readout; invites premature optimization of speech | Show only after stop (TS-8) |
| AF-6 | Progress bar/sweep in the pill | More visual than a number | Too small to read; any stall looks like a hang; percent semantics (AF-2) | Number + color; pulse is reserved for recording |
| AF-7 | Overrun as `+12s` count-up or red "SLOW" | Transparency | Anxiety-inducing for a tool used mid-sentence; red in a bar reads as an error state | Floor + `…` after grace (TS-5); details in the report |
| AF-8 | ML/regression model for ETA | "More accurate" | Training data doesn't exist, uninterpretable, overfits one machine, breaks portability; the physical model is nearly linear in audio seconds | Two-parameter stage model + robust calibration (TS-2, DF-2) |
| AF-9 | Auto-open report or toast on completion | "Helpful" | Violates the v1.0 focus-safe policy (D-17): no toasts/steals before typing; also a report is not urgent | Click to open (TS-10); no completion toast. Do not add an overrun toast either |

### Recommendation — ETA contract (acceptance criteria for requirements)

1. **ETA endpoint is "text begins inserting".** Decode + finalize are inside the ETA; `typing` is a separate state (`VoicePill` already shows "Typing..."). End-to-end (first-to-last keystroke) is recorded in the ledger as a separate `typing_ms` metric, not folded into the ETA. Without this definition, `--type-delay 2ms` on a 2,000-character transcript silently breaks the promise.
2. **First estimate is published within one frame of the stop transition** (target <100 ms after `write_pid_state(pid, "transcribing")`), before `load_model()`.
3. **Display is monotone non-increasing under normal conditions**; upward corrections are allowed only when the observed rate proves the estimate wrong, at most once per 2 s, and are recorded as `eta_increased=true` for report analysis.
4. **Overrun state machine:** `counting → floor(1s) → grace(3s) → indeterminate(…)` until done. Entering `indeterminate` sets `overrun=true`; leaving it without completion only happens on abort.
5. **No negative, no zero, no fractions, no ranges, no percent** anywhere in the pill.
6. **ETA never appears during `recording` or `starting`.**

---

## 2. Confidence and calibration UX

### Table Stakes

| ID | Feature | Why Expected | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| TS-12 | **Silent calibration** | The user is dictating, not tuning software; any calibration prompt is friction at the worst moment | LOW | Predictor + ledger | Calibration is a side effect of normal use. No first-run wizard, no "rate this estimate" |
| TS-13 | **Cold start always yields a number** | New machine / new model must not regress to the old static label | LOW-MEDIUM | Prior table by model class (tiny→large) × device class (CPU int8 / CUDA fp16) | Priors are seeds, not truth. Ship them in code with a comment; the first 3 runs replace them per config. Label the run `estimate_source=prior` |
| TS-14 | **Config-keyed lookup with global fallback** | `--model medium.en --device cuda --compute-type float16` must not borrow `small.en` CPU int8 statistics | MEDIUM | `args.model/device/compute_type/beam_size/vad_filter/language`; `actual_backend()` | Key = normalized config fingerprint. Missing key → global median → prior. Never key on hardware serials or hostnames |
| TS-15 | **Outlier-robust statistics** | First run after boot (cold page cache) and model-download runs are 10× slower and will poison a mean | MEDIUM | Ledger flags: `cold_start`, `downloaded_model`, `fallback`, `watchdog` | Median/trimmed mean; explicit exclusion rules; keep the raw rows so the report can show what was excluded and why |
| TS-16 | **Reset/disable controls** | Users change GPUs, drivers, thermal paste; stale calibration must be recoverable | LOW | New CLI verbs | `voice --reset-calibration [--config KEY]`, `VOICE_ETA=off` (display only), `VOICE_METRICS=off` (no ledger) |

### Differentiators

| ID | Feature | Value Proposition | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| DF-7 | **Convergence view** (error vs number of runs, per config) | Proves the cold-start story instead of asserting it; shows whether 5 or 50 runs are needed | MEDIUM | Report + ledger + `estimate_source` | Simple SVG line; no JS needed |
| DF-8 | **Drift downweighting** | Model/driver/thermal changes silently invalidate old data; auto-recovery beats manual reset | MEDIUM | Ledger timestamps + config fingerprint | If median abs % error of the last 10 runs exceeds a threshold, downweight older samples for that key (do not delete them). Report marks the invalidation event |
| DF-9 | **Optional benchmark seeding** (`voice --calibrate`) | Cuts cold-start error from run 1 | MEDIUM | `--doctor` harness; a short bundled or synthesized sample | **Optional/deferred.** Decoding a tone is not representative of speech; a bundled spoken sample adds licensing/size questions. Only pursue if cold-start error proves painful in real use |

### Anti-Features

| ID | Anti-Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|---|
| AF-10 | Manual fudge-factor slider / `VOICE_ETA_MULTIPLIER` as the primary UX | Easy to implement, "user knows best" | Users will tune it once, forget, and then distrust all numbers; hides real regressions; support burden | Automatic robust calibration (DF-2) + reset (TS-16) |
| AF-11 | Confidence labels in the pill ("±", "low confidence") | Transparency | Unreadable in a 2-word-wide pill; user asked for one number | Provenance in ledger/report (DF-3, DF-5) |
| AF-12 | First-run calibration wizard | Perceived accuracy | Blocks the first dictation, the exact moment of maximum impatience | Silent prior + convergence (TS-12, TS-13) |
| AF-13 | Shared/global calibration across machines or users | "Everybody benefits" | Hardware-specific by definition; importing it makes other machines *less* accurate; conflicts with the privacy stance | Per-machine ledger, per-config key, CSV for manual research only |

---

## 3. Telemetry and report UX

### Table Stakes

| ID | Feature | Why Expected | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| TS-17 | **Per-run ledger with predicted vs actual, stages, audio/voiced seconds, chunk & segment counts, char counts — no text** | This is the milestone's foundation; without it there is no calibration, report, or outlier lab | MEDIUM | Instrumentation seams: `toggle_background_recording` (start), `run_background_recording` (stop/load/decode/typing), `transcribe()` (`info.duration_after_vad`, `segment.end`), `insert_text()` | Count **both** segment meanings explicitly: `chunk_count` (180 s audio files) and `whisper_segment_count` (decode segments), plus `failed_chunk_count`. Store `chars_recognized` and `chars_inserted` |
| TS-18 | **Durable storage outside `/run`, ISO-8601 local timestamps with numeric offset, schema version** | Existing logs live in `$XDG_RUNTIME_DIR/voice-stt` (`voice.py:46-50`) and vanish on reboot — unacceptable for history. User explicitly wants local time with numeric offset | LOW | New `XDG_STATE_HOME/voicemode/` tree; existing `STATE_DIR` stays for runtime only | e.g. `2026-10-25T21:14:03+02:00`. Never a naive local timestamp; never UTC-only. Durations from `time.monotonic()`, not wall clock (NTP jumps) |
| TS-19 | **Historical predicted-vs-actual chart** | The core question "is the ETA any good?" | MEDIUM | Ledger | Two series over run time; annotate config changes (model/device) because they explain jumps |
| TS-20 | **Error % over time** | Shows drift and convergence; supports calibration decisions | LOW-MEDIUM | Ledger | Signed error is more diagnostic than absolute; show both |
| TS-21 | **Segment/chunk scatter** (audio seconds vs decode ms or real-time factor) | Reveals the real cost curve, chunk-edge effects, and long-segment outliers | MEDIUM | Per-chunk ledger records | User explicitly asked for "segment scatter"; clarify at requirements time whether x-axis is audio seconds and whether points are chunks or Whisper segments. Recommend **chunks** as points, colored by config, with a fitted line |
| TS-22 | **CSV export** | Analysis outside the tool; sharing with a developer without sharing audio | LOW | Ledger | `voice --export-csv [path]`, one row per run (and a `--per-chunk` variant). Numbers only |
| TS-23 | **Offline, self-contained report opened by CLI and pill click** | Must work on a machine with no network and no running server; no CDN, no build step | MEDIUM | New `voice --report`; `xdg-open`; click handler (TS-10) | Generate on demand: static HTML with inline CSS + **inline SVG charts**, no JavaScript, no external assets. Regeneration is cheap at this data volume; avoids a stale-cache problem |
| TS-24 | **Retention/size cap + data deletion** | Long-lived app, unbounded history is a liability | LOW | Ledger | Cap (e.g. 20k runs / 50 MB) with oldest-first prune; `voice --forget-metrics` with confirmation |
| TS-25 | **Report states the privacy contract and schema** | Users cannot verify "no transcript stored" otherwise | LOW | Report template | One visible line: what is stored, where, how to delete; link to `docs/`; show `schema_version` |

### Differentiators

| ID | Feature | Value Proposition | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| DF-10 | **Per-config calibration table** (runs, median abs %, p90, current RTF, last seen) | Turns the report into a calibration instrument, not a vanity chart | MEDIUM | Ledger + predictor | Sortable static table; no JS — sort by pre-computed order or accept fixed order |
| DF-11 | **Run table with filters and links to outliers** | Answers "which run was that 90 s one?" | MEDIUM | Ledger + outlier records | Filters can be query-string-driven on the static page if desired; otherwise group by day/config |
| DF-12 | **Error histogram + p50/p90** | One glance at whether the ETA is usable | LOW-MEDIUM | Ledger | SVG bars |
| DF-13 | **Reproducibility metadata in exports** (`schema_version`, app version, generator timestamp) | Makes CSVs from different releases comparable | LOW | Ledger header | |
| DF-14 | **`--metrics --json` summary** | Enables scripting and future integrations without scraping HTML | LOW | `--json` convention already exists | Same data as `--doctor` predictor block |

### Anti-Features

| ID | Anti-Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|---|
| AF-14 | Live dashboard daemon / Prometheus / Grafana integration | "Observability" | A dictation tool has one user and a few runs per day; a daemon adds a new lifecycle, port, and failure mode | Static on-demand report (TS-23) |
| AF-15 | Auto-refresh while the report is open | Feels current | Requires a server or polling; fights the static-file model; burns battery for no decision | Regenerate on open |
| AF-16 | Storing full argv / command lines | Easiest way to capture config | Leaks `--save-dir` paths, input device names, custom model paths (possibly containing a username) | Allowlisted config fields only (TS-30). Never store argv |
| AF-17 | Storing transcript text or word sequences "for quality analysis" | Tempting for WER metrics | Direct violation of the user's privacy requirement and the README's offline guarantee | Char counts only; audio only in opt-in outlier capture |
| AF-18 | Cloud sync / share links / "upload report" | Convenient bug reports | Breaks the local-only promise; a report is a behavioral fingerprint (when/how long you dictate) | CSV/manual file sharing by the user |

---

## 4. Outlier capture / lab

### Table Stakes

| ID | Feature | Why Expected | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| TS-26 | **Opt-in only, default off, visibly reported** | Audio capture is the highest-risk feature in this milestone | LOW | New config/env flag; `--doctor` line | `VOICE_CAPTURE_OUTLIERS=1` (or `voice --capture-outliers on`). Must be obvious in `--doctor` and the report footer. Off means *no copies and no retention* |
| TS-27 | **Bounded storage and automatic expiry** | A "lab" that fills the disk is a bug | LOW-MEDIUM | New outlier dir under `XDG_STATE_HOME` | Per-file cap (reject > `chunk_seconds`), retention days (e.g. 7), total cap (e.g. 500 MB), oldest-first purge |
| TS-28 | **Never captures text; captures audio only, plus numeric evidence** | The text is the sensitive output; audio is already transient in v1.0 | LOW | Existing WAV lifecycle (`should_delete`, unlink in `voice.py:1818-1824`) | Copy **before** the unlink; capture only the failing chunk, not the whole session, unless the whole session is one chunk |
| TS-29 | **List and purge commands** | Users must be able to see and remove what was captured | LOW | New CLI verbs | `voice --outliers list` and `voice --outliers clean [--all]`; show size and age |

### Differentiators

| ID | Feature | Value Proposition | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| DF-15 | **Automatic outlier detection** from ETA residual + absolute thresholds | Finds the runs worth investigating without the user watching | MEDIUM | Ledger + predictor | e.g. `actual > max(3 × predicted, predicted + 20 s)` or `RTF > 3 × config median`. Also flag `watchdog`/`fallback` runs. Never auto-capture without opt-in (TS-26) |
| DF-16 | **Replay harness** (`voice --replay-outlier <id>`) | Separates "this audio is pathological" from "the machine was busy" — the actual debugging question | MEDIUM-HIGH | Captured WAV; `transcribe()`; model loading | Re-decode with current config and record timings in the outlier record. Explicitly re-runs inference on stored audio; document privacy implications |
| DF-17 | **Outlier record links timing evidence** (predicted, actual, stage breakdown, config key, ETA at each correction) | Makes an outlier explainable, not just a file on disk | LOW-MEDIUM | Ledger | This is what turns "slow sometimes" into a fixable issue |

### Anti-Features

| ID | Anti-Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|---|
| AF-19 | Always-on rolling audio buffer ("shadowplay for STT") | Guarantees you catch the outlier | Continuous microphone retention is a surveillance-grade privacy risk and constant disk churn; contradicts the README guarantee | Threshold-triggered, opt-in capture (TS-26/27) |
| AF-20 | Automatic upload of outliers / crash reports | Easiest debugging for the maintainer | Breaks local-only; audio can contain anything | Local lab + manual export |
| AF-21 | Capturing a transcript snippet "for context" | Speeds triage | Text is the thing the user explicitly excluded; also biases analysis | Metadata only (chars, segment count, config) |
| AF-22 | Unbounded corpus growth / "keep forever" | Simplicity | Disk bloat and privacy exposure grow silently | Caps + expiry (TS-27) |

> Note: v1.0 already retains WAVs on failure/timeout for recovery (`report_stt_failure` logs the path; watchdog path skips unlink). The outlier feature must reuse and *bound* that behavior, not add a second parallel retention mechanism. Treat the existing retained-WAV behavior as in-scope for the privacy documentation.

---

## 5. Privacy controls

### Table Stakes

| ID | Feature | Why Expected | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| TS-30 | **No text, no audio by default; allowlist-only fields** | Explicit user requirement and existing README privacy guarantee | MEDIUM | New ledger module; sanitize model identifier | Store `model_basename` + a short hash for custom local paths, never the full path. Do not store `input_device` strings (may contain a person's name), hostname, username, or cwd |
| TS-31 | **Zero network code in the metrics path** | The product's core promise is offline | LOW | Code review + test asserting no network imports in the module | Enforce with a test that greps/imports-audits the metrics module |
| TS-32 | **Kill switch** (`VOICE_METRICS=off`) | Some users want no local history at all | LOW | Config parsing conventions (`env_bool`) | Off = no file writes; UI falls back to static text; predictor uses priors only |
| TS-33 | **Documented schema + deletion path** | Necessary for trust and for contributors | LOW | `docs/`; README privacy section | `voice --metrics-schema` prints fields and rationale |

### Differentiators

| ID | Feature | Value Proposition | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| DF-18 | **Self-describing schema command** | Lets a skeptical user audit exactly what is collected, with reasons, before enabling anything | LOW | Ledger field registry | Single registry object = schema, docs, and CSV header generated from one source |
| DF-19 | **Redaction levels on export** | Share useful numbers without hardware identifiers | LOW-MEDIUM | CSV export | `--export-csv --redact` drops CPU model / precise device string; default export includes them with a printed warning |

### Anti-Features

| ID | Anti-Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|---|
| AF-23 | Anonymous usage analytics / "phone home" | Product improvement | Violates the explicit offline/local-only stance; a dictation timing profile is behavioral data | Local ledger the user can choose to share |
| AF-24 | Hashed user IDs ("anonymous") | Counting unique users | Still a persistent identifier; unnecessary for a single-user tool | No IDs at all; per-run UUID only for joining start/end events |
| AF-25 | IP, geolocation, hostname, username, home paths | Easier support | Unnecessary and identifying; home paths are already a known leak via model paths | Basenames + hashes; aggregate only |

---

## 6. Future TTS estimation (readiness, not implementation)

Do **not** build TTS ETA in this milestone. Build the seams so it is additive.

### Table Stakes (for this milestone)

| ID | Feature | Why Expected | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| TS-34 | **Generic ledger `kind` + ordered `stages[]` + backend/chars fields** | Prevents a schema migration and a second storage path when TTS arrives | LOW | Ledger schema | `kind` is `stt` or `tts`; `stages: [{name, started_at, duration_ms}]`; plus `tts_backend`, `chars`, `speed`, `voice` (voice ID is not text) |
| TS-35 | **Predictor keyed by stage type, not by "transcription"** | TTS has different stages (synth vs playback) and different drivers (chars/sec vs audio seconds) | LOW-MEDIUM | Predictor design | A `StageEstimator` per stage kind. STT: `load + decode`. TTS later: `synth(chars) + playback(audio_duration)` |
| TS-36 | **Pill labels/state mapping are data-driven, not literal "Transcribing..."** | Today `displayText` hardcodes strings (`VoicePill.qml:50-60`); adding TTS should not require rewriting the switch | LOW | `Voice.qml` `overallState`; `VoicePill.qml` | Show `stage`/`eta` from the progress contract; keep the existing state names as fallback |

### Differentiators (when TTS is built)

| ID | Feature | Value Proposition | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|---|
| DF-20 | **Playback ETA from real audio duration** | Exact, not estimated: the WAV/MP3 exists before playback; `soundfile` is already a dependency | LOW (when built) | `play_tts_audio()`; audio file metadata | Needs elapsed-playback tracking; today `ffplay` is spawned without progress parsing (`voice.py:1319+`) |
| DF-21 | **Synthesis ETA from chars/sec per voice/speed/lang** | Kokoro synthesis is single-shot (`kokoro.create(text)`, `voice.py:1274-1303`), so rate is nearly linear in chars | MEDIUM (when built) | TTS ledger data | Mid-run correction requires chunking text into sentences first — a real change, not a UI tweak |

### Anti-Features

| ID | Anti-Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|---|
| AF-26 | Building TTS ETA now | "Symmetry" | No TTS timing data yet; forces speculative schema and UI work; distracts from the STT milestone | Seams only (TS-34/35/36) |
| AF-27 | Modeling synth + playback as one stage | Simpler code | Synthesis is CPU-bound and bursty; playback is wall-clock; blending them makes both estimates wrong and hides which one is slow | Separate stages from day one (schema level) |

---

## 7. Status-bar integration contract (cross-cutting)

This is where the feature can fail for reasons unrelated to math. The v1.0 pill and service live **outside this repository** (`~/.config/quickshell/ii/...`), so the repo must ship both a machine contract and a documented widget patch.

| Concern | Decision | Complexity | Depends on (existing) | Notes |
|---|---|---|---|---|
| Progress channel | **Atomic `progress.json` in the runtime dir**, written via temp file + `os.replace` | LOW-MEDIUM | `STATE_DIR` (`voice.py:46`); `Voice.qml` poll loop (`:159-259`) | Keep the PID file format unchanged (`pid state`) for backward compatibility; add a second `FileView`. QML must tolerate missing/partial files (it already does for PID) |
| Polling cost | Reuse the existing 100 ms active poll; idle drops to 2.5 s (`Voice.qml:253-259`) | LOW | `Voice.qml` | No extra timer; no 10 Hz redraw of text (AF-3) |
| State precedence | `recording`/`starting` must beat `transcribing` when both files exist | LOW | `overallState` (`Voice.qml:23-30`) | Document the precedence table; test with stale files |
| Label width | Reserve width; whole-second quantized text | LOW | `implicitWidth` (`VoicePill.qml:65-67`) | Otherwise the bar shifts every second |
| Click behavior | Report only; no toggle on click | LOW | `inertMouseArea` (`:104-112`) | Accidental recording toggles from a bar click would be a regression. (A separate click-to-toggle may be a future option, never in this milestone) |
| Portability | Ship a Quickshell snippet + `--status --json` contract; document non-Quickshell fallback | MEDIUM | Docs; `--json` | Without this, "ETA in the bar" only works on the author's dotfiles, contradicting the portability requirement |
| Process end | Final ledger record written **before** `remove_pid()` | LOW | `finally` block (`voice.py:1853-1865`) | Otherwise the last (and most interesting) run is lost; also guarantees the report includes the run the user just clicked on |

---

## Feature Dependencies

```
Instrumentation seams (new)
    ├──requires──> TS-17 ledger records
    │                   ├──requires──> DF-2 calibration ──requires──> TS-14 config key
    │                   │                        └──enhances──> TS-1 immediate ETA
    │                   ├──requires──> TS-19/20/21/22 report
    │                   ├──requires──> DF-15 outlier detection ──requires──> TS-26..29 capture
    │                   └──requires──> DF-7 convergence / DF-8 drift
    └──requires──> TS-2 stage decomposition
                        └──requires──> TS-1 immediate estimate (must publish before load_model)

DF-1 mid-run correction ──requires──> transcribe() streams segments (refactor of voice.py:646-680)
DF-1 ──enhances──> TS-4 cross-chunk countdown
DF-1 ──requires──> info.duration_after_vad (fallback info.duration)

TS-23 report HTML ──requires──> TS-18 durable ledger path
TS-10 pill click ──requires──> TS-23 report generation + xdg-open
TS-7 distinct transcribing ──enhances──> TS-3 ETA text (non-color cue)
TS-36 data-driven labels ──requires──> progress.json + VoicePill switch refactor

TS-6 fallback re-estimate ──conflicts with──> DF-2 calibration if fallback runs are not excluded
AF-19 always-on audio buffer ──conflicts with──> TS-30 no-audio-by-default
AF-9 auto-open report ──conflicts with──> v1.0 focus-safe notification policy (D-17)
```

### Dependency notes

- **TS-17 requires instrumentation, not just a new writer.** The useful numbers already exist but are thrown away: `Recorder.stop_to_wav()` returns duration, `Wave`/`wave` gives exact per-chunk audio seconds, `faster-whisper` returns `info.duration_after_vad` and per-segment `.end`, and `transcripts` gives char counts before insertion. The work is threading these through `run_background_recording()` (`voice.py:1709-1865`) without changing behavior.
- **TS-1 and TS-2 conflict unless ordering is explicit.** The predictor must publish a prior-based total *before* `load_model()` (`voice.py:1783`) so the user sees a number immediately; the measured load time then refines the estimate. Do not wait for load completion to publish.
- **DF-1 is the only change to the inference hot path.** It requires replacing the generator-consuming one-liner in `transcribe()` with an explicit loop (and mirroring it in the CPU-fallback branch). This is the highest-risk refactor in the milestone: it must preserve `initial_prompt` chaining (`last_success_text[-200:]`), per-chunk error handling, and deletion semantics. Tests should cover both the happy path and fallback.
- **TS-18 conflicts with the existing log location.** `LOG_FILE` lives in `$XDG_RUNTIME_DIR` and is wiped at reboot. Metrics must not. Keep logs where they are; add a separate persistent tree.
- **TS-10 depends on a new CLI verb, not on QML knowing paths.** Putting `XDG_STATE_HOME` logic in QML duplicates configuration and breaks for users with non-default env. Have the pill call `voice --report`.
- **TS-6 and DF-2 interact.** A GPU→CPU fallback run must not be attributed to the GPU config's calibration, or the next GPU run is predicted 20× too slow. Likewise, model-download runs must not count as normal cold starts.
- **DF-15 depends on TS-26 being off by default.** Detection can run always; capture cannot.

---

## MVP Definition

### Ship in v1.1 (core)

The milestone is not "show an ETA"; it is "prove the ETA is honest". A version without the ledger and report cannot do that.

- [ ] **TS-17, TS-18, TS-30, TS-31, TS-32, TS-33** — durable, privacy-safe ledger with the full stage vocabulary
- [ ] **TS-2, TS-1, TS-3, TS-4, TS-5, TS-7, TS-8, TS-9** — stage-aware estimate, immediate display, sane formatting, overrun handling
- [ ] **DF-1** — mid-run correction from segment timestamps (explicitly in scope)
- [ ] **TS-12, TS-13, TS-14, TS-15, DF-2, DF-3** — silent per-config calibration with cold-start priors
- [ ] **TS-19, TS-20, TS-22, TS-23, TS-24, TS-25, DF-12** — report with the two headline charts, CSV, deletion, privacy note
- [ ] **TS-10, TS-11, TS-36** — click-through, CLI parity, data-driven labels
- [ ] **DF-15, TS-26..TS-29** — detection + opt-in bounded capture (in scope; can be the last phase)

### Add after core validation (v1.1.x)

- [ ] **TS-21, DF-10, DF-11** — scatter and per-config tables once there is enough real data to look at
- [ ] **TS-6** — fallback-aware correction (rare on the author's CPU-only setup; important for CUDA users)
- [ ] **DF-4, DF-5, DF-7, DF-8, DF-13, DF-14, DF-18, DF-19** — warm start, doctor accuracy block, convergence/drift, export metadata, schema command
- [ ] **DF-16, DF-17** — replay lab and evidence links

### Future (v2+)

- [ ] **TS-34/35/36 already ship; DF-20/DF-21** — TTS synthesis + playback ETA with separate stages
- [ ] **DF-9** — benchmark seeding, only if cold-start error is measured to matter

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---|---|---|---|
| TS-1 immediate number | HIGH | LOW | P1 |
| TS-2 stage-aware total | HIGH | MEDIUM | P1 |
| TS-3 format/floor rules | HIGH | LOW | P1 |
| TS-5 overrun handling | HIGH | LOW | P1 |
| TS-7 distinct transcribing | HIGH | LOW | P1 |
| TS-17 ledger | HIGH (enabler) | MEDIUM | P1 |
| TS-18 durable storage + timestamps | HIGH | LOW | P1 |
| DF-1 mid-run correction | HIGH | MEDIUM | P1 |
| DF-2 per-config calibration | HIGH | MEDIUM-HIGH | P1 |
| TS-12/13/14/15 calibration prerequisites | HIGH | LOW-MEDIUM | P1 |
| TS-23/19/22 report + CSV | HIGH | MEDIUM | P1 |
| TS-30/31/32 privacy baseline | HIGH | MEDIUM | P1 |
| TS-10 click-through | MEDIUM | LOW-MEDIUM | P1 |
| TS-11 CLI status parity | MEDIUM | LOW | P1 |
| DF-15/TS-26..29 outlier lab | MEDIUM | MEDIUM | P2 |
| TS-20/21 error chart + scatter | MEDIUM | MEDIUM | P2 |
| DF-3 provenance | MEDIUM | LOW | P2 |
| DF-4 warm start | MEDIUM | LOW-MEDIUM | P2 |
| DF-5 doctor accuracy | MEDIUM | LOW-MEDIUM | P2 |
| TS-6 fallback correction | MEDIUM (CUDA users) | MEDIUM | P2 |
| DF-16 replay | LOW-MEDIUM | MEDIUM-HIGH | P3 |
| DF-9 benchmark seeding | LOW | MEDIUM | P3 |
| TTS ETA (DF-20/21) | future | MEDIUM | P3 (next milestone) |

---

## Competitor / archetype analysis

Patterns rather than product-specific claims (confidence LOW; no live product testing was performed, and the merged websearch provider is classified LOW unless cross-checked).

| Feature | File-transcription GUIs (Buzz/MacWhisper class) | CLI inference tools (whisper.cpp, yt-dlp, ffmpeg class) | This project's approach |
|---|---|---|---|
| Progress model | Determinate per-file queue; total work known up front | Streaming rate/ETA lines, often with speed multiplier; unknown totals degrade to elapsed counters | Determinate by audio seconds, but stage-aware (load + decode + finalize) |
| ETA visibility | Percent or "processing file 2/5"; not time-to-completion in the UI chrome | ETA printed to a terminal, frequently corrected; ETA is verbose, not glanceable | Single glanceable second count in a bar pill; details only in the report |
| Overrun behavior | Bar stalls at 99 % (the classic failure) | ETA recalculates upward without explanation | Floor → grace → indeterminate, with the overrun recorded for analysis |
| Mid-run correction | Usually none per file | Common (rolling rate) | Per Whisper segment; honest about the ~30 s correction cadence |
| Calibration | None; one fixed estimate | None; user reads the rate | Per-config, silent, robust, with provenance |
| Privacy | Varies; some upload | Local | Local-only ledger, no text/audio by default, opt-in bounded capture |
| Click-through | N/A | N/A | Pill click → static offline HTML report |

Takeaway: the differentiator is not "having an ETA" — terminal tools have had that for decades. It is **showing one trustworthy number in a 2-word-wide bar, and being able to prove afterwards how wrong it was**. The ledger + report is what makes the number defensible, and it is the part most likely to be under-scoped.

---

## Open questions for requirements definition

1. **"Segment" is overloaded.** The milestone says "segment counts" and "mid-run correction after each segment". Confirm: `chunk` = 180 s WAV file (current `Recorder` chunking), `whisper_segment` = decoder output segment. The ledger should store both and the UI should never expose either.
2. **ETA endpoint.** Confirm "until text begins inserting" (recommended) vs "until the last character is typed". The latter makes typing a first-class ETA stage and changes the pill copy.
3. **Report location and format.** `XDG_STATE_HOME/voicemode/report.html` regenerated on demand (recommended) vs `XDG_DATA_HOME`. Confirm no JS/offline requirement, or whether interactive filtering is worth the complexity.
4. **Quickshell ownership.** The pill/service live in the user's dotfiles, not this repo. Decide whether v1.1 ships a patch/snippet + contract only (recommended) or vendors a standalone widget.
5. **Outlier capture default.** Confirm audio (not text) is acceptable as the captured artifact, and confirm retention defaults.
6. **Cold-start seeding.** Is a `--calibrate` benchmark acceptable if it requires a bundled speech sample, or is prior-only acceptable for the first runs?

---

## Sources

**Codebase (HIGH confidence, read directly):**
- `voice.py:46-50` — runtime `STATE_DIR`, PID/log file locations (ephemeral `/run`)
- `voice.py:150-337` — `Recorder`, chunking, `stop_to_wav()` duration/paths
- `voice.py:631-680` — `load_model()`, `transcribe()`, GPU→CPU fallback, generator consumption
- `voice.py:799-821` — PID state file format and writers (`starting`/`recording`/`transcribing`/`typing`)
- `voice.py:895-912` — chunk seconds, STT timeout
- `voice.py:1490-1544` — TTS background lifecycle (synth then playback, single-shot)
- `voice.py:1661-1865` — toggle + background recording state machine and instrumentation seams
- `voice.py:1274-1303` — Kokoro single-shot synthesis
- `voice.py:1991-1999` — `print_status()` ignores state
- `~/.config/quickshell/ii/services/Voice.qml:23-30, 54-96, 141-259` — state precedence, FileView polling, duration recovery
- `~/.config/quickshell/ii/modules/ii/bar/VoicePill.qml:31-67, 104-112, 140-164` — state→text/color mapping, inert mouse area, pulse
- `.planning/PROJECT.md`, `README.md`, `issue.md` — privacy guarantee, CLI surface, existing progress gap
- Verified in `.venv`: `faster_whisper.TranscriptionInfo` exposes `duration` and `duration_after_vad`; `Segment` exposes `.start`/`.end`/`.text`; `transcribe()` returns `(Iterable[Segment], TranscriptionInfo)` and supports `log_progress` (HIGH confidence)

**UX research (MEDIUM confidence — cross-checked; the `websearch` provider classifies unverified results LOW, MEDIUM when verified):**
- Nielsen Norman Group, "Progress Indicators Make a Slow System Less Insufferable" (2014) — static indicators are the worst option; determinate feedback for ≥10 s; allow extra time; changes in speed are noticed; never let the indicator stall. https://www.nngroup.com/articles/progress-indicators/
- UX Tigers, "Progress Indicators Ease the Wait" (2026) — determinate feedback above 10 s, with the caveat that the bar must not stall, lie, or reset. https://www.uxtigers.com/post/progress-indicators
- Stack Overflow, "Smart progress bar ETA computation" — EWMA/smoothing of observed rate; naive remaining = (n−prog) × rate is embarrassingly jumpy near the end. https://stackoverflow.com/questions/933242/smart-progress-bar-eta-computation
- Nielsen Norman Group, "Response Times: The 3 Important Limits" — feedback thresholds (0.1 s / 1 s / 10 s) that justify showing a number at all for a ~2 s dictation.
- telemetry-kit privacy docs and TelemetryDeck privacy FAQ — data minimization, no PII, local-first, retention limits: the pattern the local ledger follows (without any network component). https://docs.telemetry-kit.dev/privacy-compliance

**Not used / gaps:** No live usability testing; no measurements of actual RTF on this machine for each model/device combination (the predictor must measure, not assume); competitor UI behavior characterized by archetype rather than hands-on review.

---

*Feature research for: voicemode v1.1 Latency Prediction & Telemetry*
*Researched: 2026-10-25*
