# Roadmap: voicemode (Arch Linux / Hyprland)

## Overview

v1.0 delivered working push-to-talk dictation and text-to-speech. v1.1 makes transcription latency legible and falsifiable: a single-number ETA in the Quickshell pill, honest prediction-vs-actual telemetry, an offline accuracy report, and a calibration loop that stays portable across CPU and CUDA hardware and model configurations.

## Milestones

- ✅ **v1.0 Initial Release** — Phases 1-5 (shipped 2026-09-19)
- 🚧 **v1.1 Latency Prediction & Telemetry** — Phases 6-10 (in progress)

## Phases

<details>
<summary>✅ v1.0 Initial Release (Phases 1-5) — SHIPPED 2026-09-19</summary>

- [x] Phase 1: Environment & Audio Subsystem (2/2 plans) — completed 2026-09-18
- [x] Phase 2: Wayland Keystroke Injection (2/2 plans) — completed 2026-09-19
- [x] Phase 3: Text-to-Speech & Model Asset Pipeline (2/2 plans) — completed 2026-09-19
- [x] Phase 4: Hyprland Integration & Daemon Lifecycle (2/2 plans) — completed 2026-09-19
- [x] Phase 5: End-to-End System Verification (2/2 plans) — completed 2026-09-19

</details>

### 🚧 v1.1 Latency Prediction & Telemetry (In Progress)

**Milestone Goal:** Show a trustworthy single-number ETA during transcription, and record prediction-vs-actual telemetry so the estimator improves over time and stays portable across CPU/CUDA hardware and model configurations.

- [x] **Phase 6: Foundations, Ledger & Status Contract** - Freeze the schema and status contract, fix lifecycle races, and instrument honest stage timings.
- [x] **Phase 7: ETA Engine & Calibration** - Turn measured runs into an immediate, robust, mid-run-corrected single-number estimate. — completed 2026-10-29
- [ ] **Phase 8: Accuracy Report & Click-Through** - Prove the ETA's honesty with offline terminal, CSV, and HTML reports.
- [ ] **Phase 9: Quickshell ETA Integration** - Replace "Transcribing..." with a glanceable countdown and a click that opens the report.
- [ ] **Phase 10: Accuracy Loop, Portability & Hardening** - Close the improvement loop, capture outliers only on opt-in, and verify the matrix.

## Phase Details

### Phase 6: Foundations, Ledger & Status Contract

**Goal**: The worker records honest, privacy-safe timing data and publishes a trustworthy status snapshot, while non-transcription commands stay fast and lifecycle races stop producing fiction.
**Depends on**: Nothing (first phase of v1.1; builds on the shipped v1.0 lifecycle)
**Requirements**: FND-01, FND-02, FND-03, FND-04, FND-05, LED-01, LED-02, LED-03, LED-04, LED-05, LED-06, LED-07, DEC-01, DEC-02, DEC-03, DEC-04, STS-01, STS-02, STS-03, STS-04, STS-05
**Success Criteria** (what must be TRUE):

  1. Non-transcription commands (`--status`, `--report`, `--toggle`, `--cancel`, `--doctor`) work without loading numpy, sounddevice, or faster-whisper, and `voice --status` completes in under 100 ms warm.
  2. Two rapid toggle presses during cold start leave exactly one worker running and the PID state file is never observed torn, and every abnormal exit ends in a terminal outcome instead of a stale "transcribing" state; only the existing PID state vocabulary is published.
  3. After every run — success, cancel, error, watchdog timeout, or GPU→CPU fallback — exactly one schema-v1 ledger row exists with predicted and actual timings, stage timings whose decode spans full generator consumption, per-segment decoder evidence, config/backend/host fingerprint, outcome, prediction metadata, and reserved TTS fields with no TTS data written, while `status.json` is removed.
  4. `status.json` is published atomically at every transition and within 100 ms of entering transcribing, using monotonic durations and epoch cross-process timestamps; deleting it never changes the bar's state because the PID file remains the authority, and stale snapshots expire.
  5. The ledger records character counts only and contains no transcript text, prompts, hotwords, clipboard content, hostnames, usernames, or paths; directories are `0700` and files `0600`; `VOICE_METRICS=off` stops all telemetry writes.

**Plans:** 7/7 plans complete
Plans:

- [x] 06-07-PLAN.md

**Wave 1**

- [x] 06-01-PLAN.md — Tracer: one run → one ledger row + status publish/remove end-to-end, telemetry seam, import-light CLI

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 06-02-PLAN.md — Freeze ledger schema v1: allowlisted builder, privacy tests, TTS-reserved fields, rotation, docs
- [x] 06-03-PLAN.md — Close duplicate-worker race and torn PID reads: flock around toggle, atomic PID writes, ownership gate

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 06-04-PLAN.md — Publish status contract v1: atomic status.json at every transition, 5 s heartbeat, prior ETA, expiry

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 06-05-PLAN.md — Honest timing: timed transcription seam, per-chunk evidence, early model load, incremental decoding

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 06-06-PLAN.md — Every exit truthful: shared finalize authority, watchdog row, abandoned-run reconciliation

### Phase 7: ETA Engine & Calibration

**Goal**: A calibrated, honest ETA: one number appears immediately, counts down smoothly, corrects mid-run, and never lies when it expires.
**Depends on**: Phase 6
**Requirements**: ETA-01, ETA-02, ETA-03, ETA-04, ETA-05, ETA-06, ETA-07, ETA-08, ETA-09
**Success Criteria** (what must be TRUE):

  1. A single integer ETA appears within 100 ms of entering transcribing on a fresh install — before model load — using shipped priors and prefixed with `~` when uncalibrated.
  2. The ETA counts down at a steady integer cadence, is monotone non-increasing except for marked upward revisions at most once per 2 s, stays hidden while starting/recording, and never shows a negative, zero, fractional, or ranged value.
  3. On overrun the display clamps at 1 s and then reads `Finishing…`; the overrun is recorded in the ledger rather than hidden.
  4. After 20 runs on this machine, the ETA's median absolute error against "text begins inserting" is at or below 20%, while failed, fallback, cold, contended, and outlier runs are excluded from fitting but kept in the ledger.
  5. `--status --json` exposes state, phase, ETA, source, and confidence; `--reset-calibration` returns the estimator to prior-based numbers; `VOICE_ETA=off` hides the ETA without affecting transcription.

**Plans:** 4/4 plans complete

Plans:

- [x] 07-04-PLAN.md

**Wave 1**

- [x] 07-01-PLAN.md — Estimator Core (Formula, Priors, Keying)

**Wave 2** *(blocked on Wave 1)*

- [x] 07-02-PLAN.md — Mid-Run Correction & Display Rules

**Wave 3** *(blocked on Wave 1,2)*

- [x] 07-03-PLAN.md — Calibration, CLI Flags, Status Exposure

### Phase 8: Accuracy Report & Click-Through

**Goal**: An offline, self-contained accuracy report that the user can open on demand and that proves how honest the ETA was.
**Depends on**: Phase 7
**Requirements**: RPT-01, RPT-02, RPT-03, RPT-04, RPT-05, RPT-06
**Success Criteria** (what must be TRUE):

  1. `voice --report` produces a terminal summary plus CSV and HTML output, with since/last/path/open filters, and never imports Whisper.
  2. The HTML report shows predicted vs actual, error over time, stage breakdown, and a residual histogram using inline SVG, with no JavaScript, no external assets, and no network requests.
  3. A fresh install shows an explicit empty state, and every report carries a privacy footer naming the schema, what is stored, where it lives, how to delete it, and the clipboard caveat.
  4. A pre-rendered `report.html` for the last 200 runs is regenerated atomically after each run so the click is instant; `--metrics --json` and CSV export use stable headers.
  5. If `xdg-open` is missing or fails, the user gets a notification plus the printed report path; the opened path is validated under the state directory.

**Plans**: TBD

### Phase 9: Quickshell ETA Integration

**Goal**: The Quickshell pill shows a truthful, glanceable ETA during transcription and opens the accuracy report on click.
**Depends on**: Phase 8
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05
**Success Criteria** (what must be TRUE):

  1. During transcription the pill shows a single-number ETA in place of `"Transcribing..."`, visually distinct from recording by both palette role and glyph, and legible in light, dark, and grayscale.
  2. The number counts down at 1 Hz from the worker-provided epoch without spawning a process, without synchronous 10 Hz reads, and without shifting the bar's layout on each tick.
  3. Unknown, malformed, or stale status renders a busy state — never idle and never a frozen number — while recording still shows no ETA.
  4. A click during transcribing/typing/wrap-up opens the local report; a click during recording is inert; a missing report or unavailable opener degrades to a notification or printed path.
  5. The live QML change is committed in the dotfiles repo and a matching vendored reference exists under `integrations/quickshell/`, with docs naming the live copy as authoritative.

**Plans**: TBD
**UI hint**: yes

### Phase 10: Accuracy Loop, Portability & Hardening

**Goal**: The estimator keeps improving without collecting unconsented data, and its behavior is honest across hardware, users, and failure modes.
**Depends on**: Phase 9
**Requirements**: ACC-01, ACC-02, ACC-03, ACC-04, ACC-05, ACC-06, ACC-07
**Success Criteria** (what must be TRUE):

  1. The report shows convergence/drift and a per-config calibration table, and `--doctor` reports sample count, median absolute error, p90, last calibration, ledger/status health, and resolved paths.
  2. Outliers are always detected and visible in the report; corpus capture is off by default and, when explicitly enabled, stores only bounded, permission-restricted audio outside the timed path with free-space checks and no network.
  3. CPU int8 is verified; CUDA is detected and recorded but never enabled; AMD and Intel GPUs stay on CPU; calibration keys use the resolved backend; hardware probes never hang or pollute the ledger.
  4. The dictation → ETA → report loop survives UID ≠ 1000, unset `XDG_RUNTIME_DIR`, 44.1 kHz multi-chunk audio, cold boot, 4 GB RAM, a read-only state directory, and a full disk without breaking transcription.
  5. `docs/telemetry.md` and the README document schema, privacy, opt-in capture, environment variables, and deletion; TTS-reserved fields are present with no TTS priors mixed in; the evaluation protocol (median absolute error, p90, signed bias, overrun share, stratified) is recorded before collection.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 6 → 7 → 8 → 9 → 10

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Environment & Audio Subsystem | v1.0 | 2/2 | Complete | 2026-09-18 |
| 2. Wayland Keystroke Injection | v1.0 | 2/2 | Complete | 2026-09-19 |
| 3. Text-to-Speech & Model Asset Pipeline | v1.0 | 2/2 | Complete | 2026-09-19 |
| 4. Hyprland Integration & Daemon Lifecycle | v1.0 | 2/2 | Complete | 2026-09-19 |
| 5. End-to-End System Verification | v1.0 | 2/2 | Complete | 2026-09-19 |
| 6. Foundations, Ledger & Status Contract | v1.1 | 7/7 | Complete    | 2026-10-29 |
| 7. ETA Engine & Calibration | v1.1 | 4/4 | Complete    | 2026-10-29 |
| 8. Accuracy Report & Click-Through | v1.1 | 0/0 | Not started | - |
| 9. Quickshell ETA Integration | v1.1 | 0/0 | Not started | - |
| 10. Accuracy Loop, Portability & Hardening | v1.1 | 0/0 | Not started | - |
