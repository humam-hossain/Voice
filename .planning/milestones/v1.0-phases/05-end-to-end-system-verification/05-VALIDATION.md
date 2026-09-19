---
phase: "05"
slug: "end-to-end-system-verification"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-19"
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python `unittest` (Standard Library) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m unittest tests/test_verification_doctor.py` |
| **Full suite command** | `.venv/bin/python -m unittest discover tests` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m unittest tests/test_verification_doctor.py`
- **After every plan wave:** Run `.venv/bin/python -m unittest discover tests`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 0 | VERIF-01, VERIF-02 | T-05-01 | Wave 0 test harness for doctor and verification suite | unit | `.venv/bin/python -m unittest tests/test_verification_doctor.py` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | VERIF-01, VERIF-02 | T-05-02 | Static system diagnostics (`voice --doctor`) with remediation hints | unit/integration | `.venv/bin/python -m unittest tests/test_verification_doctor.py -k TestDoctor` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | VERIF-01, VERIF-02 | T-05-03 | 3-tier verification engine (`voice --verify` & `scripts/verify-e2e.sh`) | unit/integration | `.venv/bin/python -m unittest tests/test_verification_doctor.py -k TestVerification` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | VERIF-01, VERIF-02 | — | Arch Linux + Hyprland documentation overhaul (`README.md`, `docs/ARCH_HYPRLAND.md`, `docs/DEPENDENCIES.md`) | doc/lint | `.venv/bin/python -m unittest discover tests` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_verification_doctor.py` — test suite covering `voice --doctor` checks and `voice --verify` multi-tier pipeline
- [ ] `scripts/verify-e2e.sh` — standalone verification launcher script

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Push-to-talk live speech dictation across Kitty/Foot and Neovim/VS Code | VERIF-01 | Requires human speech input and live focused Wayland application windows | Run `voice --verify --tier 3` or press `SUPER + SHIFT + M`, speak a test sentence, verify text appears at cursor |
| Primary selection reading across Firefox/Chromium and document viewers | VERIF-02 | Requires highlighted text in GUI browser/viewer and physical audio playback listening | Highlight text in browser, press `SUPER + T`, verify speech audio plays through speakers/headphones; press `SUPER + T` again to verify playback stop |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending 2026-09-19
