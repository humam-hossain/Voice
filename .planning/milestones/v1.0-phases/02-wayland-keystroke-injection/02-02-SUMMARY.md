---
phase: 02-wayland-keystroke-injection
plan: "02"
subsystem: input-injection
tags: [dual-clipboard, wl-copy, notify-send, wayland, hyprland, cli, background-argv]

requires:
  - phase: 02-wayland-keystroke-injection
    provides: wtype Wayland typing engine and rootless shortcut simulation (02-01)
provides:
  - Dual-action clipboard persistence model in insert_text()
  - Desktop failure notification when typing fails with clipboard preservation message
  - Pure Wayland session detection ($WAYLAND_DISPLAY) in notify()
  - CLI arguments (--wayland-backend, --pre-type-delay, --keep-newlines) with delay clamping
  - Detached background daemon worker argument propagation in background_argv()
  - Wayland dependency documentation in docs/DEPENDENCIES.md and README.md
affects: [03-status-audio-visual-feedback]

actuals:
  tokens: 1800
  tasks: 3
  commits: 1

tech-stack:
  added: [wl-clipboard, notify-send]
  patterns: [dual-clipboard-persistence, pure-wayland-notification, worker-argv-serialization]

key-files:
  created: []
  modified: [voice.py, tests/test_wayland_input.py, docs/DEPENDENCIES.md, README.md]

key-decisions:
  - "Unconditionally copy transcripts to system clipboard via wl-copy prior to text injection"
  - "Notify user via notify-send when typing fails, informing them text is preserved in clipboard"
  - "Check WAYLAND_DISPLAY as well as DISPLAY in notify() to support pure Wayland without Xwayland"
  - "Forward all new Wayland flags to background worker processes via background_argv()"

patterns-established:
  - "Dual clipboard buffering: speech is preserved even if target window rejects or drops typing"
  - "Non-negative delay clamping: max(0, delay) for type_delay and pre_type_delay"

requirements-completed: [INPUT-01, INPUT-02]

coverage:
  - id: D1
    description: "Dual-action clipboard persistence and typing failure notifications"
    requirement: "INPUT-01"
    verification:
      - kind: unit
        ref: "tests/test_wayland_input.py#TestInsertTextDualBehavior"
        status: pass
    human_judgment: false
  - id: D2
    description: "CLI argument parsing, environment overrides, and non-negative delay clamping"
    requirement: "INPUT-01"
    verification:
      - kind: unit
        ref: "tests/test_wayland_input.py#TestWaylandCliParsing"
        status: pass
    human_judgment: false
  - id: D3
    description: "Background worker argument serialization in background_argv"
    requirement: "INPUT-01"
    verification:
      - kind: unit
        ref: "tests/test_wayland_input.py#TestBackgroundArgvSerialization"
        status: pass
    human_judgment: false
  - id: D4
    description: "Pure Wayland session notification support"
    requirement: "INPUT-02"
    verification:
      - kind: unit
        ref: "tests/test_wayland_input.py#TestNotifyWayland"
        status: pass
    human_judgment: false

duration: 3 min
completed: 2026-09-19
status: complete
---

# Phase 02 Plan 02: Dual Clipboard Persistence, CLI Configuration & Verification Summary

**Dual-action clipboard persistence, desktop failure alerts, pure Wayland notifications, CLI configuration with daemon serialization, and Wayland dependency documentation**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-19T01:17:50Z
- **Completed:** 2026-09-19T01:20:50Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Refactored `insert_text()` to implement dual-action persistence: speech transcripts are unconditionally buffered into the system clipboard via `wl-copy` immediately upon transcription.
- Added user notification alert via `notify-send` when typing fails or is unsupported, informing the user that the transcript remains safely buffered in the clipboard for immediate manual pasting.
- Extended `notify()` to recognize pure Wayland sessions via `$WAYLAND_DISPLAY`, ensuring alerts display even when Xwayland is not present on Hyprland.
- Implemented CLI arguments `--wayland-backend`, `--pre-type-delay`, and `--keep-newlines`/`--no-keep-newlines` with environment variable fallbacks and non-negative delay clamping.
- Updated `background_argv()` to forward new Wayland flags to detached daemon processes spawned by `--toggle`.
- Updated `docs/DEPENDENCIES.md` and `README.md` to document `wtype` (primary rootless injection) and `wl-clipboard` under Arch Linux and Hyprland.
- Validated the complete 24-test unit test suite and verified end-to-end stdin typing and clipboard persistence on the system.

## Task Commits

Each task was committed atomically:

1. **Tasks 02-02-01 through 02-02-03: Dual clipboard persistence, CLI options, daemon argv forwarding, documentation, and verification** - `0d53beb` (feat)

**Plan metadata:** `docs(02-02): complete plan summary`

## Files Created/Modified
- `voice.py` - Core CLI updated with dual clipboard persistence in `insert_text`, `$WAYLAND_DISPLAY` check in `notify`, argument parsing, and `background_argv` serialization
- `tests/test_wayland_input.py` - Unit test suite expanded with `TestInsertTextDualBehavior`, `TestWaylandCliParsing`, `TestBackgroundArgvSerialization`, and `TestNotifyWayland`
- `docs/DEPENDENCIES.md` - Added Wayland Input & Clipboard Stack documentation
- `README.md` - Updated tested target to Arch Linux/Hyprland and documented Wayland CLI configuration

## Decisions Made
- Implemented dual-action persistence upfront so transcripts are never lost if an application window loses focus, closes, or drops synthetic keystrokes.
- Left transcript in clipboard when `--output-method paste` is selected rather than attempting complex and fragile clipboard restores.
- Forwarded all CLI options to background workers via `background_argv()` to prevent background daemons from silently reverting to default settings.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness
- Phase 2 complete. Ready for phase verification and Phase 3 (Status & Audio-Visual Feedback).

---
*Phase: 02-wayland-keystroke-injection*
*Completed: 2026-09-19*
