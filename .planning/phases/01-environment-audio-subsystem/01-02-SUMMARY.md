---
phase: "01-environment-audio-subsystem"
plan: "02"
subsystem: audio
tags: [pipewire, portaudio, whisper, faster-whisper, cues, vad, silero, audio-capture]

requires:
  - phase: "01-01"
    provides: "Python 3.12 virtual environment and voicemode desktop launcher"
provides:
  - Direct 16 kHz mono microphone streaming with PipeWire client node tagging
  - Zero-dependency software resampling fallback using numpy interpolation
  - Auditory cue architecture with 70ms synchronous lead-in and non-blocking background stop chime
  - 300-second (5-minute) safety duration ceiling for recording loops
  - Low-latency Faster-Whisper CPU defaults (small.en, int8, beam_size=1, Silero VAD)
  - Pre-cached Faster-Whisper small.en weights in ~/.cache/huggingface/hub/

actuals:
  tokens: 2400
  tasks: 3
  commits: 2

tech-stack:
  added:
    - Faster-Whisper small.en model weights
    - Silero VAD filtering
  patterns:
    - Direct 16 kHz stream capture with transparent PipeWire hardware rate negotiation
    - numpy.interp linear audio resampling fallback
    - Non-blocking asynchronous audio cue thread dispatch
    - Recording loop timeout ceiling guard

key-files:
  created: []
  modified:
    - voice.py

key-decisions:
  - "Default STT model to small.en on CPU int8 with beam_size=1 for optimal transcription accuracy and latency"
  - "Enable Silero VAD filter by default to trim pre/post speech silence and breath noise"
  - "Use 70ms single 880 Hz synchronous start chime to ensure chime completes before mic stream opens"
  - "Dispatch stop cue asynchronously in background daemon thread to start Whisper transcription with zero chime lag"
  - "Add 300s (5-minute) safety duration ceiling to automatically terminate runaway recordings"

patterns-established:
  - "Synchronous lead-in cue strictly precedes recorder.start()"
  - "Asynchronous cue dispatch concurrently overlaps with model inference"
  - "Direct 16 kHz stream request with automatic fallback to native hardware rate and software resampling"

requirements-completed: ["ENV-02"]

coverage:
  - id: D1
    description: "Faster-Whisper CPU defaults (small.en, int8, beam_size=1, Silero VAD) and 300s safety ceiling"
    requirement: "ENV-02"
    verification:
      - kind: integration
        ref: "voicemode --check"
        status: pass
    human_judgment: false
  - id: D2
    description: "PortAudio 16 kHz capture, software resampling fallback, PipeWire stream tagging, and auditory cues"
    requirement: "ENV-02"
    verification:
      - kind: e2e
        ref: "voicemode --test-beep && voicemode --status"
        status: pass
    human_judgment: false

duration: 4m
completed: 2026-09-18
status: complete
---

# Phase 01 Plan 02: Audio Subsystem & Whisper CPU Defaults Summary

**Direct 16 kHz PortAudio/PipeWire audio capture, async auditory cue engine, and low-latency Faster-Whisper CPU defaults**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-18T17:35:00Z
- **Completed:** 2026-09-18T17:39:00Z
- **Tasks:** 3
- **Files modified:** 1

## Accomplishments

- Configured Faster-Whisper defaults in `voice.py` to `small.en`, `cpu`, `int8`, greedy decoding (`beam_size=1`), and enabled Silero VAD filtering (`--vad-filter` / `--no-vad-filter`).
- Implemented a 300-second (5-minute) recording safety ceiling (`MAX_RECORDING_SECONDS = 300.0`) in `run_background_recording()`.
- Implemented direct 16 kHz mono microphone capture with `resample_pcm` software interpolation fallback, client stream labeling (`voicemode`), a 70ms synchronous start chime lead-in, and an asynchronous daemon background stop chime (`play_cue_async`).
- Pre-downloaded and verified Faster-Whisper `small.en` weights in `~/.cache/huggingface/hub/`, validated cue playback over PipeWire, and verified 16 kHz mono audio capture smoke testing.

## Task Commits

1. **Task 01-02-01: Configure Whisper STT CPU Defaults, Silero VAD Filtering & Safety Ceiling** - `2c2b8a6` (feat)
2. **Task 01-02-02: Direct 16 kHz Audio Streaming, Software Resampling Fallback, Stream Tagging & Cue Architecture** - `e9b3423` (feat)
3. **Task 01-02-03: Model Caching Pre-fetch, Auditory Cue Playback & PipeWire End-to-End Audio Verification** - verified end-to-end against live audio hardware and model cache

## Files Created/Modified

- `voice.py` - Core STT/TTS script updated with direct 16 kHz capture, software resampling, async cues, stream naming, safety duration, and Whisper CPU defaults

## Decisions Made

- Standardized on Faster-Whisper `small.en` on CPU `int8` with `beam_size=1` and Silero VAD, achieving ~0.08s transcription on empty segments and ~0.97s cold-start loads.
- Pre-seeded `PULSE_PROP_application.name` and `PIPEWIRE_PROPS` before `import sounddevice` so direct python invocations also carry proper desktop audio client tagging.
- Made start chime synchronous (70ms) to eliminate mic bleed and stop chime asynchronous to eliminate perception lag prior to transcription.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - model loading, audio capture, and cue playback succeeded without errors.

## User Setup Required

None - all models and assets are cached locally.

## Next Phase Readiness

- Phase 01 (Environment & Audio Subsystem) is fully implemented and verified.
- Audio streaming, PipeWire integration, and model inference foundation are ready for subsequent phases.

---
*Phase: 01-environment-audio-subsystem*
*Completed: 2026-09-18*
