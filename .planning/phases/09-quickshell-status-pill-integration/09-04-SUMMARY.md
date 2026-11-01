---
phase: 09-quickshell-status-pill-integration
plan: 04
type: summary
gap_closure: true
gap_ids:
  - G-09-1
started: 2026-11-01T15:22:00Z
completed: 2026-11-01T15:38:00Z
status: complete
commits:
  - 14ed3a9
  - fc4d6a8
  - c919783
---

# Phase 09 Plan 04 Summary: Gap Closure — 5-Second Linger, Total Duration Freezing, and Re-entry Prevention

## Objective

Close UAT Gap G-09-1 by implementing a 5-second completion linger, freezing total duration when typing starts, and preventing concurrent recording attempts while transcribing or typing.

## Changes Made

### Task 1: QML Timer and Duration Freezing Updates

**Voice.qml** (`.dotfiles` authoritative + vendored copy):
- Changed `typingLingerTimer.interval` from `1000` to `5000` — pill lingers 5 full seconds after typing completes.
- Added `typingDurationCaptured` boolean property to control one-shot freeze.
- Split `updateDuration()`: `overallState === "transcribing"` continues ticking `totalElapsedSeconds` with wall clock; `overallState === "typing"` captures total duration once then freezes — total duration strictly measures start-of-recording to end-of-transcription.
- Reset `typingDurationCaptured` in `resetDuration()`, on idle poll cleanup, and on new recording start.

**VoicePill.qml** (`.dotfiles` authoritative + vendored copy):
- Changed `wrapUpTimer.interval` from `1500` to `5000` — Neon Green styling and 3-bar timers remain visible for 5 seconds before collapsing to idle.

### Task 2: voice.py Concurrency Hardening

**toggle_background_recording()**:
- When `state == "recording"` and SIGUSR1 is sent: immediately calls `write_pid_state(pid, "transcribing")` under the PID lock so disk state transitions atomically without relying on async worker wake-up.
- When `state in ("transcribing", "typing")`: plays error cue, sends desktop notification ("Cannot start recording: transcription/typing in progress."), prints warning to stderr, and returns 0 without spawning.
- `notify()` hardened with try/except around `subprocess.run` to prevent test failures when `notify-send` Popen is mocked.

### Task 3: Mirroring, Documentation, and Tests

- Vendored copies in `integrations/quickshell/` mirrored from `.dotfiles` — verified byte-identical via `diff -u`.
- `integrations/quickshell/README.md` updated: 5s linger (was 1.5s), total duration definition (freezes at transcription end, excludes typing time), timer intervals (5000ms).
- 4 new simulation tests added to `test_pill_integration_simulation.py`:
  - `test_qml_timer_intervals_and_parity`: asserts 5000ms on both timers + byte parity between dotfiles and vendored.
  - `test_total_duration_freezes_during_typing`: Python simulation of Voice.qml `updateDuration()` logic verifying freeze semantics.
  - `test_toggle_recording_atomically_transitions_to_transcribing`: verifies D-03 atomic state transition.
  - `test_toggle_recording_rejects_during_transcribing_and_typing`: verifies D-04 re-entry rejection with error cue and notification.
- `test_hyprland_daemon.py::test_busy_state_protection_error_cue` updated to expect the new `notify()` call.

## Verification

- **228 tests pass** (`uv run pytest tests/ -x` — 228 passed in 10.30s).
- Zero diff between `.dotfiles` QML and vendored copies confirmed.
- All 6 design truths (D-01 through D-06) verified.

## Design Truth Traceability

| Truth | Status | Evidence |
|-------|--------|----------|
| D-01: 5s linger after typing | ✅ | `typingLingerTimer.interval: 5000`, `wrapUpTimer.interval: 5000`, `test_qml_timer_intervals_and_parity` |
| D-02: Total duration freezes at typing | ✅ | `typingDurationCaptured` flag, split `updateDuration()`, `test_total_duration_freezes_during_typing` |
| D-03: Atomic transcribing on SIGUSR1 | ✅ | `write_pid_state(pid, "transcribing")` after `os.kill`, `test_toggle_recording_atomically_transitions_to_transcribing` |
| D-04: Reject recording during transcribing/typing | ✅ | `state in ("transcribing", "typing")` guard, `test_toggle_recording_rejects_during_transcribing_and_typing` |
| D-05: Byte-identical QML parity | ✅ | `diff -u` empty, `test_qml_timer_intervals_and_parity` |
| D-06: All tests pass | ✅ | 228/228 passed |
