# Phase 9: Quickshell Status Pill Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-01
**Phase:** 9-quickshell-status-pill-integration
**Areas discussed:** Timer display progression, Glyphs & visual indicators, Layout stability, Click-through latency report, File watching & sync, Pop-up UI deferral

---

## Timer Display Progression

| Option | Description | Selected |
|--------|-------------|----------|
| Countdown ETA numbers (`3s`, `2s`) | Count down predicted remaining seconds | |
| Static text labels | Display `"Transcribing..."`, `"Typing..."`, etc. | |
| Dual & 3-bar progress timers | Dual progress (`0:08 \| 0:05`) while recording; 3-bar progress (`0:10 \| 0:07 \| 0:10`) on stop and during typing; zero text labels | ✓ |

**User's choice:** Dual timer during recording (`recorded_time | transcribed_time`), immediately switching to 3 bars on recording stop (`recorded_time | transcribed_time | total_time`). No `"Transcribing..."`, `"Finalizing..."`, or `"Typing..."` text strings at all.
**Notes:** ETA calculation was completely removed because parallel chunk transcription eliminated the need for post-recording prediction. State progression is shown through pure numbers, glyphs, and colors.

---

## Visual Identity: Glyphs & Color Matching

| Option | Description | Selected |
|--------|-------------|----------|
| Static colors & generic icon | Single icon and theme color across all states | |
| State-matched glyphs & colors | Sky Blue for STT transcribing; Neon Green for typing with `edit` pen glyph; dual pulse during recording+transcribing; uniform color across icon AND text | ✓ |

**User's choice:** Sky Blue for STT transcribing, Neon Green for typing/writing, and `edit` (pen) glyph during text insertion. Both the glyph and the text MUST share the exact same state color.
**Notes:** During concurrent recording and chunk decode, the pill alternates/pulses between the recording color (`colPrimary`) and Sky Blue. When recording stops, it switches purely to Sky Blue. When typing begins, it switches to Neon Green and the `edit` glyph.

---

## Layout Stability & Sizing

| Option | Description | Selected |
|--------|-------------|----------|
| Unconstrained text | Bar width changes fluidly as timer strings grow | |
| Tabular figures & stable sizing | Use monospaced/tabular figures (`tnum`) and stable layout bounds to prevent horizontal bar jitter | ✓ |

**User's choice:** Prevent horizontal bar jitter and layout jump as numbers tick and bars appear.

---

## Click-Through Latency Report

| Option | Description | Selected |
|--------|-------------|----------|
| Inert pill | Clicking does nothing in all states | |
| Click to open latency report | Clicking during transcribing, typing, or wrap-up opens `report.html`; inert during recording; pointer cursor on hover | ✓ |

**User's choice:** Clicking during processing opens the local HTML latency report.

---

## Text Output Method

| Option | Description | Selected |
|--------|-------------|----------|
| Sequential wtype keystroke typing | Simulates keystrokes with delay | |
| Instant clipboard paste | Copies to Wayland clipboard and injects Ctrl+V | ✓ |

**User's choice:** Recommend/prefer instant paste to avoid typing delays while retaining the visual typing indicator during injection.

---

## the agent's Discretion

- Exact hex/rgba shade tuning for Sky Blue and Neon Green tokens.
- Specific fallback mechanism when opening `report.html` if the default browser fails (e.g. desktop notification).
- Wrap-up linger duration (1.5s) before returning to idle.

---

## Deferred Ideas

- **Phase 11: Voice Desktop Pop-up UI**: Dedicated interactive Quickshell overlay popup window for voice recording history, settings, and telemetry. Deferred to a dedicated phase for comprehensive design and implementation.
