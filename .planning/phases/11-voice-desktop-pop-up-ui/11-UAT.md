---
status: testing
phase: 11-voice-desktop-pop-up-ui
source:
  - 11-01-SUMMARY.md
  - 11-02-SUMMARY.md
started: 2026-11-03T03:51:00Z
updated: 2026-11-03T07:27:00Z
---

## Current Test

number: 3
name: Live Telemetry Characters, Recent Dictations Table (Date+AM/PM) & Single-Icon Report Button
expected: |
  Inside the VoicePopup overlay:
  1. Live Telemetry:
     - "Characters" row starts at "0" during active recording, updates live with recognized character count as incremental chunks decode, stays accurate through typing, and displays the finalized count when idle.
     - Never displays stale character counts from previous recordings during an active session.
  2. Recent Dictations Table:
     - Formatted as a structured table with dedicated column headers: `Time`, `Audio`, `Chars`, `RTF`, and `Status`.
     - `Time`: Local date + 12-hour AM/PM format for each run (e.g. `Nov 3, 2:35 PM`).
     - `Audio`: Accurate audio duration (e.g. `17.2s` or `0.0s`).
     - `Chars`: Formatted recognized character count (e.g. `809`, `61`, or `0`).
     - `RTF`: Calculated real-time factor (e.g. `0.52x`, `0.61x`).
     - `Status`: Distinct icons and badges:
       - Cancelled runs display a rose `close` icon and `cancelled` label.
       - Succeeded runs display a green `check` icon and `ok` label.
       - Outlier runs display an amber `warning` icon and `outlier` label.
  3. Open Full Report Button:
     - Uses `colPrimaryContainer` background with a single `open_in_new` icon and bold text.
awaiting: user response

## Tests

### 1. Quickshell Bar Display & VoicePopup Trigger
expected: Quickshell starts cleanly, top bar displays VoicePill, and hovering VoicePill opens the VoicePopup overlay both when idle and during active recording.
result: pass

### 2. Status Header, Action Gating, 2-Column Alignment, 3 Categorized Cards & Auto-Type Switch
expected: |
  Inside the VoicePopup overlay:
  1. Top Status Banner: Concise 1-word titles and pure duration.
  2. Action Button Gating: Single toggle button ("Start" / "Stop", disabled "Start" during transcribing/typing) without redundant transcribing label.
  3. 3 Distinct Cards: General/Audio (top), STT (middle), TTS (bottom) in separate visual boxes.
  4. Strict 2-Column Alignment: Labels strictly in 125px Column 1; all controls, chips, and grids strictly in Column 2.
  5. Auto-Type Switch: Replaces type/paste with simple ON/OFF auto-typing switch.
result: pass

### 3. Live Telemetry & Duration Stats
expected: |
  The popup displays live stats:
  - Recorded audio duration and transcribed duration
  - Total elapsed duration and recognized character count
result: [pending]

### 4. Interactive Configuration Controls & Atomic Persistence
expected: |
  The popup contains 12 configuration controls (switches for vad_filter, beep, capture_corpus; dropdown/selectors for model, device, compute_type, language, chunk_duration, output_method, beam_size, tts_voice, tts_backend).
  Modifying any setting immediately syncs to ~/.config/voicemode/config.json with 0600 permissions.
result: [pending]

### 5. Recent Runs Card & Full Report Button
expected: |
  The popup displays a scrollable list of recent runs parsed from metrics.jsonl in reverse chronological order (newest first) with duration, chars, RTF, and status tags.
  The "Open Full Report" button opens ~/.local/state/voicemode/report.html in the default browser.
result: [pending]

### 6. Configuration backend persistence and precedence in voice.py
expected: Configuration options sync to config.json with 0600 permissions and resolve with CLI > ENV > config.json > default precedence across all 12 settings
result: pass
source: automated
coverage_id: 11-01-D1

### 7. Dotfiles parity and full regression suite verification
expected: 100% byte-for-byte identity between repository and dotfiles copies of VoicePopup.qml and VoicePill.qml, with all 286 test suite checks passing
result: pass
source: automated
coverage_id: 11-02-D2

## Summary

total: 7
passed: 3
issues: 0
pending: 4
skipped: 0

## Gaps

[none yet]
