# Quick Plan: Fix status bar timing metrics displaying 0 after recording/transcription

**Goal:** Ensure the Quickshell status pill and Live Telemetry retain honest, non-zero timing metrics (`recorded_duration | transcribed_duration | total_duration`) throughout typing and post-recording wrap-up linger, eliminating the bug where metrics drop to `0:00 | 0:00 | 0:00`.

## Root Cause Analysis
1. In `Voice.qml:196`, when procfs indicates the worker process is no longer alive (`!procAlive`), `root.sttPid` was set to `0`. On the very next 100ms poll, `recorder.pid` still contained the exiting PID on disk. Because `root.sttPid` was `0`, `root.sttPid === pid` evaluated to `false`, entering the `else` branch which called `root.resetDuration()`. Because `status.json` had already been unlinked by `voice.py` on exit, the durations could not be re-parsed, permanently zeroing out `recordedAudioSeconds`, `transcribedAudioSeconds`, `totalElapsedSeconds`, and their formatted representations 100ms after completion.
2. In `Voice.qml:206`, `root.resetDuration()` was called unconditionally on any PID mismatch, even when the PID was in `transcribing` or `typing` state, rather than restricting resets strictly to new recording/starting sessions.
3. In `Voice.qml:121`, `typingLingerTimer.onTriggered` called `root.resetDuration()`, wiping durations the moment STT state transitioned to `idle`.
4. In `VoicePill.qml:107-127`, `VoicePill.qml` entered `wrapup` for 5s when `Voice.overallState` transitioned to `idle`, but queried `Voice.formattedRecordedDuration`, `Voice.formattedTranscribedDuration`, and `Voice.formattedTotalDuration` directly. Since `Voice.resetDuration()` had just wiped them, the pill displayed `0:00 | 0:00 | 0:00`. `VoicePill` also lacked cached properties for transcribed and total durations.

## Tasks

### 1. Fix Duration Retention & Lifecycle State in `Voice.qml`
- In `Voice.qml` `poll()`:
  - When `!procAlive`, do not reset `root.sttPid = 0` while `recorder.pid` still contains `pid`. Clear `root.sttPid = 0` only when `recText.length === 0` and linger is inactive.
  - In `if (root.sttPid === pid) ... else`: only call `root.resetDuration()` if `rawState === "recording" || rawState === "starting"`.
  - In `typingLingerTimer.onTriggered`: transition `root.sttState = "idle"` without calling `root.resetDuration()`. Durations are cleared when a new recording starts or when explicit reset is called.
  - In idle cleanup: do not wipe durations to 0 when idle so `VoicePopup.qml` and `VoicePill.qml` can read the metrics of the completed dictation.

### 2. Cache Durations and Fall Back in `VoicePill.qml`
- In `VoicePill.qml`:
  - Declare `property string lastTranscribedDuration: "0:00"` and `property string lastTotalDuration: "0:00"`.
  - Connect to `Voice.formattedRecordedDurationChanged`, `Voice.formattedTranscribedDurationChanged`, and `Voice.formattedTotalDurationChanged` to record the last non-"0:00" values.
  - In `displayText` for `case "wrapup"`, use the cached durations if `Voice` durations are `"0:00"` or empty.
  - Reset cached durations to `"0:00"` when a new session starts (`overallState` becomes `recording` or `starting`).

### 3. Maintain Dotfiles Parity & Add Regression Verification Tests
- Keep 100% byte-for-byte parity between:
  - `integrations/quickshell/Voice.qml` <-> `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml`
  - `integrations/quickshell/VoicePill.qml` <-> `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml`
- Add unit/regression simulation tests in `tests/test_pill_integration_simulation.py`:
  - Simulate worker process termination and status unlinking while in `transcribing` and `typing`.
  - Assert that `Voice.qml` and `VoicePill.qml` logic preserves the final non-zero durations (`recorded_duration`, `transcribed_duration`, `total_duration`) during typing and wrap-up without resetting to 0.
- Run `uv run pytest` to ensure 100% of test suite passes.
