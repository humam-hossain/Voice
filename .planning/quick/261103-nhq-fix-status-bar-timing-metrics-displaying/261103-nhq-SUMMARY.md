---
status: complete
date: 2026-11-03
commit: 237debe
---

# Quick Task Summary: Fix status bar timing metrics displaying 0 after recording/transcription

## Overview
Resolved the issue where the Quickshell voice status pill and Live Telemetry displayed `0:00 | 0:00 | 0:00` following recording and transcription completion.

## Root Causes Fixed
1. **Premature `root.sttPid = 0` during Procfs Check:**
   When `/proc/<pid>/stat` indicated the worker process had completed, `Voice.qml` set `root.sttPid = 0`. On the subsequent 100ms poll, `recorder.pid` on disk still contained `pid`, causing `root.sttPid === pid` to evaluate to `false` and enter the `else` branch, resetting all durations to `0:00` just 100ms after the worker process exited.
2. **Unconditional `resetDuration()` in PID Discovery:**
   `Voice.qml` previously called `root.resetDuration()` unconditionally whenever encountering a new PID, wiping durations even when discovering a transcribing/typing process rather than restricting resets to new capture sessions (`rawState === "recording" || rawState === "starting"`).
3. **`typingLingerTimer` and Idle Poll Duration Wipes:**
   `typingLingerTimer.onTriggered` and the idle polling handler in `Voice.qml` unconditionally called `root.resetDuration()`, wiping durations the moment STT state transitioned to `idle` (which happens 5s after transcription completion).
4. **Missing Cache and Fallbacks in `VoicePill.qml`:**
   `VoicePill.qml` previously lacked cached properties for `lastTranscribedDuration` and `lastTotalDuration`, and `displayText` for `case "wrapup"` directly queried `Voice` durations without falling back to cached values. When `Voice` transitioned to `idle` and triggered `wrapUpTimer`, the pill displayed `0:00 | 0:00 | 0:00` for 5 seconds.

## Changes Made
- **`integrations/quickshell/Voice.qml` & `.dotfiles/.../Voice.qml`:**
  - Preserved `root.sttPid` while `recorder.pid` still references the PID.
  - Restricted `root.resetDuration()` to new recording/starting session starts.
  - Removed duration wipe on `typingLingerTimer.onTriggered` and idle polling cycle so completed metrics remain readable in Live Telemetry and during wrap-up.
- **`integrations/quickshell/VoicePill.qml` & `.dotfiles/.../VoicePill.qml`:**
  - Added `lastTranscribedDuration` and `lastTotalDuration` tracking alongside `lastRecordedDuration`.
  - Added signal handlers in `Connections` to cache non-zero durations for recorded, transcribed, and total times.
  - Updated `displayText` for `case "wrapup"` to fall back to cached durations if `Voice` durations are `0:00`.
  - Reset cached durations to `0:00` when a new capture session starts.
- **Tests & Parity:**
  - Maintained 100% byte-for-byte parity with `/home/pera/github_repo/.dotfiles/restow/quickshell/`.
  - Added `test_status_bar_timing_metrics_retention_after_transcription` to `tests/test_pill_integration_simulation.py` covering state transitions and duration retention.
  - Verified 287/287 tests passing in pytest.
