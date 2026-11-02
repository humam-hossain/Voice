---
phase: 10-accuracy-loop-portability-hardening
plan: 02
subsystem: reporting-diagnostics
tags: [outliers, drift, hardware-probe, doctor, latency-scatter]

requires:
  - phase: 10-accuracy-loop-portability-hardening
    provides: always-on outlier classification and degraded durability

provides:
  - Latency report outlier filtering (voice --report --outliers)
  - Drift percentage calculation comparing recent 20 runs against lifetime baseline
  - Stratified duration latency views (short <5s, medium 5-30s, long >30s)
  - SVG charts with Crimson (#f43f5e) diamond markers for outlier runs
  - Guarded hardware probing inspecting CPU vector extensions (AVX2/AVX-512) and discrete GPUs (<1.0s timeout, zero model loading)
  - Enforced CPU int8 default execution
  - Comprehensive voice --doctor telemetry card, hardware card, and path permission / storage audits (0700/0600, >1GB disk space)
  - Structured nested JSON keys ("telemetry", "hardware", "paths") on voice --doctor --json

affects:
  - 10-03-PLAN.md
  - docs/telemetry.md
  - README.md

actuals:
  tokens: 14200
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - Guarded hardware probing without loading AI inference runtimes
    - Crimson (#f43f5e) diamond SVG polygon marker highlighting for statistical outliers
    - Zero-import overhead discipline on reporting CLI dispatch paths

key-files:
  created: []
  modified:
    - voicemode_report.py
    - voice.py
    - voicemode_telemetry.py
    - tests/test_report.py
    - tests/test_verification_doctor.py

key-decisions:
  - "GPU hardware (CUDA, ROCm) detected during doctor or hardware probing is reported purely informatively; CPU int8 execution remains strictly enforced"
  - "Doctor exit codes distinguish advisory warnings (mic muted, path permission advisories, low disk space, telemetry defects -> exit 0) from fatal STT breaks (missing wtype, missing mic -> exit 1)"
  - "Outliers are rendered as hollow Crimson (#f43f5e) diamonds in latency scatter and RTF trend plots with full metadata tooltips"

patterns-established:
  - "Guarded hardware probe: inspect /proc/cpuinfo flags, use ctranslate2 device count and 1.0s timed out nvidia-smi query without model instantiation"
  - "Advisory vs fatal exit codes in diagnostic tooling"

requirements-completed:
  - ACC-02
  - ACC-03
  - ACC-07

coverage:
  - id: D4
    description: "Latency report outlier filtering, drift tracking, stratified duration views, and SVG Crimson markers"
    requirement: ACC-02
    verification:
      - kind: unit
        ref: "tests/test_report.py#TestReportOutliersAndDrift"
        status: pass
    human_judgment: false
  - id: D5
    description: "Guarded hardware backend probing (AVX2/AVX-512, CUDA, ROCm) with enforced CPU int8 default"
    requirement: ACC-03
    verification:
      - kind: unit
        ref: "tests/test_verification_doctor.py#TestHardwareBackendProbe"
        status: pass
    human_judgment: false
  - id: D6
    description: "voice --doctor telemetry card, hardware card, path audits (0700/0600), and JSON contract"
    requirement: ACC-07
    verification:
      - kind: unit
        ref: "tests/test_verification_doctor.py#TestDoctorTelemetryAndPaths"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-11-02
status: complete
---

# Phase 10: Accuracy Loop, Portability & Hardening — Plan 02 Summary

**Outlier reporting and drift visualization, guarded hardware backend probing, and comprehensive telemetry/hardware diagnostics in `voice --doctor`**

## Performance

- **Duration:** 20 min
- **Started:** 2026-11-02T11:40:00Z
- **Completed:** 2026-11-02T12:01:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

1. **Outliers, Drift Tracking & Stratified Latency Views (`voicemode_report.py`):**
   - Added `--outliers` CLI filter to restrict latency report strictly to outlier runs.
   - Calculated `drift_pct` comparing the median wait latency of recent 20 runs against lifetime baseline.
   - Added duration stratification buckets: Short (<5s), Medium (5-30s), Long (>30s) with run counts, median wait, and median RTF.
   - Styled outlier points on SVG latency scatter and RTF trend plots as Crimson (`#f43f5e`) hollow diamond markers (`<polygon>` elements) with `.chart-outlier` class and detailed tooltips.
   - Added "Outlier Runs" hero filter card in HTML report and `[OUTLIER]` tag in terminal summaries with corpus WAV presence check (`[audio: wav]` vs `[audio: pruned]`).

2. **Guarded Hardware Backend Probing (`voice.py:probe_hardware_backend`):**
   - Implemented non-invasive CPU vector extension inspection via `/proc/cpuinfo` for AVX2 and AVX-512 without spawning external processes.
   - Safely probed CUDA devices via `ctranslate2.get_cuda_device_count()` with a 1.0s timeout on `nvidia-smi` without loading Whisper models.
   - Checked `/dev/kfd` (ROCm) and `/dev/dri` (Intel/Mesa GPU).
   - Strictly enforced `default_backend: "cpu, int8"`, maintaining discrete GPUs as informative-only detections.

3. **Expanded Doctor Diagnostics (`voice.py:run_doctor`):**
   - Added Path & Permissions Audit checking runtime dir (0700), state dir (0700), corpus dir (0700), ledger file (0600), and filesystem free space (> 1 GB).
   - Added dedicated Hardware Backend card (CPU architecture, vector extensions, discrete GPUs, default backend).
   - Added dedicated Telemetry Diagnostics card (run count, median wait latency, p90 latency, mean RTF, outlier count/rate, drift %, last run timestamp, or onboarding prompt on 0 runs).
   - Emitted structured JSON contract on `voice --doctor --json` containing `"telemetry"`, `"hardware"`, and `"paths"` nested keys.
   - Enforced exit code semantics: advisory warnings (muted mic, low disk space, telemetry defects) exit with code 0; fatal STT breaks exit with code 1.

## Verification

- Automated test suites passing:
  - `uv run pytest tests/test_report.py -k test_outliers -x` -> 5 passed
  - `uv run pytest tests/test_verification_doctor.py -k test_hardware -x` -> 4 passed
  - `uv run pytest tests/test_report.py tests/test_verification_doctor.py -x` -> 96 passed (100%)
- CLI command invocations verified:
  - `voice --doctor --json` returns structured JSON with all expected keys.
  - `voice --doctor` prints clean 8-card human-readable report.
  - `voice --report --outliers` filters exclusively to outlier runs.
