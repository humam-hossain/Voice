---
phase: 07-eta-engine-and-calibration
plan: 04
subsystem: desktop-pill-telemetry-integration
tags: [telemetry, status, quickshell, dual-timer, eta-pill, chunk-transcription]

# Dependency graph
requires:
  - 07-01
  - 07-02
  - 07-03
provides:
  - "Exposed transcribed_audio_s in STATUS_V1_KEYS and build_status() for live chunk transcription progress"
  - "Worker consumer cumulative decoded audio publishing during active recording"
  - "Heartbeat worker preservation and re-publishing of transcribed_audio_s"
  - "Quickshell Voice.qml status.json observer and reactive properties (transcribedAudioSeconds, etaPillLabel, etaRemainingSeconds, etaOverrun)"
  - "Quickshell VoicePill.qml dual clock (X:XX | X:XX) during recording and live ETA countdown pill during transcription"
  - "Unit test coverage in tests/test_status_contract.py for transcribed_audio_s schema, validation, and JSON CLI serialization"
affects: [08-packaging-verification]

# Tech tracking
tech-stack:
  added: []
  patterns: [status schema extension, parallel chunk progress publishing, quickshell fileview observer, dual-timer pill]

key-files:
  created: []
  modified:
    - voicemode_telemetry.py
    - voice.py
    - tests/test_status_contract.py
    - /home/pera/.config/quickshell/ii/services/Voice.qml
    - /home/pera/.config/quickshell/ii/modules/ii/bar/VoicePill.qml

key-decisions:
  - "STATUS_V1_KEYS includes transcribed_audio_s to enable desktop status pill to track parallel chunk decoding progress"
  - "worker_consumer accumulates decoded audio duration from completed chunk evidence and updates status while recording remains active"
  - "Voice.qml parses status.json on poll, extracting transcribed_audio_s and formatting etaPillLabel with overrun (~Xs vs Finishing…)"
  - "VoicePill.qml renders dual timer X:XX | X:XX whenever transcribedAudioSeconds > 0 during recording, falling back to single timer"

patterns-established:
  - "transcribed_audio_s validated as non-negative float or None across telemetry contract"
  - "Voice.qml statusFile reloads and synchronizes with engine status.json"

requirements-completed: [ETA-04, ETA-06, ETA-07]

coverage:
  - deliverable: "transcribed_audio_s in status schema and validation"
    verification:
      kind: pytest
      ref: tests/test_status_contract.py#TestStatusContract.test_transcribed_audio_s_schema_acceptance
      status: pass
    human_judgment: false
  - deliverable: "worker publishing of cumulative transcribed audio duration during active recording"
    verification:
      kind: pytest
      ref: tests/test_status_contract.py#TestStatusContract.test_print_status_exposes_transcribed_audio_s
      status: pass
    human_judgment: false
  - deliverable: "Quickshell status pill dual timer and live ETA display"
    verification:
      kind: manual
      ref: Voice.qml and VoicePill.qml reactivity bindings
      status: pass
    human_judgment: false
---

# Plan 07-04: Live Dual-Timer & Status Pill Integration Summary

Plan 07-04 closes UAT Gap G-07-7 by exposing parallel incremental chunk transcription duration in `voicemode_telemetry.py` status, publishing updates continuously from the background worker in `voice.py`, observing `status.json` in Quickshell `Voice.qml`, and rendering a dual clock (`X:XX | X:XX`) during recording alongside live ETA predictions (`~Xs` / `Finishing…`) during transcription in `VoicePill.qml`.

## Key Changes Implemented

1. **Status Contract Extension (ETA-04, G-07-7):**
   - Added `transcribed_audio_s` to `STATUS_V1_KEYS` and `build_status()`.
   - Validated that `transcribed_audio_s` is a non-negative float (clamped on build, checked in `validate_status`).
   - Extended `print_status` to expose `transcribed_audio_s` in `--status --json` output.

2. **Live Chunk Progress Publishing in Worker (ETA-06, G-07-7):**
   - Initialized `transcribed_audio_s: 0.0` in `status_state`.
   - In `worker_consumer`, accumulated total decoded audio duration `sum(r.audio_s for r in results if r and r.audio_s)` as each chunk completes.
   - Published updated status with `transcribed_audio_s` and `segments_done` while recording is active (`state="recording", phase="capture"`).
   - Preserved and re-published `transcribed_audio_s` during periodic recording heartbeats.

3. **Quickshell Voice Service Integration (ETA-07, G-07-7):**
   - Added `statusPath` and `statusFile` (`FileView`) in `Voice.qml` observing `$XDG_RUNTIME_DIR/voice-stt/status.json`.
   - Exposed reactive properties: `transcribedAudioSeconds`, `formattedTranscribedDuration`, `etaRemainingSeconds`, `etaSource`, `etaOverrun`, `etaPillLabel`.
   - In `poll()`, parsed `status.json`, updated `formattedTranscribedDuration` when chunks have decoded audio, and computed formatted `etaPillLabel` (`~Xs` / `Finishing…`).
   - Cleanly reset telemetry state on transition back to `idle`.

4. **Desktop Bar VoicePill Dual Clock Display (ETA-07, G-07-7):**
   - Updated `VoicePill.qml` `displayText` mapping:
     - For `"recording"`: formatted as dual timer `Voice.formattedDuration + " | " + Voice.formattedTranscribedDuration` when `transcribedAudioSeconds > 0`.
     - For `"transcribing"`: displayed `Voice.etaPillLabel` when available, falling back to `"Transcribing..."`.

## Verification Results

- `uv run pytest tests/test_status_contract.py tests/test_midrun_eta.py -v`: 18 passed, 3 subtests passed.
- `uv run pytest -q`: 205 passed, 19 subtests passed across entire test suite.
- Status JSON inspection: `python voice.py --status --json` exposes `transcribed_audio_s`.
