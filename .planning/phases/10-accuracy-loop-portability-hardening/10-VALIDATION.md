---
phase: "10"
slug: "accuracy-loop-portability-hardening"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-02"
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.2.0 (`uv run pytest`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/test_telemetry.py tests/test_report.py -x` |
| **Full suite command** | `uv run pytest -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_telemetry.py tests/test_report.py tests/test_durability.py -x`
- **After every plan wave:** Run `uv run pytest -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | ACC-04 | T-10-01 | Secure fallback to /tmp/voice-stt-$UID/ with 0700 perms | unit | `uv run pytest tests/test_durability.py -k test_degraded_durability -x` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 1 | ACC-01 | T-10-02 | Silent outlier tagging, zero focus theft | unit | `uv run pytest tests/test_telemetry.py -k test_outlier -x` | ❌ W0 | ⬜ pending |
| 10-01-03 | 01 | 1 | ACC-01 | T-10-03 | Corpus 0700/0600 perms, FIFO quota, no network | unit | `uv run pytest tests/test_durability.py -k test_corpus -x` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 2 | ACC-02 | T-10-04 | Honest drift/outlier stats, sanitized paths | unit | `uv run pytest tests/test_report.py -k test_outliers -x` | ❌ W0 | ⬜ pending |
| 10-02-02 | 02 | 2 | ACC-03, ACC-07 | T-10-05 | Hardware probe timeout, no Whisper cold-start | unit | `uv run pytest tests/test_verification_doctor.py -k test_hardware -x` | ❌ W0 | ⬜ pending |
| 10-03-01 | 03 | 3 | ACC-05, ACC-06 | T-10-06 | TTS reserved fields non-polluting, stratified latency | unit | `uv run pytest tests/test_telemetry.py -k test_tts_readiness -x` | ❌ W0 | ⬜ pending |
| 10-03-02 | 03 | 3 | ACC-07 | T-10-07 | Documentation sync, zero privacy leaks | integration | `uv run pytest tests/test_durability.py tests/test_telemetry.py tests/test_report.py tests/test_verification_doctor.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_durability.py` — test harness for degraded durability (UID, permissions, ENOSPC in-memory fallback, 44.1kHz resampling, 4GB RAM thread clamp, cold boot) and corpus FIFO management.
- [ ] Stubs and test cases in `tests/test_report.py` for outlier filtering and SVG styling.
- [ ] Stubs and test cases in `tests/test_verification_doctor.py` for hardware probes and doctor JSON keys.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Wayland active window focus during speech dictation with outlier run | ACC-01 | Requires active graphical Wayland compositor session | Trigger dictation into active terminal, simulate high latency decode, verify terminal focus is retained and typing completes without focus loss |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending 2026-11-02
