---
phase: 07-eta-engine-and-calibration
plan: 01
subsystem: telemetry
tags: [telemetry, eta, calibration, ratio-of-sums, shrinkage, status-contract]

# Dependency graph
requires:
  - 06-foundations-ledger-status-contract
provides:
  - "Decoupled 4-tier hierarchy key extraction (L0 -> L1 -> L2 -> L3) in voicemode_telemetry.py"
  - "Ratio-of-sums rate calculation avoiding micro-recording arithmetic mean bias"
  - "James-Stein shrinkage blending with sample threshold n >= 3 and linear weight min(1.0, n/10.0)"
  - "Dynamic model load subtraction reducing load_s by elapsed_record_s"
  - "Extended status schema contract with revision_count, last_revised_at, key_level, key_n"
  - "Hermetic unit tests in tests/test_eta_engine.py verifying ETA-01, ETA-02, ETA-08"
affects: [07-02, 07-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [ratio-of-sums rate resolution, multi-tier fallback hierarchy, James-Stein shrinkage, dynamic load subtraction]

key-files:
  created:
    - tests/test_eta_engine.py
  modified:
    - voicemode_telemetry.py

key-decisions:
  - "Rate statistic is strictly ratio of sums sum(decode_s)/sum(audio_s) rather than arithmetic mean of ratios"
  - "Shrinkage uses linear weight min(1.0, n/10.0) blending narrow tier with broader tier when n >= 3"
  - "Prediction horizon terminates at start of text insertion (insert_s) with dynamic load subtraction"
  - "Extended status keys (revision_count, last_revised_at, key_level, key_n) validated without schema rejection"

patterns-established:
  - "Accumulator updates maintain sum_decode_s, sum_audio_s, n, load_s across L0..L2"
  - "Outlier rates outside [0.01, 10.0] are rejected and fall back to broader hierarchy tiers"

requirements-completed: [ETA-01, ETA-02, ETA-08]

coverage:
  - deliverable: "Ratio-of-sums transcription rate calculation"
    verification:
      kind: pytest
      ref: tests/test_eta_engine.py#test_ratio_of_sums_formula
      status: pass
    human_judgment: false
  - deliverable: "4-tier key hierarchy extraction and shrinkage resolution"
    verification:
      kind: pytest
      ref: tests/test_eta_engine.py#TestKeyHierarchy
      status: pass
    human_judgment: false
  - deliverable: "Dynamic model load subtraction and text insertion horizon"
    verification:
      kind: pytest
      ref: tests/test_eta_engine.py#TestTimingEndpoints
      status: pass
    human_judgment: false
  - deliverable: "Extended status schema contract validation"
    verification:
      kind: pytest
      ref: tests/test_eta_engine.py#test_status_contract_extension
      status: pass
    human_judgment: false

# Metrics
duration: 10 min
completed: 2026-10-29
status: complete
---

# Phase 07 Plan 01: ETA Engine Core & Calibration Summary

Delivered the decoupled, tracer-led ETA estimation core in `voicemode_telemetry.py` implementing ratio-of-sums rate calculation, 4-tier key hierarchy (L0 -> L1 -> L2 -> L3), James-Stein shrinkage blending, dynamic model load subtraction, and status schema extensions.

## Accomplishments

1. **Tracer Pipeline & Ratio-of-Sums**: Built end-to-end latency rate resolution using ratio-of-sums `sum(decode_s) / sum(audio_s)` rather than arithmetic mean of rates, preventing micro-recording bias.
2. **4-Tier Key Hierarchy & Shrinkage**: Implemented L0 (8 fields), L1 (6 fields), L2 (4 fields), L3 (prior model family) hierarchy with sample floor `n >= 3` and James-Stein shrinkage weighting `min(1.0, n/10.0)` blending narrow keys with broader parent keys.
3. **Dynamic Load Subtraction & Text Insertion Horizon**: Integrated dynamic model load deduction (`max(0.0, load_s - elapsed_record_s)`) terminating at the text insertion start endpoint (`insert_s = 0.2s`).
4. **Status Schema Extension**: Extended `STATUS_V1_KEYS` to validate `revision_count`, `last_revised_at`, `key_level`, and `key_n`.
5. **Unit Test Suite**: Created hermetic unit tests in `tests/test_eta_engine.py` covering all timing endpoints, ratio of sums, hierarchy tiers, shrinkage, and out-of-bounds rejection.

## Verification Results

- `pytest tests/test_eta_engine.py -v`: 10 passed
- `pytest tests/test_status_contract.py -v`: 9 passed
- `pytest tests/test_telemetry.py -k TestTracerContract -v`: 2 passed
- Full regression suite: 170 passed, 19 subtests passed

## Self-Check: PASSED
