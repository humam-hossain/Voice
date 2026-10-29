---
status: diagnosed
phase: 07-eta-engine-and-calibration
source:
  - 07-01-SUMMARY.md
  - 07-02-SUMMARY.md
  - 07-03-SUMMARY.md
started: 2026-10-29T05:52:00Z
updated: 2026-10-29T07:19:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Core ETA Estimator & Ratio-of-Sums Engine
expected: Ratio-of-sums rate resolution sum(decode_s)/sum(audio_s), 4-tier hierarchy (L0..L3), James-Stein shrinkage blending, dynamic model load subtraction, and prediction horizon ending at text insertion all execute correctly with 100% pass across hermetic unit tests.
result: pass

### 2. Mid-Run Recalculation & 1-Second Dwell Overrun
expected: Mid-run segment rate updates recalculate smoothly during Whisper generator consumption; downward revisions step down immediately while upward revisions are debounced; overruns dwell at 1s for 1.0s before transitioning to "Finishing…" with overrun: true.
result: pass

### 3. Calibration Persistence, Exclusion Gating & Cold Boot
expected: Worker finalization updates calibration.json cache strictly post-paste with 0o600 permissions; failed, fallback, cold, and outlier runs are filtered out of calibration; tmpfs .boot_session marker cleanly marks cold boot runs; MAD confidence score is computed on bounded residuals.
result: pass

### 4. CLI Status JSON Contract Extended Fields
expected: Running python voice.py --status --json outputs valid JSON adhering to extended status contract, exposing revision_count, last_revised_at, key_level, key_n, eta_source, eta_confidence, overrun, eta_remaining_s, and eta_epoch.
result: pass

### 5. CLI Reset Calibration and Epoch Marker
expected: Running python voice.py --reset-calibration deletes calibration.json, sets .calibration_reset epoch timestamp file, and outputs "Calibration reset to priors."
result: pass

### 6. Environment Variable Kill Switch (VOICE_ETA=off)
expected: Setting VOICE_ETA=off suppresses ETA calculations across all telemetry queries, returning None for all ETA fields in status and telemetry.
result: pass

### 7. Live Push-to-Talk Dictation with Visible ETA
expected: |
  Step-by-step test instructions:
  1. Focus an open text editor, scratchpad, or terminal where text can be typed.
  2. Start dictation:
     - Press your configured Hyprland push-to-talk hotkey, OR run in another terminal: `python voice.py --toggle`
  3. Speak a test sentence for 3-5 seconds (e.g., "The quick brown fox jumps over the lazy dog").
  4. Stop dictation (release the hotkey, or run `python voice.py --toggle` again).

  Observable behavior to confirm:
  1. The status overlay / pill appears immediately upon entering transcription with a single integer countdown (e.g., "~2s", "1s").
  2. No negative numbers, zero seconds, or ranges are shown.
  3. If transcription overruns the estimate, it dwells at "1s" for exactly 1.0 second before transitioning to "Finishing…".
  4. The transcribed text types directly into your focused window.
result: issue
reported: "there is no status overlay or PILO nothing appears, like everything is just like before so that is the issue, like what i wanted was that as i am recording the audio for each chunk of audio there is supposed to be converted in parallel so when it is getting converted there should be another time clock that will show that ok this is how much seconds have been already confirmed convert it to text add that to the time, this is the total time that has been added, currently I am seeing the previous recording my audio is the timer not the other things like the other one so that's how I want to do it. like X:XX | X:XX (first one for showing audio recording | second one for how much audio has been transcribed to text)"
severity: major

## Summary

total: 7
passed: 6
issues: 1
pending: 0
skipped: 0

## Gaps

- gap_id: G-07-7
  truth: "Voice status pill reflects live transcription progress and dual-timer/ETA display during recording and transcribing states rather than only showing a static timer or Transcribing label"
  status: failed
  reason: "User reported: there is no status overlay or PILO nothing appears, like everything is just like before so that is the issue, like what i wanted was that as i am recording the audio for each chunk of audio there is supposed to be converted in parallel so when it is getting converted there should be another time clock that will show that ok this is how much seconds have been already confirmed convert it to text add that to the time, this is the total time that has been added, currently I am seeing the previous recording my audio is the timer not the other things like the other one so that's how I want to do it. like X:XX | X:XX (first one for showing audio recording | second one for how much audio has been transcribed to text)"
  severity: major
  test: 7
  root_cause: "Status contract and worker do not publish parallel chunk transcribed_audio_s to status.json during recording, and Quickshell Voice.qml/VoicePill.qml only monitors recorder.pid without reading status.json or rendering dual-timers X:XX | X:XX"
  artifacts:
    - path: "voicemode_telemetry.py"
      issue: "STATUS_V1_KEYS does not expose transcribed_audio_s"
    - path: "voice.py"
      issue: "worker_consumer does not publish transcribed_audio_s during active recording chunks"
    - path: "/home/pera/.config/quickshell/ii/services/Voice.qml"
      issue: "FileView does not read status.json and lacks transcribedSeconds / eta properties"
    - path: "/home/pera/.config/quickshell/ii/modules/ii/bar/VoicePill.qml"
      issue: "displayText does not render dual timer X:XX | X:XX or ETA countdown pill"
  missing:
    - "Extend status schema and worker publishing to emit transcribed_audio_s during parallel chunk decoding"
    - "Connect Quickshell Voice.qml to status.json and expose transcribed duration and ETA properties"
    - "Update VoicePill.qml displayText to render X:XX | X:XX during recording and live ETA countdown during transcribing"
  debug_session: .planning/debug/status-pill-dual-timer.md
