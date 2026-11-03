# Phase 11: Voice Desktop Pop-up UI - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-02
**Phase:** 11-Voice Desktop Pop-up UI
**Areas discussed:** Trigger & Invocation, Content & Telemetry Scope, Interactive Controls & Settings, Layout & Card Architecture, Config Change Behavior, Start Recording Button, Popup Auto-dismiss, Recent Runs Click Action, Layout Feasibility

---

## Trigger & Invocation — Pill Click vs Popup

| Option | Description | Selected |
|--------|-------------|----------|
| Left-click toggles popup; report opened from inside | Hover stays inert to avoid accidental popups during typing/recording | ✓ (initially) |
| Both left-click and 1000ms hover open popup | Matches CpuGpu/Memory pills; report opened from inside | |
| Hover opens popup, click opens report.html | Split interaction model | |

**User's choice:** Initially selected left-click toggle, then via freeform input revised to hover-based trigger (matching existing StyledPopup pattern). Final: hover with 1000ms intent delay.
**Notes:** User provided extensive freeform vision describing the popup as a hover-triggered configuration inspector with recent runs and action buttons.

---

## Pill Behavior During Recording

| Option | Description | Selected |
|--------|-------------|----------|
| Inert while recording | Clicking during active recording does nothing to avoid mic disruption | ✓ |
| Allow opening popup during recording | Shows live recording duration in popup | |
| Click acts as Stop action | Triggers transcribing phase | |

**User's choice:** Inert during recording (no accidental disruption).

---

## Popup When Recording Starts

| Option | Description | Selected |
|--------|-------------|----------|
| Popup stays open | Shows live state updating in real-time; dismiss manually or on hover-out | ✓ |
| Popup auto-dismisses | Prevents visual distraction during dictation | |

**User's choice:** Popup stays open showing live progress.

---

## Configuration Interactivity

| Option | Description | Selected |
|--------|-------------|----------|
| Read-only display of current values | Inspector only, changes via env vars/CLI | |
| Interactive toggles persisting to config file | Live settings panel, changes persist across sessions | ✓ |
| Session-only interactive changes | Reset on next launch | |

**User's choice:** Persist to config file (`~/.config/voicemode/config.json`).

---

## Config Change Application

| Option | Description | Selected |
|--------|-------------|----------|
| Apply on next recording toggle | Config written immediately; fresh worker reads updated values | ✓ |
| Require explicit restart/reload | Manual action needed | |

**User's choice:** Apply on next toggle (natural due to detached worker subprocess architecture).

---

## Start Recording Button

| Option | Description | Selected |
|--------|-------------|----------|
| Include Start Recording button (green mic) | Invokes `voice --toggle`, clickable alternative to hotkey | ✓ |
| Recording is hotkey-only | Popup only has Stop and Cancel | |

**User's choice:** Include Start Recording button.

---

## Recent Runs Count

| Option | Description | Selected |
|--------|-------------|----------|
| 3-5 recent runs | Compact, guaranteed no-scroll | |
| Up to 10 recent runs | More history but larger popup | ✓ |
| Last run only | Minimal | |

**User's choice:** 10 runs.

---

## Recent Runs Click Action

| Option | Description | Selected |
|--------|-------------|----------|
| Purely informational rows | Duration, chars, RTF, outcome inline; full details in HTML report | ✓ |
| Clicking expands to show per-stage breakdown | Inline load_ms, decode_ms, insert_ms | |

**User's choice:** Informational only.

---

## Layout Feasibility — Scrolling

| Option | Description | Selected |
|--------|-------------|----------|
| Recent runs scrollable, rest fixed | Config and live state never scroll; only runs section scrolls if needed | ✓ |
| Reduce to 5 runs for no-scroll | Guaranteed fit on 1080p | |
| Full popup scrollable | Entire content scrolls | |
| Two-column layout | Config left, runs right; wider but shorter | |

**User's choice:** Recent runs section scrollable, config and live state fixed.
**Notes:** Estimated ~618px height with 10 runs + 12 config rows. Fits on 1080p (~1040px available) but tight.

---

## Color Palette

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 9 palette + dedicated button colors | Sky Blue (STT), Neon Green (typing/start), Crimson (cancel/outliers), colPrimary (recording) | ✓ |
| Material You dynamic tokens only | Adapts to wallpaper but loses STT/typing identity | |
| Mixed approach | Chrome uses M3 tokens, state indicators keep dedicated accents | |

**User's choice:** Phase 9 palette with Start=Neon Green, Cancel=Crimson, Stop=colPrimary.

---

## Popup Chrome Style

| Option | Description | Selected |
|--------|-------------|----------|
| Match existing StyledPopup | Dark surface container, colOnSurface text, subtle borders | ✓ |
| Custom/different style | | |

**User's choice:** Match existing popup style.

---

## The Agent's Discretion

- Exact popup width (likely 320px or wider for config panel)
- Config JSON schema structure and key naming
- Config file merge priority (CLI > env > config file recommended)
- How voice.py discovers and reads the config file
- Recent runs row layout density and font sizing
- Whether action buttons are icon-only or icon+label
- Scrollable area height threshold for recent runs
- How to read metrics.jsonl from QML (helper script, voice --report --json, or direct parsing)

## Deferred Ideas

None — discussion stayed within phase scope.
