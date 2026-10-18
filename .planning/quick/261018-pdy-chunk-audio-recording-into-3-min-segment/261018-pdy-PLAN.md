# Quick Plan: Chunk Audio Recording into 3-Minute Segments with Sequential Transcription

**Goal:** Enable gapless 3-minute audio chunking during recording sessions, save each segment to a separate temporary WAV file without recording pauses, sequentially transcribe each segment on session stop, skip any failed segment with `[SKIPPING 3MIN SEG]`, and insert the full combined transcript at the end.

**Files in scope:**
- `voice.py`
- `tests/test_hyprland_daemon.py`
- `tests/test_audio_chunking.py` (new test suite dedicated to audio chunking & error recovery)

## Architecture & Implementation Plan

### 1. Gapless Audio Chunking in `Recorder`
- Add `chunk_seconds: float = 180.0` parameter to `Recorder.__init__`.
- In `Recorder._callback`:
  - Continually buffer incoming audio frames without stopping or restarting the `sd.InputStream`.
  - Count accumulated samples. When samples reach `chunk_samples = int(chunk_seconds * actual_sample_rate)`:
    - Atomically extract the completed frames for that chunk.
    - Start a new frame buffer for the next chunk immediately.
    - Dispatch writing of the completed chunk's WAV file to a background writer (or thread-safe completed chunk queue) to ensure zero disk I/O latency in the PortAudio callback thread.
- In `Recorder.stop_to_wav`:
  - Close the audio stream.
  - Flush any remaining frames as the final chunk.
  - Ensure all chunk WAV files are written and verified on disk.
  - Return `(list[Path], float, bool)` containing the list of chunk WAV paths, total recording duration, and cleanup flag (`should_delete`).
  - Provide backward-compatible handling so callers expecting `Path` or `list[Path]` both work seamlessly.

### 2. Sequential Transcription with Segment Error Recovery in `run_background_recording`
- Handle `wav_paths` (iterable of chunk paths).
- For each chunk file:
  - Start a per-chunk watchdog timer using `stt_timeout_seconds()`.
  - Pass the tail of previous segment transcripts as `initial_prompt` to Faster-Whisper to maintain semantic and punctuation continuity across chunk boundaries.
  - If a segment transcribes successfully, append its text.
  - If transcription of a segment raises an exception or fails, log the failure, report STT diagnostics with recovery WAV pointer, and append `[SKIPPING 3MIN SEG]`.
  - In `finally` for each chunk, cancel its watchdog timer and unlink temporary chunk files if `should_delete` is True.
- Combine all segment transcripts with `" ".join(...)`.
- After all segments are processed, type/paste the assembled transcript into the active focused window and copy to clipboard.

### 3. Session Safety Ceiling & CLI / Env Configuration
- Update `MAX_RECORDING_SECONDS = 1800.0` (30 minutes default ceiling for multi-chunk sessions, configurable via `VOICE_MAX_RECORDING_SECONDS`).
- Define `DEFAULT_CHUNK_SECONDS = 180.0` and `SKIPPED_SEGMENT_MARKER = "[SKIPPING 3MIN SEG]"`.
- Add `--chunk-seconds` flag to `parse_args()` and helper `chunk_seconds(args)`.

### 4. Comprehensive Unit Tests
- Create `tests/test_audio_chunking.py`:
  - Test `Recorder` chunking logic: verify zero-pause boundary splitting when sample threshold is reached.
  - Test multi-chunk sequential transcription in `run_background_recording`.
  - Test error resilience: mock a failure on chunk 2 in a 3-chunk recording and assert that chunk 1 and chunk 3 texts appear with `[SKIPPING 3MIN SEG]` in place of chunk 2.
  - Test temporary WAV file cleanup.
- Update `tests/test_hyprland_daemon.py`:
  - Update `test_safety_recording_duration_ceiling_default` to expect `1800.0`.
  - Verify all existing daemon and keybinding tests pass.

## Verification
- Run full unit test suite via `uv run python -m unittest discover tests`.
- Verify all tests pass with 0 errors.
