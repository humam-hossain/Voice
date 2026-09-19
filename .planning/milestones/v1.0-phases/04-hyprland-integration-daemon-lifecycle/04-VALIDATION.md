---
phase: "04"
slug: "hyprland-integration-daemon-lifecycle"
status: planned
nyquist_compliant: true
wave_0_complete: false
created: "2026-09-19"
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python standard library `unittest` |
| **Config file** | None (standard `unittest` discovery under `tests/`) |
| **Quick run command** | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_hyprland_daemon.py` |
| **Full suite command** | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest discover tests` |
| **Estimated runtime** | ~1.5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_hyprland_daemon.py`
- **After every plan wave:** Run `/home/pera/github_repo/Voice/.venv/bin/python -m unittest discover tests`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 0 | HYPR-01 | — | Unit test harness stubs | unit | `.venv/bin/python -m unittest tests/test_hyprland_daemon.py` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | HYPR-01 | T-04-01, T-04-05 | Lockscreen safety (`locked = false`), Lua block generator, auto-detection | unit | `.venv/bin/python -m unittest tests/test_hyprland_daemon.py -k TestHyprlandKeybindInstallation` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | HYPR-01 | T-04-03, T-04-08 | Dotfiles symlink preservation (`path.resolve()`), full path discovery, dynamic reload | unit | `.venv/bin/python -m unittest discover tests` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 0 | HYPR-02 | — | Daemon lifecycle test stubs | unit | `.venv/bin/python -m unittest tests/test_hyprland_daemon.py` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | HYPR-02 | T-04-02, T-04-06 | Hardened `/proc/<pid>/cmdline` verification, double-tap 300ms race wait, busy state protection | unit | `.venv/bin/python -m unittest tests/test_hyprland_daemon.py -k TestDaemonLifecycleStates` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | HYPR-02 | T-04-04, T-04-07, T-04-09 | 60s transcription watchdog, clean signals (`SIGUSR1` vs `SIGTERM`), symmetric mutex, focus-safe feedback | unit | `.venv/bin/python -m unittest discover tests` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_hyprland_daemon.py` — test harness covering keybinding generation, symlink preservation, PID states, signal differentiation, process inspection, watchdogs, and focus-safe notifications.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Push-to-talk STT hotkey in Hyprland session | HYPR-01, HYPR-02 | Requires active Hyprland compositor receiving input chord from physical keyboard | Press `SUPER + SHIFT + M`, hear 880 Hz start chime, speak phrase, press `SUPER + SHIFT + M`, hear stop chime, verify text types into focused window |
| Speak selection hotkey in Hyprland session | HYPR-01 | Requires active Hyprland compositor and Wayland primary selection | Highlight text in any application, press `SUPER + T`, hear Kokoro audio reading the selected text |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
