---
phase: 03-text-to-speech-model-asset-pipeline
verified: 2026-09-19T02:50:00Z
status: passed
score: 7/7 must-haves verified
covered_files:
  - .planning/phases/03-text-to-speech-model-asset-pipeline/03-01-PLAN.md
  - .planning/phases/03-text-to-speech-model-asset-pipeline/03-01-SUMMARY.md
  - .planning/phases/03-text-to-speech-model-asset-pipeline/03-02-PLAN.md
  - .planning/phases/03-text-to-speech-model-asset-pipeline/03-02-SUMMARY.md
  - scripts/download-kokoro-assets.sh
  - tests/test_tts_pipeline.py
  - voice.py
covered_digest: "v1:sha256:fc9c413297884ed6f515d189ca9464e16352842e035f4300a199e2bcb07c3c8e"
behavior_unverified: 0
---

# Phase 03: Text-to-Speech & Model Asset Pipeline Verification Report

**Phase Goal:** Download and verify local Kokoro ONNX models and test primary selection reading with `ffplay` audio output.
**Verified:** 2026-09-19T02:50:00Z
**Status:** passed

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Kokoro model weights and voices download safely with size guards and verify via `voice.py --tts-check` | ✓ VERIFIED | `download_tts_assets` enforces size guards (>300MB model, >20MB voices) with atomic `.tmp` swap; `.venv/bin/python voice.py --tts-check` loads ONNX graph and validates 54 voices with exit code 0; `TestKokoroAssetManagement` passed |
| 2 | Offline-first privacy is strictly enforced with no silent cloud fallback | ✓ VERIFIED | `synthesize_tts` raises explicit error and prompts user to run `--download-tts-assets` when Kokoro assets are missing; does not fall back to `edge-tts`; `test_offline_first_guard_no_cloud_fallback` passed |
| 3 | TTS speech speed is clamped to `[0.5, 2.0]` with default voice `af_heart` and 1.2x speed | ✓ VERIFIED | `clamp_tts_speed` clamps bounds; default voice `af_heart`, secondary `bm_george`, default speed 1.2x, `trim=False`; `test_speed_clamping` and `test_default_voice_and_speed` passed |
| 4 | Wayland primary selection (`wl-paste --primary`) captures highlighted text without clipboard destruction | ✓ VERIFIED | `selected_or_clipboard_text` reads primary selection with 1.0s timeout and non-destructive clipboard fallback; `TestWaylandSelectionCapture` passed |
| 5 | Conservative text normalization cleans prose and code identifiers while bounding length to 5,000 chars | ✓ VERIFIED | `normalize_tts_text` strips ANSI escapes, flattens markdown links, summarizes URLs to domains with punctuation retention, splits snake_case, and adds path pauses; `bound_tts_text` limits to 5,000 chars with desktop warning; dual-tone error chime on invalid text; `TestTtsTextNormalization` passed |
| 6 | PipeWire stream properties identify voicemode playback in audio mixer tools | ✓ VERIFIED | `play_tts_audio` sets `PULSE_PROP_application.name="voicemode"` and `PULSE_PROP_media.name="voicemode-tts"` on `ffplay` subprocess; `test_pipewire_stream_properties_applied_to_ffplay` passed |
| 7 | `--stop-tts` and process interruption halt playback cleanly without false error toasts | ✓ VERIFIED | `play_tts_audio` filters SIGTERM/SIGINT exit codes into `KeyboardInterrupt`; `stop_tts_background` terminates worker group; opportunistic GC purges temp files >30m old; `--speak -` supports stdin piping; `TestAudioPlaybackAndInterruption` passed |

**Score:** 7/7 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `voice.py` | Complete Kokoro asset pipeline, normalization, selection capture, and headless playback | ✓ EXISTS + SUBSTANTIVE | Contains `download_tts_assets`, `kokoro_voice_names`, `print_tts_check`, `clamp_tts_speed`, `selected_or_clipboard_text`, `normalize_tts_text`, `bound_tts_text`, `cleanup_stale_tts_files`, `play_tts_audio`, and `speak_selection` |
| `scripts/download-kokoro-assets.sh` | Shell asset download helper | ✓ EXISTS + SUBSTANTIVE | Delegates to venv Python downloader with curl/wget fallback |
| `tests/test_tts_pipeline.py` | Comprehensive TTS unit and integration test suite | ✓ EXISTS + SUBSTANTIVE | 27 automated tests covering asset management, text normalization, Wayland selection, and audio playback interruption |
| `models/kokoro/` | Production Kokoro ONNX model weights and voice vectors | ✓ EXISTS + SUBSTANTIVE | `kokoro-v1.0.onnx` (325MB) and `voices-v1.0.bin` (28MB, 54 voices) verified and locally cached |

**Artifacts:** 4/4 verified

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `voice.py:main` | `voice.py:download_tts_assets` | CLI dispatch | ✓ WIRED | Line 1690: `--download-tts-assets` triggers streaming download with size guards |
| `voice.py:main` | `voice.py:print_tts_check` | CLI dispatch | ✓ WIRED | Line 1693: `--tts-check` verifies model graph and returns exit code 0/1 |
| `voice.py:speak_selection` | `voice.py:selected_or_clipboard_text` | Function call | ✓ WIRED | Line 1221: captures primary selection with 1.0s timeout before background spawn |
| `voice.py:start_tts_background` | `voice.py:bound_tts_text` | Function call | ✓ WIRED | Line 1060: enforces 5,000 char maximum length with warning notification |
| `voice.py:run_tts_background` | `voice.py:normalize_tts_text` | Function call | ✓ WIRED | Line 1104: normalizes prose, URLs, markdown, and code identifiers before synthesis |
| `voice.py:run_tts_background` | `voice.py:synthesize_tts` | Function call | ✓ WIRED | Line 1114: synthesizes audio using offline Kokoro ONNX pipeline |
| `voice.py:run_tts_background` | `voice.py:play_tts_audio` | Function call | ✓ WIRED | Line 1117: plays audio via headless `ffplay` with PipeWire stream tags |
| `voice.py:stop_tts_background` | worker process group | POSIX signal | ✓ WIRED | Line 1047: `os.killpg(pid, signal.SIGTERM)` terminates active playback |

**Wiring:** 8/8 connections verified

## Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| **TTS-01**: Download and verify Kokoro ONNX model weights (`kokoro-v1.0.onnx`) and voice vectors (`voices-v1.0.bin`) in `models/kokoro/` | ✓ SATISFIED | None |
| **TTS-02**: Verify Wayland primary selection text capture (`wl-paste --primary`) and audio output playback via `ffplay` | ✓ SATISFIED | None |

**Coverage:** 2/2 requirements satisfied

## Anti-Patterns Found

None found. No stubs, no blocking issues, no untracked dependencies, and no unbounded subprocess calls.

## Human Verification Required

None — all observable truths, asset integrity, text normalizations, Wayland primary selection capture, PipeWire properties, and interruption signals are covered by 27 automated unit/integration tests and confirmed via live `.venv/bin/python voice.py --tts-check`.

## Gaps Summary

**No gaps found.** Phase goal achieved. Ready to proceed to Phase 4.

## Verification Metadata

**Verification approach:** Goal-backward (derived from phase goal and requirements)  
**Must-haves source:** ROADMAP.md and 03-VALIDATION.md  
**Automated checks:** 27 passed in `test_tts_pipeline.py` (51 total in project), 0 failed  
**Human checks required:** 0  
**Total verification time:** 2 min  

---
*Verified: 2026-09-19T02:50:00Z*  
*Verifier: Antigravity*
