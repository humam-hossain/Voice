---
phase: "07"
slug: "eta-engine-and-calibration"
status: complete
nyquist_compliant: true
wave_0_complete: false
created: "2026-10-29"
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `pytest tests/test_telemetry.py tests/test_timing.py tests/test_status_contract.py -q` |
| **Full suite command** | `pytest tests/test_audio_chunking.py tests/test_hyprland_daemon.py tests/test_incremental_transcription.py tests/test_lifecycle_outcomes.py tests/test_pid_race.py tests/test_status_contract.py tests/test_telemetry.py tests/test_timing.py tests/test_verification_doctor.py tests/test_wayland_input.py` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_eta_*.py tests/test_midrun_*.py -q`
- **After every plan wave:** Run `pytest tests/test_telemetry.py tests/test_timing.py tests/test_status_contract.py tests/test_eta_*.py tests/test_midrun_*.py`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | ETA-01 | T-07-01 | Division-by-zero guard, numerical bounds | unit | `pytest tests/test_eta_engine.py::TestETAEngine::test_ratio_of_sums -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | ETA-02 | T-07-02 | 4-level hierarchy fallback & shrinkage | unit | `pytest tests/test_eta_engine.py::TestKeyHierarchy::test_hierarchy_and_shrinkage -x` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 1 | ETA-08 | T-07-03 | Insert start endpoint & load subtraction | unit | `pytest tests/test_eta_engine.py::TestTimingEndpoints::test_insert_endpoint -x` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 2 | ETA-04 | T-07-04 | Downward step immediate, upward hysteresis | integration | `pytest tests/test_midrun_eta.py::TestMidRunRevisions::test_revision_hysteresis -x` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 2 | ETA-05 | T-07-05 | Overrun 1s dwell to Finishing clamp | integration | `pytest tests/test_midrun_eta.py::TestOverrunBehavior::test_dwell_and_finishing -x` | ❌ W0 | ⬜ pending |
| 07-02-03 | 02 | 2 | ETA-06 | T-07-06 | State visibility lifecycle | integration | `pytest tests/test_midrun_eta.py::TestETAVisibility::test_visibility_lifecycle -x` | ❌ W0 | ⬜ pending |
| 07-02-04 | 02 | 2 | ETA-07 | T-07-07 | Single integer & prefix persistence | unit | `pytest tests/test_midrun_eta.py::TestDisplayRules::test_prefix_persistence -x` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 3 | ETA-03 | T-07-08 | Exclusions gating & atomic cache permissions | unit | `pytest tests/test_eta_engine.py::TestCalibrationFilter::test_exclusions_and_confidence -x` | ❌ W0 | ⬜ pending |
| 07-03-02 | 03 | 3 | ETA-09 | T-07-09 | CLI flags, kill-switch & status json | CLI | `pytest tests/test_eta_cli.py::TestETACLI::test_cli_flags_and_kill_switch -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_eta_engine.py` — unit tests covering ETA-01, ETA-02, ETA-03, ETA-08
- [ ] `tests/test_midrun_eta.py` — integration tests covering ETA-04, ETA-05, ETA-06, ETA-07
- [ ] `tests/test_eta_cli.py` — tests covering ETA-09, `--reset-calibration`, `VOICE_ETA=off`, and `.boot_session`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual cadence on desktop display | ETA-07 | Subjective smoothness & desktop UI rendering | Trigger dictation in terminal or Hyprland window and observe countdown output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending 2026-10-29
