---
phase: 03-text-to-speech-model-asset-pipeline
plan: "02"
subsystem: text-to-speech
tags: [wayland, primary-selection, wl-paste, text-normalization, pipewire, ffplay, interruption, garbage-collection]

requires:
  - phase: 03-text-to-speech-model-asset-pipeline
    plan: "01"
    provides: Kokoro ONNX model asset pipeline and verification
provides:
  - Native Wayland primary selection text capture (`wl-paste --primary`) with 1.0s timeout and clipboard fallback
  - Conservative text normalization pipeline (ANSI stripping, markdown flattening, URL simplification, snake_case splitting, path pauses, smart line pauses)
  - Text length bounding to 5,000 characters with user warning toast
  - Upfront validation and empty-text abort with dual-tone error chime before worker spawn
  - PipeWire audio stream identification (`PULSE_PROP_application.name="voicemode"`, `PULSE_PROP_media.name="voicemode-tts"`)
  - Clean user interruption handling mapping SIGTERM/SIGINT return codes into graceful KeyboardInterrupt
  - Opportunistic temporary file cleanup (purging `voice-tts-*` older than 30m)
  - Comprehensive unit test suite in `tests/test_tts_pipeline.py`
affects: [04-status-audio-visual-feedback]

actuals:
  tasks: 3
  commits: 1

tech-stack:
  added: [wl-clipboard, pipewire, ffplay]
  patterns: [primary-selection-capture, conservative-normalization, pipewire-env-tagging, clean-interruption-filtering, opportunistic-gc]

key-files:
  modified: [voice.py, tests/test_tts_pipeline.py]

key-decisions:
  - "Read Wayland primary selection via wl-paste --primary without touching standard clipboard or injecting synthetic copy keystrokes (per D-04, D-09)"
  - "Enforced 1.0s timeout on wl-paste calls catching TimeoutExpired cleanly to prevent hung clients from freezing the daemon (per D-05)"
  - "Implemented conservative text normalization pipeline converting URLs to domains, snake_case to words, path slashes to pauses, and stripping markdown (per D-07)"
  - "Enforced 5,000 character length limit upfront with desktop warning toast (per D-06)"
  - "Validated text and Kokoro model assets upfront in parent process before worker spawn or temp file creation (per D-08, D-15)"
  - "Provided distinct desktop toast feedback indicating whether text originated from selection or clipboard fallback (per D-12)"
  - "Tagged ffplay subprocess with PulseAudio/PipeWire properties for audio routing and volume identification (per D-17)"
  - "Filtered termination signal exit codes (-15, -2, 255, 143, 130) as clean interruptions with 'Speech stopped.' notification (per D-18, D-19)"
  - "Added cleanup_stale_tts_files to opportunistically purge temp WAV/MP3/TXT older than 30 minutes (per D-20)"

patterns-established:
  - "selected_or_clipboard_text: non-destructive primary selection reading with standard clipboard fallback"
  - "bound_tts_text: 5,000-character bounding with desktop toast notification"
  - "PipeWire environment tagging on headless media players"
  - "clean_interruption_filter: converting signal exit codes to KeyboardInterrupt"

requirements-completed: [TTS-02]

coverage:
  - id: D-04
    description: "Read Wayland primary selection via wl-paste --primary with clipboard fallback"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestWaylandSelectionCapture.test_primary_prioritized_over_clipboard"
        status: pass
    human_judgment: false
  - id: D-05
    description: "Enforce 1.0s timeout on wl-paste calls catching TimeoutExpired cleanly"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestWaylandSelectionCapture.test_timeout_on_unresponsive_wayland_client"
        status: pass
    human_judgment: false
  - id: D-06
    description: "Bound input text to 5,000 characters with desktop warning toast"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestTtsTextNormalization.test_length_bounding_and_warning_toast"
        status: pass
    human_judgment: false
  - id: D-07
    description: "Conservative text normalization pipeline for TTS"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestTtsTextNormalization"
        status: pass
    human_judgment: false
  - id: D-08
    description: "Upfront validation in parent process before worker spawn or temp file creation"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestTtsTextNormalization.test_empty_text_upfront_abort"
        status: pass
    human_judgment: false
  - id: D-09
    description: "Non-destructive selection reading without modifying regular clipboard or highlight"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestWaylandSelectionCapture"
        status: pass
    human_judgment: false
  - id: D-10
    description: "Support for piping standard input via --speak -"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestTtsTextNormalization.test_stdin_piping"
        status: pass
    human_judgment: false
  - id: D-11
    description: "Subtle low dual-tone chime on empty selection or error"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestWaylandSelectionCapture.test_empty_selection_error_chime_and_notification"
        status: pass
    human_judgment: false
  - id: D-12
    description: "Visual toast distinguishing primary selection vs clipboard fallback"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestWaylandSelectionCapture.test_toast_distinguishes_source"
        status: pass
    human_judgment: false
  - id: D-17
    description: "PipeWire stream identification on ffplay processes"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestAudioPlaybackAndInterruption.test_pipewire_stream_tagging"
        status: pass
    human_judgment: false
  - id: D-18
    description: "Stop active speech playback with brief Speech stopped notification"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestAudioPlaybackAndInterruption.test_stop_tts_terminates_process_group_and_notifies"
        status: pass
    human_judgment: false
  - id: D-19
    description: "Map SIGTERM/SIGINT signal exit codes to clean KeyboardInterrupt without error toasts"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestAudioPlaybackAndInterruption.test_clean_interruption_filter"
        status: pass
    human_judgment: false
  - id: D-20
    description: "Opportunistic garbage collection purging temporary TTS files older than 30 minutes"
    requirement: "TTS-02"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestAudioPlaybackAndInterruption.test_cleanup_stale_tts_files"
        status: pass
    human_judgment: false
---

# Plan 03-02 Summary: Wayland Primary Selection Capture, Text Normalization, and Headless Playback

Successfully implemented Wayland primary selection text capture, conservative text normalization, PipeWire stream identification, clean interruption handling, and opportunistic garbage collection.

## Key Accomplishments
1. **Wayland Primary Selection Capture**: Enhanced `read_x_selection` to query `wl-paste --primary` under Wayland with a strict 1.0s timeout (`subprocess.TimeoutExpired` safety). Implemented `selected_or_clipboard_text` prioritizing primary selection with fallback to standard clipboard without altering clipboard contents or on-screen highlights.
2. **Conservative Text Normalization**: Built `normalize_tts_text` stripping ANSI escape sequences, converting markdown links to anchor text, simplifying raw URLs to domains while preserving punctuation, converting `snake_case` tokens to readable words, removing markdown syntax, converting path slashes to pauses, inserting pauses for unpunctuated line breaks, and normalizing unicode quotes and dashes.
3. **Length Bounding & Upfront Validation**: Implemented `bound_tts_text` enforcing a 5,000-character ceiling with desktop warning toasts. Added upfront text and Kokoro asset validation in `start_tts_background` and `speak_selection`, aborting cleanly with an audible dual-tone error chime (`play_cue(args, "error")`) when input or assets are absent.
4. **PipeWire Stream Tagging**: Tagged `ffplay` audio streams using `PULSE_PROP_application.name="voicemode"` and `PULSE_PROP_media.name="voicemode-tts"`, enabling volume mixing and stream recognition.
5. **Clean Interruption & Toggle Behavior**: Filtered termination signal exit codes (-15, -2, 255, 143, 130) in `play_tts_audio` into clean `KeyboardInterrupt` exceptions, eliminating false error toasts when users press `Super+T` to stop playback.
6. **Opportunistic Garbage Collection**: Added `cleanup_stale_tts_files` to purge `voice-tts-*.wav`, `*.mp3`, and `*.txt` older than 30 minutes from `STATE_DIR` on startup, speech trigger, and stop.
7. **Comprehensive Automated Test Coverage**: Implemented unit test suites `TestTtsTextNormalization`, `TestWaylandSelectionCapture`, and `TestAudioPlaybackAndInterruption` in `tests/test_tts_pipeline.py`.

## Verification
- Unit test suite: `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_tts_pipeline.py` (27 tests passed).
- Repository regression test suite: `/home/pera/github_repo/Voice/.venv/bin/python -m unittest discover tests` (51 tests passed).
- Ruff linting check: `uv run ruff check tests/test_tts_pipeline.py` (All checks passed).

## Self-Check: PASSED
