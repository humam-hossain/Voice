---
status: resolved
trigger: "A roughly four-minute dictation did not transcribe and showed no notification; determine whether its failure is in the log and whether the diagnostics change covers it."
created: 2026-09-25
updated: 2026-09-25
symptoms:
  expected: "Transcribe the recording and insert it, or report the failure stage through a desktop notification and the log."
  actual: "The 243.5-second recording stopped, then the background STT process logged a 60-second transcription watchdog timeout and aborted without a desktop notification."
  errors: "voice.log contains: voice STT transcription watchdog timed out after 60s. Aborting daemon."
  timeline: "The failed recording began at 20:33:31 local time and stopped at about 20:37:35 on 2026-09-25. A subsequent 28.2-second recording succeeded."
  reproduction: "Record for about four minutes, stop, and let medium.en transcription on CPU int8 run past the 60-second watchdog."
---

## Current Focus
- hypothesis: Confirmed — the watchdog hard-exits the process with os._exit(1), bypassing the STT failure reporter, notification, and WAV cleanup.
- test: Compare the watchdog handler with the normal STT exception handlers and correlate the exact log lines and retained WAV file.
- expecting: The timeout path skips failure diagnostics and the failed recording remains recoverable.
- next_action: None; diagnosis complete. Application code was not changed.

## Evidence
- timestamp: 2026-09-25 20:40 +06
  observation: voice.log shows the 20:33:31 session recording for 243.5s, then CPU int8 medium.en load succeeded, then the 60-second transcription watchdog timed out. No Transcript inserted or failure notification message followed.
- timestamp: 2026-09-25 20:40 +06
  observation: /tmp/voice-lkp7lfb0.wav exists at 7,790,240 bytes, matching the failed recording. This indicates the hard exit skipped the finally cleanup.
- timestamp: 2026-09-25 20:40 +06
  observation: run_background_recording uses threading.Timer(60.0, transcription_watchdog_handler); that handler prints to stderr, removes the PID state, then calls os._exit(1). Normal STT exceptions instead call report_stt_failure, which writes traceback context and attempts a critical notification.
- timestamp: 2026-09-25 20:40 +06
  observation: Commit 06c542c (2026-09-25 19:40 +06) added detailed STT failure diagnostics, while the failed session occurred later at 20:33. The current code still has the direct-exit watchdog path.
- timestamp: 2026-09-25 20:45 +06
  observation: Re-ran local transcription directly against the retained WAV outside the background watchdog path; it completed and recovered the user's dictation. The combined model loading and transcription work exceeded the app's fixed 60-second watchdog during the original run; the available log does not isolate phase timings.
- timestamp: 2026-09-25 21:39 +06
  observation: Follow-up implementation added a configurable 300-second default, routes watchdog expiry through detailed failure reporting with the recovery WAV path, and adds unit coverage. The daemon module passes 25 tests and the full suite passes 106 tests; syntax compilation passes. A live multi-minute inference and desktop notification were not exercised.

## Eliminated
- hypothesis: The microphone capture did not start or the WAV was empty.
  reason: The log records 243.5 seconds and the WAV file exists with a plausible multi-megabyte size.

## Resolution
- root_cause: The 60-second watchdog timer covers model loading and transcription. When it fires, its handler writes a generic timeout line and calls os._exit(1), bypassing report_stt_failure(), notify(), and the worker's finally cleanup.
- fix: Implemented in voice.py. The watchdog defaults to 300 seconds, accepts a positive VOICE_STT_TIMEOUT_SECONDS override, reports timeout stage/elapsed time and retained WAV through the shared failure reporter, and preserves existing successful insertion behavior.
- verification: Correlated voice.log with the code path, independently transcribed the retained WAV, passed the focused daemon suite (25 tests), passed the full unittest suite (106 tests), and passed py_compile. A live multi-minute timeout and Wayland notification delivery were not exercised.
- files_changed: .planning/debug/long-stt-timeout-no-notification.md, voice.py, tests/test_hyprland_daemon.py
- workflow_note: The patch and tests remain uncommitted because the GSD branch guard marks main protected and the sandbox does not permit creating git refs.
