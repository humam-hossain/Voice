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
name: Status Header, Action Gating, Inline Selectors & Categorized Layout
expected: |
  Inside the VoicePopup overlay:
  1. Top Status Banner:
     - Concise 1-word titles: "Recording", "Transcribing", "Typing", "Speaking", "Idle".
     - Displays pure live duration timer without any artificial " / 5:00" limit.
     - Pulsing dot animation with matching bar colors.
  2. Action Button State Gating:
     - When idle: Toggle button shows "Start" (primary color, enabled).
     - When recording: Toggle button shows "Stop" (secondary color, enabled).
     - When transcribing/typing: Button shows "Transcribing" or "Typing" (disabled / non-clickable) to prevent premature re-recording.
     - Cancel button: Enabled only while recording, disabled otherwise.
  3. Inline Chip Grids (No Dropdown Focus Loss):
     - STT Model (10 models) and TTS Voice (10 voices) displayed as inline 2-row option chips.
     - Clicking a chip selects the option directly without closing the popup.
     - Selected chips retain their background and show a 2px primary border on hover without turning black.
  4. Number Steppers & Categorized Sections:
     - Steppers for Chunk Duration and Beam Size feature 32x32 +/- buttons and a centered value badge.
     - Configuration divided into 3 clean labeled sections: "Speech-to-Text (STT)", "Text-to-Speech (TTS)", and "General / Audio".
  5. Sizing & Typography:
     - Generous width (~50% screen width), symmetric margins, and enlarged legible typography across left and right panels.
awaiting: user response

## Tests

### 1. Quickshell Bar Display & VoicePopup Trigger
expected: Quickshell starts cleanly, top bar displays VoicePill, and hovering VoicePill opens the VoicePopup overlay both when idle and during active recording.
result: pass

### 2. Status Header, Action Gating, Inline Selectors & Categorized Layout
expected: |
  Inside the VoicePopup overlay:
  1. Top Status Banner: Concise 1-word titles ("Recording", "Transcribing", etc.) and pure duration with no " / 5:00" limit.
  2. Action Button Gating: Single toggle button ("Start" / "Stop" / disabled "Transcribing") and "Cancel" active only when recording.
  3. Inline Option Chips: STT Model and TTS Voice use inline chips with 2px primary hover border and no focus loss.
  4. Steppers: Prominent +/- buttons for Chunk Duration and Beam Size.
  5. Layout: 3 distinct categorized sections (STT, TTS, General/Audio) and 50% screen width.
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
