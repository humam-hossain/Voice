---
phase: 03-text-to-speech-model-asset-pipeline
plan: "01"
subsystem: text-to-speech
tags: [kokoro, onnx, tts, assets, download, speed-clamping, offline-first, privacy, verification]

requires:
  - phase: 01-environment-audio-subsystem
    provides: Python 3.12 environment and audio capture/cue foundation
  - phase: 02-wayland-keystroke-injection
    provides: Wayland environment integration
provides:
  - Streaming Kokoro ONNX model and voice weights downloader with atomic replacement (voice.py --download-tts-assets)
  - Size guard enforcement (>300MB model, >20MB voices) with automatic corrupt download pruning
  - Clamped speech speed [0.5, 2.0] preventing ONNX runtime assertions
  - Verified default voice parameters (af_heart, bm_george secondary, 1.2x default speed, trim=False)
  - Strict offline-first privacy enforcement (no fallback to cloud Edge TTS when Kokoro assets are absent)
  - Full ONNX model instantiation and voice inspection in voice.py --tts-check with exit code contract (0 on success, 1 on failure)
  - Shell helper delegation in scripts/download-kokoro-assets.sh
  - Unit test suite harness in tests/test_tts_pipeline.py
affects: [03-02]

actuals:
  tasks: 3
  commits: 1

tech-stack:
  added: [kokoro-onnx, soundfile]
  patterns: [streaming-download-progress, atomic-file-replacement, fast-size-guards, offline-first-privacy]

key-files:
  created: [tests/test_tts_pipeline.py, models/kokoro/kokoro-v1.0.onnx, models/kokoro/voices-v1.0.bin]
  modified: [voice.py, scripts/download-kokoro-assets.sh]

key-decisions:
  - "Defaulted Kokoro voice to af_heart with secondary bm_george and speed 1.2x (per D-13, D-14)"
  - "Enforced speed clamping to [0.5, 2.0] before Kokoro inference to prevent unhandled assertion crashes (per D-14)"
  - "Implemented chunked streaming with atomic .tmp replacement and size guards (>300MB model, >20MB voices) (per D-02, D-03)"
  - "Strictly forbade automatic cloud Edge TTS fallback when Kokoro assets are missing, requiring explicit user download (per D-15)"
  - "Contracted --tts-check to instantiate Kokoro ONNX model and return exit code 1 if missing/invalid, 0 when verified (per D-03)"
  - "Updated scripts/download-kokoro-assets.sh to delegate to canonical Python downloader with standalone curl/wget fallback (per D-02)"

patterns-established:
  - "download_file_with_progress: safe streaming with percentage, speed, size guard, and atomic rename"
  - "clamp_tts_speed: bounding speech speed to kokoro-onnx internal range [0.5, 2.0]"
  - "Offline privacy guard: early check in synthesize_tts before any network or cloud action"

requirements-completed: [TTS-01]

coverage:
  - id: D-01
    description: "Local model directory models/kokoro/ with kokoro-v1.0.onnx and voices-v1.0.bin"
    requirement: "TTS-01"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestKokoroAssetManagement"
        status: pass
    human_judgment: false
  - id: D-02
    description: "Streaming downloader with progress reporting and atomic temporary file rename"
    requirement: "TTS-01"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestKokoroAssetManagement.test_download_asset_streaming_and_atomic_replace"
        status: pass
    human_judgment: false
  - id: D-03
    description: "Fast size guards (>300MB model, >20MB voices) and full ONNX instantiation in --tts-check returning exit code 0/1"
    requirement: "TTS-01"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestKokoroAssetManagement.test_print_tts_check_exit_code_contract"
        status: pass
    human_judgment: false
  - id: D-13
    description: "Default voice af_heart and secondary voice bm_george"
    requirement: "TTS-01"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestKokoroAssetManagement.test_default_voice_and_speed"
        status: pass
    human_judgment: false
  - id: D-14
    description: "Default speed 1.2x and clamping to [0.5, 2.0]"
    requirement: "TTS-01"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestKokoroAssetManagement.test_speed_clamping"
        status: pass
    human_judgment: false
  - id: D-15
    description: "Strict offline-first privacy with no automatic fallback to cloud Edge TTS"
    requirement: "TTS-01"
    verification:
      - kind: automated
        ref: "tests/test_tts_pipeline.py#TestKokoroAssetManagement.test_offline_first_guard_no_cloud_fallback"
        status: pass
    human_judgment: false
---

# Plan 03-01 Summary: Kokoro ONNX Model Asset Management & Verification Pipeline

Successfully implemented the offline neural Text-to-Speech (TTS) asset management and verification pipeline for voicemode on Arch Linux.

## Key Accomplishments
1. **Canonical Python Streaming Downloader**: Implemented `voice.py --download-tts-assets` using chunked streaming (128 KiB chunks) with real-time transfer rate reporting, size guard validation (>300,000,000 bytes for model, >20,000,000 bytes for voices), and atomic replacement via temporary files. Downloaded production assets into `models/kokoro/` (`kokoro-v1.0.onnx`: 325.5 MB, `voices-v1.0.bin`: 28.2 MB).
2. **Speed Clamping & Defaults**: Added `clamp_tts_speed` ensuring speech rates remain within `[0.5, 2.0]`. Set default voice to `af_heart`, secondary to `bm_george`, default speed to `1.2x`, and `kokoro_trim` to `False`.
3. **Strict Offline-First Privacy**: Updated `synthesize_tts` and `synthesize_kokoro_tts` to forbid silent cloud fallback to Microsoft Edge TTS when Kokoro models are absent. Missing assets trigger a desktop notification, console guidance, and an error cue chime.
4. **Full ONNX Verification Contract**: Enhanced `voice.py --tts-check` to verify asset file presence, check size guards, instantiate `kokoro_onnx.Kokoro`, and inspect available voice vectors, returning exit code 0 on verified setup and 1 on missing/incomplete assets.
5. **Shell Wrapper Integration**: Updated `scripts/download-kokoro-assets.sh` to delegate to `voice.py --download-tts-assets` using the virtual environment Python, with curl/wget fallback.
6. **Wave 0 Test Harness**: Created `tests/test_tts_pipeline.py` covering asset streaming, atomic replacement, size guard failure cleanup, speed clamping, privacy guards, and `--tts-check` return code contracts.

## Verification
- Automated unit test suite: `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_tts_pipeline.py` (9 tests passed).
- Kokoro on-disk asset assertions: `kokoro-v1.0.onnx` >= 300MB, `voices-v1.0.bin` >= 20MB (Passed).
- System verification: `/home/pera/github_repo/Voice/.venv/bin/python voice.py --tts-check` returned exit code 0 (`kokoro status: verified (54 voices loaded)`).

## Self-Check: PASSED
