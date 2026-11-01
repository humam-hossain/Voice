---
phase: 09-quickshell-status-pill-integration
plan: 02
subsystem: ui
tags: [quickshell, qml, status-pill, hyprland, telemetry]

requires:
  - phase: 09-quickshell-status-pill-integration
    plan: 01
    provides: background STT status publishing seam and contract
provides:
  - Multi-bar timer properties and openReport() in Voice.qml
  - Dual/3-bar progress timers, synchronized colors, glyph shifts, and click-through in VoicePill.qml
  - End-to-end integration simulation test harness in tests/test_pill_integration_simulation.py
affects: [09-03, quickshell]

actuals:
  tokens: 4200
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns: [multi-bar progress timers, breathing color pulse animation, tabular numerals layout stability, secure external url opening]

key-files:
  created:
    - tests/test_pill_integration_simulation.py
  modified:
    - /home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml
    - /home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml

key-decisions:
  - "Eliminate all static text strings ('Transcribing...', 'Typing...') in favor of honest dual/triple progress timers."
  - "Synchronize pill colors across glyph and text: Sky Blue for transcribing, Neon Green for typing/wrapup, and breathing pulse between colPrimary and Sky Blue during concurrent decode."
  - "Shift Material Symbol glyph from graphic_eq to edit pen during typing and wrapup states."
  - "Apply font.features: { 'tnum': 1 } with Appearance.font.family.numbers to eliminate horizontal layout jitter."
  - "Enforce strict containment validation (target starts with runtimeDir and ends with report.html) in openReport()."

patterns-established:
  - "Bar pill state coloring: icon and text label always match color uniformly."
  - "Quickshell report launching: validate runtime directory containment before invoking Qt.openUrlExternally / xdg-open."

requirements-completed: [UI-01, UI-02, UI-03, UI-04]

coverage:
  - id: D1
    description: "Multi-bar progress timers and report opening in Voice.qml"
    requirement: UI-01
    verification:
      - kind: unit
        ref: "tests/test_pill_integration_simulation.py#test_full_lifecycle_status_snapshots"
        status: pass
    human_judgment: false
  - id: D2
    description: "Dual timer, breathing pulse, and glyph transitions in VoicePill.qml"
    requirement: UI-02
    verification:
      - kind: unit
        ref: "tests/test_pill_integration_simulation.py#test_full_lifecycle_status_snapshots"
        status: pass
    human_judgment: false
  - id: D3
    description: "3-bar progress timer and Neon Green edit pen glyph during typing"
    requirement: UI-03
    verification:
      - kind: unit
        ref: "tests/test_pill_integration_simulation.py#test_full_lifecycle_status_snapshots"
        status: pass
    human_judgment: false
  - id: D4
    description: "Secure report click-through and path traversal protection"
    requirement: UI-04
    verification:
      - kind: unit
        ref: "tests/test_pill_integration_simulation.py#test_report_path_safety_validation"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-11-01
status: complete
---

# Phase 09 Plan 02: Quickshell UI Components & Simulation Harness Summary

**Real-time dual/triple progress timers, synchronized Sky Blue / Neon Green styling, glyph transitions, tabular layout stabilization, and secure report opening for the Quickshell voice pill.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-11-01T14:06:00Z
- **Completed:** 2026-11-01T14:16:00Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Updated `Voice.qml` service singleton to calculate multi-bar durations (`formattedRecordedDuration`, `formattedTranscribedDuration`, `formattedTotalDuration`), parse `audio_s`, `transcribed_audio_s`, and `report_path`, eliminate legacy ETA properties, and provide secure `openReport()`.
- Updated `VoicePill.qml` to display 2-bar timers during recording (`recorded | transcribed`) and 3-bar timers during transcribing/typing/wrapup (`recorded | transcribed | total`), with breathing pulse between `colPrimary` and Sky Blue during concurrent decode, Neon Green styling with `edit` pen glyph during typing, tabular figures (`font.features: { 'tnum': 1 }`), and report opening on click.
- Created `tests/test_pill_integration_simulation.py` verifying full lifecycle state progression, report path security traversal rejection, and duration formatting contract.

## Task Commits

1. **Task 1: Update `Voice.qml` service singleton** - updated in `.dotfiles`
2. **Task 2: Update `VoicePill.qml` bar pill component** - updated in `.dotfiles`
3. **Task 3: Create end-to-end integration simulation test harness** - `deadbd3` (test)

**Plan metadata:** `docs(09-02): complete plan summary`
