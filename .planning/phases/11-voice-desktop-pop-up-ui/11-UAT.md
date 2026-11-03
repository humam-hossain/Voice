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
name: Status Header, Action Gating, Dimensions & Telemetry Font Scaling
expected: |
  Inside the VoicePopup overlay:
  1. Top Status Banner:
     - Placed prominently above the action buttons.
     - Displays state icon, state title, live durations, and heartbeat/breathing pulse when active.
     - Uses matching bar palette colors (Recording = colPrimary, Transcribing = Sky Blue #38bdf8, Typing = Neon Green #4ade80, Speaking = Secondary, Idle = Surface Variant).
  2. Action Button State Gating:
     - When idle: Toggle button shows "Start Recording" (green, enabled).
     - When recording: Toggle button shows "Stop Recording" (red/accent, enabled).
     - When transcribing/typing/speaking: Toggle button transitions to "Transcribing..." / "Typing..." (disabled / non-clickable) so premature re-recording is blocked until idle.
     - Cancel button: Enabled only while recording, disabled otherwise.
  3. Left Column Font Scaling:
     - Live Telemetry labels and values enlarged from smaller to small/normal (matching the right-side selector buttons).
     - Recent Dictations list and headers enlarged to match.
awaiting: user response

## Tests

### 1. Quickshell Bar Display & VoicePopup Trigger
expected: Quickshell starts cleanly, top bar displays VoicePill, and hovering VoicePill opens the VoicePopup overlay both when idle and during active recording.
result: pass

### 2. Status Header, Action Gating, Dimensions & Telemetry Font Scaling
expected: |
  Inside the VoicePopup overlay:
  1. Top Status Banner:
     - Placed prominently above the action buttons.
     - Displays state icon, state title, live durations, and heartbeat/breathing pulse when active.
     - Uses matching bar palette colors (Recording = colPrimary, Transcribing = Sky Blue #38bdf8, Typing = Neon Green #4ade80, Speaking = Secondary, Idle = Surface Variant).
  2. Action Button State Gating:
     - When idle: Toggle button shows "Start Recording" (green, enabled).
     - When recording: Toggle button shows "Stop Recording" (red/accent, enabled).
     - When transcribing/typing/speaking: Toggle button transitions to "Transcribing..." / "Typing..." (disabled / non-clickable) so premature re-recording is blocked until idle.
     - Cancel button: Enabled only while recording, disabled otherwise.
  3. Left Column Font Scaling:
     - Live Telemetry labels and values enlarged from smaller to small/normal (matching the right-side selector buttons).
     - Recent Dictations list and headers enlarged to match.
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
