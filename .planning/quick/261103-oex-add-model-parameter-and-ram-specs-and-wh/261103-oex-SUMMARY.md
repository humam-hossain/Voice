---
quick_id: 261103-oex
slug: add-model-parameter-and-ram-specs-and-wh
title: Add model parameter and RAM specs and Whisper model update/download button
status: complete
date: 2026-11-03
tags: [stt, tts, quickshell, whisper, models]
---

# Quick Task Summary: Add STT/TTS Model Specs and Whisper Update/Download Button

**Goal:**
- Expose model parameters, download/disk size, and required RAM/VRAM across all supported STT (Whisper) models and TTS backends in both CLI and Quickshell desktop popup.
- Provide concise parameter tags on model chips and an expanded model details card in `VoicePopup.qml`.
- Add an asynchronous "Download Model" / "Check / Update Model" button in `VoicePopup.qml` with live status feedback.
- Support `large-v3-turbo` in the STT model selector.
- Preserve 100% byte-for-byte parity with `/home/pera/github_repo/.dotfiles`.

## Deliverables

1. **Model Metadata Specifications in `voice.py`:**
   - Added canonical dictionaries `WHISPER_MODELS_METADATA` and `TTS_BACKENDS_METADATA` specifying:
     - `tiny`, `tiny.en` (39M params, ~75 MB disk, ~390 MB RAM)
     - `base`, `base.en` (74M params, ~145 MB disk, ~500 MB RAM)
     - `small`, `small.en` (244M params, ~480 MB disk, ~1.0 GB RAM)
     - `medium`, `medium.en` (769M params, ~1.5 GB disk, ~2.6 GB RAM)
     - `large-v2`, `large-v3` (1550M params, ~3.1 GB disk, ~4.7 GB RAM)
     - `large-v3-turbo` (809M params, ~1.6 GB disk, ~2.8 GB RAM)
     - `kokoro` (82M params, 338 MB disk, ~500 MB RAM)
     - `edge` (Cloud API, 0 MB disk, 0 MB local RAM)
   - Added helper functions:
     - `is_whisper_model_cached(model_name)`: Accurately checks Hugging Face cache directories.
     - `get_models_metadata()`: Returns structured data with cache status.
     - `download_whisper_model(model_name, args)`: Downloads and verifies Faster-Whisper models.
     - `print_models_info(args)`: Outputs human-readable table or structured JSON.
   - Added CLI arguments:
     - `--download-model [MODEL]`: Direct download/update of any Whisper model.
     - `--models-info`: Display table or JSON (`--json`) of all models and status.

2. **Quickshell UI Updates (`VoicePopup.qml`):**
   - Added `ModelOptionChip` displaying the model name and concise parameter tag (`39M`, `244M`, `769M`, `1.55B`, `809M`).
   - Added `large-v3-turbo` to the STT model selection grid.
   - Added `modelInfoBox` in the STT card:
     - Displays selected model name, parameters, download size, RAM requirements, and cache status badge (`Ready (Cached)` vs `Not Cached`).
     - Added dynamic action button: "Download Model (~1.5 GB)" if missing, or "Check / Update Model" if cached.
     - Dispatches background download via `Quickshell.Io.Process` without blocking the UI, displaying live status and completion confirmation.
   - Added `ttsDetailsBox` in the TTS card:
     - Displays parameters, disk size, and memory usage for Kokoro vs Microsoft Edge.
   - Synchronized 1:1 with `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePopup.qml`.

3. **Automated Testing:**
   - Added `tests/test_model_specs.py` covering all metadata entries, caching queries, JSON/text CLI output, download routines, and dotfiles parity.
   - 297/297 unit tests passed across the entire project suite.
