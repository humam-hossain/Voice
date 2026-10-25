# Requirements: voicemode (Arch Linux / Hyprland)

**Defined:** 2026-10-26
**Milestone:** v1.1 — Latency Prediction & Telemetry
**Core Value:** Seamless, low-latency push-to-talk speech dictation and text-to-speech on Arch Linux + Hyprland using local models and native Wayland utilities.

## Milestone Goal

Show a trustworthy single-number ETA during transcription, and record prediction-vs-actual telemetry so the estimator improves over time and stays portable across CPU/CUDA hardware and model configurations.

## v1 Requirements

Committed scope for v1.1. Each maps to exactly one roadmap phase (6–10).

### Foundation & Integrity (FND)

- [ ] **FND-01**: Non-transcription commands (`--status`, `--report`, `--toggle`, `--cancel`, `--stop-tts`, `--doctor`) run without importing numpy, sounddevice, or faster-whisper; `voice --status` completes in under 100 ms warm.
- [ ] **FND-02**: The PID state file is written atomically; readers never observe partial content; the existing `pid state` file format is unchanged.
- [ ] **FND-03**: Two rapid toggle presses never spawn two workers (flock around read-decide-spawn; the worker re-verifies the PID file holds its own PID before recording).
- [ ] **FND-04**: Every exit path (success, error, cancel, watchdog) writes a terminal ledger row and clears status/PID; SIGKILL is detected by expiry rather than a cleanup write.
- [ ] **FND-05**: No new PID state strings are introduced; new granularity lives only in `status.json.phase`.

### Telemetry Ledger (LED)

- [ ] **LED-01**: One JSONL record per STT run in `$XDG_STATE_HOME/voicemode/metrics.jsonl`, schema v1, append-only, rotated at ~5 MB.
- [ ] **LED-02**: A record stores predicted-as-shown and actual timing, stage timings (finalize/load/decode/insert), per-segment audio/decode/chars/ok, config, resolved backend, host fingerprint, and outcome/error stage.
- [ ] **LED-03**: Prediction metadata is stored: source (prior/calibrated/mid-run), key level, n, confidence, time shown, and revisions.
- [ ] **LED-04**: No transcript text, prompts, hotwords, paths, argv, hostname, username, or clipboard content is stored; enforced by an allowlist serialization test plus a regex scan.
- [ ] **LED-05**: A `source` discriminator and TTS fields are reserved in schema v1; no TTS data is written yet.
- [ ] **LED-06**: `VOICE_METRICS=off` kill switch; documented deletion procedure; directories `0700` / files `0600`; tests never write to real state or runtime directories.
- [ ] **LED-07**: Character counts only — never words and never text.

### Decode Timing (DEC)

- [ ] **DEC-01**: `decode_ms` covers full generator consumption, not the `model.transcribe()` call.
- [ ] **DEC-02**: Per-segment decoder evidence is recorded (temperature/fallbacks, avg_logprob, compression ratio, no_speech probability, VAD duration) to flag outliers.
- [ ] **DEC-03**: Instrumentation covers both the primary and the GPU→CPU fallback paths.
- [ ] **DEC-04**: Monotonic clocks measure durations, epoch seconds carry cross-process timestamps, and QML never subtracts a Python timestamp from its own clock.

### Status Contract (STS)

- [ ] **STS-01**: The worker writes `status.json` atomically at every transition and after each segment; schema v1, at most ~1 KB.
- [ ] **STS-02**: Fields: `schema`, `pid`, `run_id`, `state` (PID vocabulary), `phase`, `started_at`, `updated_at`, `expires_at`, `audio_s`, `segments`, `segments_done`, `eta_epoch`, `eta_remaining_s`, `eta_confidence`, `eta_source`, `overrun`, `report_path`.
- [ ] **STS-03**: The first ETA is available within 100 ms of entering `transcribing`, before model load.
- [ ] **STS-04**: The PID file remains the authority; `status.json` is advisory; deleting it never changes bar state.
- [ ] **STS-05**: A terminal exit removes `status.json`; `expires_at` prevents stale rendering after a crash.

### Predictor & ETA (ETA)

- [ ] **ETA-01**: Estimate = finalize + load + rate × Σ(audio after VAD) + insert; rate is the ratio of sums, not the mean of ratios.
- [ ] **ETA-02**: Key hierarchy with a minimum of 3 samples per level, falling back to a shipped prior; the chosen level and n are recorded.
- [ ] **ETA-03**: Robust calibration (median/shrinkage, MAD-based confidence) excludes failures, fallbacks, outliers, cold runs, and high-load runs from fitting only — the records themselves are kept.
- [ ] **ETA-04**: Mid-run correction after each segment; the display is monotone non-increasing except for marked upward revisions at most once per 2 s.
- [ ] **ETA-05**: Overrun behavior: 1 s floor → `Finishing…` → indeterminate; never negative, zero, fractional, or a range; overrun is recorded.
- [ ] **ETA-06**: ETA is shown only during transcribing/finalizing and hidden while starting/recording.
- [ ] **ETA-07**: A single number; uncalibrated estimates are prefixed `~`; no ranges.
- [ ] **ETA-08**: The ETA endpoint is "text begins inserting"; typing time is measured separately.
- [ ] **ETA-09**: `--status --json` exposes state/phase/ETA/source/confidence; `--reset-calibration`; `VOICE_ETA=off`.

### Reporting (RPT)

- [ ] **RPT-01**: `--report` produces terminal, CSV, and HTML output, with since/last filters, output path, and open; it never imports Whisper.
- [ ] **RPT-02**: Self-contained HTML with inline SVG and no JS or network: predicted vs actual, error % over time, stage bars, residual histogram.
- [ ] **RPT-03**: Empty state plus a privacy footer (schema, what is stored, path, deletion, clipboard caveat).
- [ ] **RPT-04**: `report.html` (last 200 runs) is regenerated atomically when the ledger changes at worker finish, so the click is instant.
- [ ] **RPT-05**: `--metrics --json` plus CSV export with stable headers.
- [ ] **RPT-06**: `xdg-open` uses argument lists, validates the path under the state directory, and falls back to a notification plus printed path.

### Quickshell Integration (UI)

- [ ] **UI-01**: `VoicePill` shows the ETA instead of `"Transcribing..."`; a single number; distinct from recording via palette role **and** glyph; verified in light, dark, and grayscale.
- [ ] **UI-02**: 1 Hz countdown from `eta_epoch` (QML `real`); no 10 Hz synchronous reads; `watchChanges` plus a fallback poll; no process spawn.
- [ ] **UI-03**: Validity gate (schema/pid/state/expiry); unknown or stale state renders busy, never idle or a frozen number.
- [ ] **UI-04**: Click during transcribing/typing/wrap-up opens the report; inert during recording; the path is validated.
- [ ] **UI-05**: Live QML is committed in `~/.dotfiles`; a vendored reference lives in `integrations/quickshell/`; docs mark the live copy as authoritative.

### Accuracy & Portability (ACC)

- [ ] **ACC-01**: Always-on outlier detection; opt-in bounded corpus capture (default off, caps, retention, free-space check, no network).
- [ ] **ACC-02**: Report convergence/drift views and a per-config calibration table; `--doctor` shows n, median absolute %, p90, and last calibration.
- [ ] **ACC-03**: CPU int8 verified; CUDA is detected and recorded only; AMD/Intel are detected and stay on CPU; the resolved backend is keyed; probes are guarded.
- [ ] **ACC-04**: Durability tests: UID≠1000, unset `XDG_RUNTIME_DIR`, 44.1 kHz multi-chunk, cold boot, 4 GB RAM, read-only state dir, disk full.
- [ ] **ACC-05**: TTS readiness only: reserved fields present, QML branches on `source`, no TTS priors mixed in.
- [ ] **ACC-06**: Evaluation protocol fixed before collecting: median absolute error, p90, signed bias, overrun share, stratified; target ≤20% median absolute error after 20 runs on this machine.
- [ ] **ACC-07**: `docs/telemetry.md` plus README updates; `--doctor` checks ledger/status health and resolved paths.

## v2 Requirements

Deferred to a future release. Tracked but not in the current roadmap.

### TTS Estimation

- **TTS-01**: Predict synthesis duration from character count, engine, and voice.
- **TTS-02**: Predict playback duration and show it in the bar.
- **TTS-03**: Record TTS predicted-vs-actual in the same ledger using the reserved schema fields.

### Estimation Quality

- **EST-01**: Streaming chunk transcription while recording, to shorten perceived latency rather than predict it.
- **EST-02**: Benchmark-driven prior seeding for a new machine.
- **EST-03**: Learned regression model for RTF (only if the dataset and portability case justify it).
- **EST-04**: Per-config scatter plots and richer calibration tables once enough runs exist.

## Out of Scope

Explicitly excluded to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Model pre-warm or resident daemon | Keeps 1.9 GB weights resident; measured peak RSS 2129 MB. Cold load is predicted, not removed. |
| Network telemetry or cloud sync | Privacy baseline: local-only ledger, zero network in the metrics path. |
| Transcript text storage | Privacy: character counts only; text never leaves the active window. |
| New PID state strings | Any unknown alive state falls through `toggle_background_recording` and spawns a second worker; the bar's switch has no default case. |
| Non-Linux support | Project is an Arch Linux + Hyprland utility. |
| Confidence badges, ranges, or progress bars in the pill | Locked decision: one glanceable number; confidence lives in the ledger/report. |
| Auto-opening the report or toasting on completion | Focus stealing before `wtype` typing; the click is explicit. |
| GUI calibration wizard or live dashboard daemon | Contradicts the lean CLI + file-contract architecture. |
| Shared or global calibration across machines | Hardware/config contamination; each machine calibrates itself. |

## Key Decisions

| Decision | Consequence |
|----------|-------------|
| ETA replaces the literal `"Transcribing..."` text | QML must remove the hardcoded string, not add a second label |
| Distinct color **and** glyph from recording | Never color-only; never the error color |
| Click opens the HTML report via `xdg-open` | Report must ship before the clickable pill |
| Single number, no range | No `8–14s`, no percent, no `±` in the pill |
| Character counts only | Allowlist serializer plus a no-text test |
| Cold model load stays | Load time is modeled and predicted |
| `status.json` is advisory; PID file is authority | Deleting `status.json` must never change bar state |
| Live QML is symlinked from `~/.dotfiles` | Bar edits commit in the dotfiles repo; vendored copies in `integrations/quickshell/` |
| Phase numbering continues at 6 | v1.0 ended at Phase 5; v1.1 occupies Phases 6–10 |

## Traceability

Populated during roadmap creation. Each requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FND-01 | TBD | Pending |
| FND-02 | TBD | Pending |
| FND-03 | TBD | Pending |
| FND-04 | TBD | Pending |
| FND-05 | TBD | Pending |
| LED-01 | TBD | Pending |
| LED-02 | TBD | Pending |
| LED-03 | TBD | Pending |
| LED-04 | TBD | Pending |
| LED-05 | TBD | Pending |
| LED-06 | TBD | Pending |
| LED-07 | TBD | Pending |
| DEC-01 | TBD | Pending |
| DEC-02 | TBD | Pending |
| DEC-03 | TBD | Pending |
| DEC-04 | TBD | Pending |
| STS-01 | TBD | Pending |
| STS-02 | TBD | Pending |
| STS-03 | TBD | Pending |
| STS-04 | TBD | Pending |
| STS-05 | TBD | Pending |
| ETA-01 | TBD | Pending |
| ETA-02 | TBD | Pending |
| ETA-03 | TBD | Pending |
| ETA-04 | TBD | Pending |
| ETA-05 | TBD | Pending |
| ETA-06 | TBD | Pending |
| ETA-07 | TBD | Pending |
| ETA-08 | TBD | Pending |
| ETA-09 | TBD | Pending |
| RPT-01 | TBD | Pending |
| RPT-02 | TBD | Pending |
| RPT-03 | TBD | Pending |
| RPT-04 | TBD | Pending |
| RPT-05 | TBD | Pending |
| RPT-06 | TBD | Pending |
| UI-01 | TBD | Pending |
| UI-02 | TBD | Pending |
| UI-03 | TBD | Pending |
| UI-04 | TBD | Pending |
| UI-05 | TBD | Pending |
| ACC-01 | TBD | Pending |
| ACC-02 | TBD | Pending |
| ACC-03 | TBD | Pending |
| ACC-04 | TBD | Pending |
| ACC-05 | TBD | Pending |
| ACC-06 | TBD | Pending |
| ACC-07 | TBD | Pending |

**Coverage:**
- v1 requirements: 48 total
- Mapped to phases: 0
- Unmapped: 48 (to be resolved by roadmap creation)

---

*Requirements defined: 2026-10-26*
*Last updated: 2026-10-26 after milestone v1.1 scope approval*
