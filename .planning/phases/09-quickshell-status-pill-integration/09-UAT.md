---
status: diagnosed
phase: 09-quickshell-status-pill-integration
source:
  - 09-01-SUMMARY.md
  - 09-02-SUMMARY.md
  - 09-03-SUMMARY.md
started: 2026-11-01T14:26:00Z
updated: 2026-11-01T14:43:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Quickshell Status Pill Integration Confirmation
expected: Confirm that the Quickshell status pill integration behavior matches expectations on your desktop.
result: issue
reported: "1. Linger 5s after writing finishes so user can inspect all 3 final timer values. 2. Exclude typing time from total duration (total time freezes when transcribing ends and typing begins). 3. Strictly prevent starting a new recording while previous session is still transcribing or typing."
severity: major

### 2. Published transcribed_audio_s during tail decode and typing states in voice.py
expected: Published transcribed_audio_s during tail decode and typing states in voice.py
result: pass
source: automated
coverage_id: 09-01-D1

### 3. Typing state publishes transcribed_audio_s and audio_s matching final duration
expected: Typing state publishes transcribed_audio_s and audio_s matching final duration
result: pass
source: automated
coverage_id: 09-01-D2

### 4. Multi-bar progress timers and report opening in Voice.qml
expected: Multi-bar progress timers and report opening in Voice.qml
result: pass
source: automated
coverage_id: 09-02-D1

### 5. Dual timer, breathing pulse, and glyph transitions in VoicePill.qml
expected: Dual timer, breathing pulse, and glyph transitions in VoicePill.qml
result: pass
source: automated
coverage_id: 09-02-D2

### 6. 3-bar progress timer and Neon Green edit pen glyph during typing
expected: 3-bar progress timer and Neon Green edit pen glyph during typing
result: pass
source: automated
coverage_id: 09-02-D3

### 7. Secure report click-through and path traversal protection
expected: Secure report click-through and path traversal protection
result: pass
source: automated
coverage_id: 09-02-D4

### 8. Committed live QML files in .dotfiles with clean status
expected: Committed live QML files in .dotfiles with clean status
result: pass
source: automated
coverage_id: 09-03-D1

### 9. Vendored exact reference copies and sync documentation in integrations/quickshell/
expected: Vendored exact reference copies and sync documentation in integrations/quickshell/
result: pass
source: automated
coverage_id: 09-03-D2

## Summary

total: 9
passed: 8
issues: 1
pending: 0
skipped: 0

## Gaps

- gap_id: G-09-1
  truth: "Pill displays honest duration metrics with 5s completion linger, total duration strictly freezes at transcription completion (excluding typing time), and hotkey re-entry is blocked during transcribing/typing."
  status: failed
  reason: "User reported: 1. Linger 5s after writing finishes so user can inspect all 3 final timer values. 2. Exclude typing time from total duration (total time freezes when transcribing ends and typing begins). 3. Strictly prevent starting a new recording while previous session is still transcribing or typing."
  severity: major
  test: 1
  root_cause: "Voice.qml continues wall-clock ticking for totalElapsedSeconds during typing and uses 1000ms linger; VoicePill.qml uses 1500ms wrapUpTimer; voice.py toggle_background_recording does not atomically mark state transcribing when signaling stop."
  artifacts:
    - path: "integrations/quickshell/Voice.qml"
      issue: "Total elapsed continues ticking during typing; linger timer is 1.0s instead of 5.0s"
    - path: "integrations/quickshell/VoicePill.qml"
      issue: "wrapUpTimer is 1.5s instead of 5.0s"
    - path: "voice.py"
      issue: "toggle_background_recording sends SIGUSR1 on stop without atomically updating recorder.pid state to transcribing under PID lock"
  missing:
    - "Set wrapUpTimer and typingLingerTimer intervals to 5000ms across Voice.qml and VoicePill.qml"
    - "Freeze totalElapsedSeconds at transcription completion in Voice.qml so typing duration is excluded from total"
    - "Write transcribing state under with_pid_lock when signaling stop in toggle_background_recording to prevent re-trigger races"
