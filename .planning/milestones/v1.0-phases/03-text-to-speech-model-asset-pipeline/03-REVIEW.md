---
phase: "03"
status: clean
files_reviewed: 3
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
---

# Code Review: Phase 03 — Text-to-Speech & Model Asset Pipeline

Reviewed all source and test files modified in Phase 03:
- `voice.py`
- `scripts/download-kokoro-assets.sh`
- `tests/test_tts_pipeline.py`

## Summary of Changes
1. **Offline Neural TTS Asset Pipeline**: Implemented canonical streaming downloader `voice.py --download-tts-assets` with atomic temporary file replacement and strict size guards (>300MB model, >20MB voices). Verified production assets in `models/kokoro/`.
2. **Speed Clamping & Safe Defaults**: Added `clamp_tts_speed` ensuring values stay within `[0.5, 2.0]`, preventing `kokoro-onnx` assertion crashes. Configured default voice `af_heart`, secondary `bm_george`, default speed `1.2x`, and `trim=False`.
3. **Strict Offline Privacy**: Guarded `synthesize_tts` against falling back to Microsoft Edge TTS when Kokoro models are absent. Missing models abort with user guidance, desktop notifications, and error cues.
4. **ONNX Instantiation Verification**: Enhanced `voice.py --tts-check` with complete ONNX session instantiation and voice inspection, returning exit code 0 on verified setup and 1 on incomplete/invalid setup.
5. **Wayland Primary Selection Capture**: Added 1.0s timeout to `wl-paste --primary` with graceful `subprocess.TimeoutExpired` handling, non-destructive clipboard fallback, and source-differentiated toasts.
6. **Conservative Text Normalization & Bounding**: Implemented `normalize_tts_text` stripping ANSI and markdown syntax, simplifying URLs to domains while preserving sentence punctuation, splitting snake_case, converting path slashes to pauses, and bounding text to 5,000 chars.
7. **PipeWire Integration & Interruption Filter**: Tagged audio streams via PulseAudio properties on `ffplay` and mapped termination signal exit codes (-15, -2, 255, 143, 130) to clean `KeyboardInterrupt` events.
8. **Opportunistic Temp File Cleanup**: Added `cleanup_stale_tts_files` to purge files older than 30 minutes.

## Review Assessment
- **Security & Privacy (ASVS L1)**: Strictly offline-first. No cloud fallback leak. Safe URL domain truncation without shell interpolation. Timeouts applied to Wayland IPC commands. Stale temporary files cleaned up.
- **Code Quality**: Functions follow single-responsibility patterns, robust exception handling, and full unit test coverage.
- **Verification**: 27 unit tests pass in `tests/test_tts_pipeline.py`. 51 total tests pass across the repository.

Status: **clean**
