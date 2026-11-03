---
phase: "11"
slug: "voice-desktop-pop-up-ui"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-03"
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/test_config.py tests/test_pill_integration_simulation.py -x` |
| **Full suite command** | `uv run pytest -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_config.py tests/test_pill_integration_simulation.py -x`
- **After every plan wave:** Run `uv run pytest -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | POP-02 | T-11-01 | Secure atomic config save (0600 file, 0700 dir) and merge precedence (CLI > env > config > default) | unit | `uv run pytest tests/test_config.py -x` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | POP-01 | T-11-02 | Action button string array execution (`Quickshell.execDetached`) and live timer binding | unit / sim | `uv run pytest tests/test_pill_integration_simulation.py -k test_popup_components -x` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 2 | POP-01 | T-11-03 | Hover intent (1000ms delay) with hover suppression during active recording | sim | `uv run pytest tests/test_pill_integration_simulation.py -k test_hover_gating -x` | ❌ W0 | ⬜ pending |
| 11-02-02 | 02 | 2 | POP-02 | T-11-04 | Parity across live dotfiles and repo integrations; full regression green | regression | `uv run pytest -x` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_config.py` — unit tests for `load_user_config()`, `save_user_config()`, and config merge hierarchy
- [ ] `tests/test_pill_integration_simulation.py` — AST & simulation tests covering `VoicePopup.qml` and `VoicePill.qml`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Quickshell visual rendering and interactive click/hover on Hyprland bar | POP-01, POP-02 | Visual rendering in active Wayland compositor | Hover over voice pill for 1000ms; verify popup appears with Material You styling. Click Start; verify recording toggles and hover-suppression prevents spurious re-open. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
