---
phase: "09"
slug: "quickshell-status-pill-integration"
status: ready
nyquist_compliant: true
wave_0_complete: false
created: "2026-11-01"
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via uv) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_status_contract.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_status_contract.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | UI-01 | T-09-01 | Privacy-safe duration emission without text | unit | `uv run pytest tests/test_status_contract.py -x` | ✅ | ⬜ pending |
| 09-01-02 | 01 | 1 | UI-01, UI-03 | T-09-02 | Closed schema validation across all transitions | integration | `uv run pytest tests/test_status_contract.py -x` | ✅ | ⬜ pending |
| 09-02-01 | 02 | 2 | UI-01, UI-03, UI-04 | T-09-04 | Validate report_path containment inside runtimeDir | unit | `uv run pytest tests/test_status_contract.py -x` | ✅ | ⬜ pending |
| 09-02-02 | 02 | 2 | UI-01, UI-02, UI-03, UI-04 | T-09-07 | Reset animation opacity to 1.0 on stop | integration | `uv run pytest tests/test_status_contract.py -x` | ✅ | ⬜ pending |
| 09-02-03 | 02 | 2 | UI-01, UI-03, UI-04 | T-09-04 | Validate path traversal rejection on report opener | integration | `uv run pytest tests/test_pill_integration_simulation.py -x` | ❌ W0 | ⬜ pending |
| 09-03-01 | 03 | 3 | UI-05 | T-09-09 | Clean dotfiles repo commit without extraneous files | git | `git -C /home/pera/github_repo/.dotfiles status --porcelain restow/quickshell` | ✅ | ⬜ pending |
| 09-03-02 | 03 | 3 | UI-05 | T-09-08 | Byte-level diff zero between dotfiles and vendored copy | integration | `diff -u /home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml integrations/quickshell/Voice.qml && diff -u /home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml integrations/quickshell/VoicePill.qml && uv run pytest tests/ -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_status_contract.py` — unit tests for tail decode status publishing and typing state schema conformance
- [ ] `tests/test_pill_integration_simulation.py` — state transition simulation harness and report path boundary verification
- [ ] `integrations/quickshell/` — vendored directory for reference copies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dual progress timer & color pulse in Quickshell | UI-01 | Rendered in live Quickshell Wayland bar overlay on Hyprland | Start recording, verify dual progress `0:02 \| 0:00` and breathing color pulse |
| Triple progress timer & solid Sky Blue shift | UI-01, UI-03 | Visual Wayland compositor rendering | Stop recording, verify immediate 3-bar progress `0:06 \| 0:03 \| 0:06` and solid Sky Blue with `graphic_eq` |
| Glyph switch to edit & solid Neon Green shift | UI-02, UI-03 | Visual Wayland compositor rendering | During text insertion, verify glyph switches to `edit` and color to neon green `#4ade80` |
| Click pill to open latency report | UI-04 | Desktop xdg-open/browser launch via Quickshell MouseArea | Click pill during transcribing/typing, verify browser opens `report.html`; click during recording is inert |
| Zero horizontal layout jitter | UI-01, UI-02 | Visual layout stability | Watch bar pill during count up, verify no pixel wobble on adjacent bar widgets |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** verified 2026-11-01
