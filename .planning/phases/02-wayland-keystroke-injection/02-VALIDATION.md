---
phase: "02"
slug: "wayland-keystroke-injection"
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-09-19"
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python standard library `unittest` with mock subprocess isolation |
| **Config file** | none — self-contained test modules runnable via standard library |
| **Quick run command** | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_wayland_input.py` |
| **Full suite command** | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest discover tests && ~/.local/bin/voicemode --help` |
| **Estimated runtime** | ~1.5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_wayland_input.py`
- **After every plan wave:** Run `/home/pera/github_repo/Voice/.venv/bin/python -m unittest discover tests && ~/.local/bin/voicemode --help`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | INPUT-01 | T-02-01 | Validate stdin text piping and special character safety | unit | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_wayland_input.py -k test_wtype_backend_selection_and_piping` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | INPUT-02 | T-02-02 | Validate key-delay, -d 0 omission, and settling delay | unit | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_wayland_input.py -k test_wtype_delay_and_newline_handling` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | INPUT-01 | T-02-03 | Validate simulated paste shortcuts and rootless fallback | unit | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_wayland_input.py -k test_paste_clipboard_wtype_sequences` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | INPUT-01 | T-02-04 | Validate dual clipboard copy and failure notifications | unit | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_wayland_input.py -k test_insert_text_dual_behavior_and_notification` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | INPUT-01 | — | Validate CLI argument parsing and background forwarding | unit | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_wayland_input.py -k test_cli_argument_forwarding` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_wayland_input.py` — unit test suite for Wayland input injection with mocked binaries (`wtype`, `ydotool`, `wl-copy`, `notify-send`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real window focus typing under Hyprland | INPUT-01, INPUT-02 | Requires live user interaction with focused window | Open terminal or text editor, invoke `voicemode --type-delay 2 "Hello Wayland"`, confirm keystrokes appear without dropped chars. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 2s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** verified 2026-09-19
