---
phase: quick-task
plan: 261018-pdy
subsystem: stt-audio-chunking
tags: [stt, audio, chunking, whisper, resilience]
requires: []
provides:
  - Gapless audio chunking in Recorder at 3-minute intervals (180.0s)
  - Zero-pause background disk write pipeline for completed audio segments
  - Sequential transcription of audio segments upon session stop
  - Error skipping resilience with `[SKIPPING 3MIN SEG]` marker on transcription failure
  - Whisper prompt chaining across segment boundaries to maintain semantic continuity
  - Single combined text output insertion at the end of the recording session
  - Configurable chunk size via `--chunk-seconds` and `VOICE_CHUNK_SECONDS`
affects: [voice.py, tests/test_hyprland_daemon.py, tests/test_audio_chunking.py]
actuals:
  tasks: 4
  tests: 117 passed
key-files:
  modified: [voice.py, tests/test_hyprland_daemon.py]
  created: [tests/test_audio_chunking.py]
key-decisions:
  - "Default DEFAULT_CHUNK_SECONDS to 180.0s (3 minutes) and SKIPPED_SEGMENT_MARKER to '[SKIPPING 3MIN SEG]'."
  - "Perform chunk cuts in Recorder._callback without stopping or restarting the PortAudio InputStream for true zero-pause recording."
  - "Offload WAV disk encoding and writing to daemon background threads to keep the audio callback non-blocking and prevent buffer overruns."
  - "Transcribe audio chunks sequentially on session stop, with prompt chaining (initial_prompt from prior segment) and per-segment watchdog timers."
  - "Catch segment-level transcription failures, log diagnostics with recovery WAV pointers, and insert '[SKIPPING 3MIN SEG]' without abandoning the remainder of the session."
  - "Type or paste the assembled transcript in a single operation once all segments are converted."
status: complete
---

# Quick Task 261018-pdy Summary

Implemented gapless 3-minute audio chunking, sequential post-recording transcription, error skipping with `[SKIPPING 3MIN SEG]`, and single-batch text insertion at session completion.

## Key Changes

1. **Gapless Audio Chunking in `Recorder` (`voice.py`):**
   - Added `chunk_seconds: float = DEFAULT_CHUNK_SECONDS` (180.0s) to `Recorder`.
   - Audio input stream (`sd.InputStream`) runs continuously without stopping between chunks.
   - When accumulated samples cross the chunk threshold, frames are cleanly rolled over into a new buffer, and writing to WAV (`/tmp/voice-xxxx-segXX.wav` or `--save-dir`) is offloaded to a background thread to prevent audio dropouts.
   - `Recorder.stop_to_wav()` joins writer threads, flushes the final partial chunk, and returns `(list[Path], duration, should_delete)` in chronological order.

2. **Sequential Transcription & Error Skipping (`voice.py`):**
   - In `run_background_recording()` and `run_terminal_mode()`, the session iterates through all segment WAV files sequentially.
   - For each chunk, a per-chunk watchdog timer protects against hangs.
   - The tail of the previous chunk's transcript is passed as `initial_prompt` to Faster-Whisper to maintain semantic and punctuation continuity.
   - If transcription of a segment raises an exception or times out, the error is logged, diagnostics are saved with the recovery WAV path, and `[SKIPPING 3MIN SEG]` is appended to the transcript.
   - Once all segments are processed, all texts are combined into one string and inserted into the active window (via `wtype`, `ydotool`, or clipboard).
   - Temporary chunk files are cleaned up in `finally`.

3. **Configuration & Safety Ceilings (`voice.py`):**
   - Added `--chunk-seconds` CLI flag and `VOICE_CHUNK_SECONDS` environment variable (default: 180.0s).
   - Raised session safety ceiling `MAX_RECORDING_SECONDS` from 180s to 1800s (30 minutes) so multi-chunk sessions can run uninterrupted up to 30 minutes (or as configured via `VOICE_MAX_RECORDING_SECONDS`).

4. **Testing (`tests/test_audio_chunking.py`, `tests/test_hyprland_daemon.py`):**
   - Added unit tests verifying single-chunk handling, multiple gapless chunks with correct sample counts, multi-chunk sequential transcription with prompt chaining, error skipping resilience (`[SKIPPING 3MIN SEG]`), and temp file cleanup.
   - Updated max recording ceiling test in `tests/test_hyprland_daemon.py`.
   - All 117 tests pass.
