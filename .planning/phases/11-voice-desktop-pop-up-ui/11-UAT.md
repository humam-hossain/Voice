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

number: 2
name: Status Header, Action Gating, 2-Column Alignment, 3 Categorized Cards & Auto-Type Switch
expected: |
  Inside the VoicePopup overlay:
  1. Top Status Banner:
     - Concise 1-word titles: "Recording", "Transcribing", "Typing", "Speaking", "Idle".
     - Displays pure live duration timer without any artificial " / 5:00" limit.
     - Pulsing dot animation with matching bar colors.
  2. Action Button State Gating:
     - When idle: Toggle button shows "Start" (green, enabled).
     - When recording: Toggle button shows "Stop" (primary/accent color, enabled).
     - When transcribing/typing: Button stays labeled "Start" but is disabled/dimmed (opacity 0.5) without redundant "Transcribing" text, while status banner above clearly shows current state.
     - Cancel button: Enabled only while recording, disabled otherwise.
  3. 3 Distinct Categorized Cards & Reordering:
     - Box 1 (Top): "General / Audio" (tune icon, primary color) with Audio Cues switch and Corpus Capture selector.
     - Box 2 (Middle): "Speech-to-Text (STT)" (mic icon, sky blue color) with STT Model, Device, Compute Type, Language, Chunk Duration, Beam Size, VAD Filter, and Auto-Type switch.
     - Box 3 (Bottom): "Text-to-Speech (TTS)" (volume_up icon, secondary color) with TTS Backend and TTS Voice.
     - Each section is an independent container card with its own border, header icon, colored title, and divider.
  4. Strict 2-Column Grid Alignment:
     - Column 1: Configuration label with consistent 125px width across all rows.
     - Column 2: All options/values, switches, steppers, and multi-row model/voice grids stay strictly inside Column 2 and never cross into Column 1.
     - 4-column aligned grids for STT Model (10 models) and TTS Voice (10 voices).
  5. Auto-Type Switch:
     - Replaced conflicting "type" vs "paste" selector with a clean "Auto-Type" switch (ON = types into window; OFF = preserves in clipboard for manual pasting, e.g. Ctrl+Shift+V in terminal).
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
result: [pending]
result: [pending]

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
