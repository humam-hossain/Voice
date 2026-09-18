---
phase: 02-wayland-keystroke-injection
plan: "01"
subsystem: input-injection
tags: [wtype, zwp_virtual_keyboard_v1, ydotool, wayland, hyprland, text-normalization, rootless-shortcuts]

requires:
  - phase: 01-environment-audio-subsystem
    provides: Python 3.12 environment, audio capture, and Faster-Whisper pipeline
provides:
  - Rootless Wayland keystroke injection engine with wtype and zwp_virtual_keyboard_v1
  - Transcript normalization (strip and newline-to-space substitution)
  - Upstream wtype -d 0 bug mitigation
  - Pre-typing settling pause and stdin piping (wtype -)
  - Rootless simulated paste shortcuts (Ctrl+V and Ctrl+Shift+V)
  - Automated unit test suite harness in tests/test_wayland_input.py
affects: [02-02, 03-status-audio-visual-feedback]

actuals:
  tokens: 1500
  tasks: 3
  commits: 1

tech-stack:
  added: [wtype]
  patterns: [rootless-wayland-input, stdin-piping, zero-delay-omission, mock-subprocess-testing]

key-files:
  created: [tests/test_wayland_input.py]
  modified: [voice.py]

key-decisions:
  - "Preferred wtype over ydotool in auto mode for rootless unprivileged input"
  - "Omitted -d flag when type_delay is 0 to mitigate upstream wtype abort crash"
  - "Used stdin piping (wtype -) to avoid shell injection and argument length limits"
  - "Implemented simulated paste via wtype modifier sequences (-M ctrl -s 20 -k v -s 20 -m ctrl)"

patterns-established:
  - "normalize_typed_text before typing with keep_newlines flag"
  - "resolve_wayland_backend helper for backend prioritization and fallback"

requirements-completed: [INPUT-01, INPUT-02]

coverage:
  - id: D1
    description: "Transcript normalization helper with newline collapsing and trimming"
    requirement: "INPUT-01"
    verification:
      - kind: unit
        ref: "tests/test_wayland_input.py#TestTextNormalization"
        status: pass
    human_judgment: false
  - id: D2
    description: "Rootless wtype keystroke injection with stdin piping and -d 0 bug mitigation"
    requirement: "INPUT-01"
    verification:
      - kind: unit
        ref: "tests/test_wayland_input.py#TestTypeTextWayland"
        status: pass
    human_judgment: false
  - id: D3
    description: "Rootless paste shortcuts for Ctrl+V and Ctrl+Shift+V via wtype modifier sequences"
    requirement: "INPUT-02"
    verification:
      - kind: unit
        ref: "tests/test_wayland_input.py#TestPasteClipboardWayland"
        status: pass
    human_judgment: false

duration: 3 min
completed: 2026-09-19
status: complete
---

# Phase 02 Plan 01: Wayland Typing Engine & Rootless Shortcut Simulation Summary

**Rootless Wayland keystroke injection via wtype over zwp_virtual_keyboard_v1 with stdin piping, -d 0 mitigation, settling pause, and simulated paste shortcuts**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-19T01:14:50Z
- **Completed:** 2026-09-19T01:17:50Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Implemented `normalize_typed_text()` to strip whitespace and collapse internal newlines to spaces by default, with opt-in `--keep-newlines` support.
- Built `resolve_wayland_backend()` prioritizing rootless `wtype` over `ydotool` in auto mode, eliminating mandatory root-daemon setup under Hyprland.
- Refactored `type_text()` with stdin piping (`wtype -`), 15s timeout protection, upstream `-d 0` bug workaround, 50ms pre-typing settling delay, and automatic fallback to `ydotool`.
- Refactored `paste_clipboard()` to synthesize rootless `Ctrl+V` and `Ctrl+Shift+V` modifier sequences via `wtype`, preceded by a 150ms clipboard offer settling pause.
- Established the automated test suite in `tests/test_wayland_input.py` covering normalization, typing execution, delay bug mitigation, fallback handling, and paste shortcut sequences.

## Task Commits

Each task was committed atomically:

1. **Tasks 02-01-01 through 02-01-03: Core Wayland typing engine, shortcuts, and tests** - `797734c` (feat)

**Plan metadata:** `docs(02-01): complete plan summary`

## Files Created/Modified
- `voice.py` - Core CLI and input injection routines updated with `normalize_typed_text`, `resolve_wayland_backend`, `type_text`, and `paste_clipboard`
- `tests/test_wayland_input.py` - Unit test harness validating normalization, typing backends, delay handling, and paste shortcuts

## Decisions Made
- Prioritized `wtype` over `ydotool` in `"auto"` mode because `wtype` operates entirely in user space via Wayland's `zwp_virtual_keyboard_v1` without root privileges.
- Omitted `-d` entirely when `type_delay <= 0` because `wtype` aborts on `-d 0` with `Invalid sleep time`.
- Enforced 15.0s timeouts on all child process calls to avoid indefinite hangs if the compositor socket stalls.
- Configured 150ms settling pause in `paste_clipboard` to allow Wayland compositor and clients time to process the clipboard offer before sending the paste keystroke.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness
- Ready for Plan 02-02: Dual Clipboard Persistence, CLI Configuration & Verification.

---
*Phase: 02-wayland-keystroke-injection*
*Completed: 2026-09-19*
