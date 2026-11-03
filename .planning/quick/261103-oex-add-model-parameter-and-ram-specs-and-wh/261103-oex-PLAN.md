# Quick Plan: Add STT/TTS Model Specs and Whisper Update/Download Button

**Goal:**
1. Display model parameters, disk sizes, and required memory (RAM/VRAM) for STT (Whisper) models and TTS backends in both the Quickshell UI and CLI.
2. Provide concise size tags on model chips and an expanded model details card in the Quickshell Voice popup.
3. Provide a live "Check / Update Model" / "Download Model" button in the STT card of the Quickshell popup that downloads or verifies the selected Whisper model, with live status updates and confirmation.
4. Support the latest `large-v3-turbo` model in addition to existing models.
5. Ensure 100% synchronization between `integrations/quickshell/` and `/home/pera/github_repo/.dotfiles/`.

## Architecture & Design

### 1. Model Metadata Specification
Define a comprehensive, canonical model metadata table in `voice.py` and mirror in `VoicePopup.qml`:
- `tiny` / `tiny.en`: 39M params, ~75 MB disk, ~390 MB RAM
- `base` / `base.en`: 74M params, ~145 MB disk, ~500 MB RAM
- `small` / `small.en`: 244M params, ~480 MB disk, ~1.0 GB RAM
- `medium` / `medium.en`: 769M params, ~1.5 GB disk, ~2.6 GB RAM
- `large-v2` / `large-v3`: 1550M params, ~3.1 GB disk, ~4.7 GB RAM
- `large-v3-turbo`: 809M params, ~1.6 GB disk, ~2.8 GB RAM
- TTS `kokoro`: 82M params, 338 MB disk, ~500 MB RAM (local neural)
- TTS `edge`: Cloud API, 0 MB disk, 0 MB local RAM (cloud streaming)

### 2. Backend CLI Enhancements (`voice.py`)
- Add `--download-model MODEL`: Downloads and verifies a specific Faster-Whisper model into `~/.cache/huggingface/hub/` using `snapshot_download` or `WhisperModel(..., local_files_only=False)` and outputs human/json status.
- Add `--models-info` / `--list-models`: Outputs JSON or formatted table with parameters, disk size, RAM requirements, and local cache availability.
- Update `check_models_status()` to accurately recognize `large-v3-turbo` and other variants.

### 3. Quickshell UI Implementation (`VoicePopup.qml`)
- In `ConfigModelGridRow`:
  - Include `large-v3-turbo` in the STT model grid.
  - Enhance `OptionChip` (or provide `ModelOptionChip`) with concise parameter/size tags (e.g. `medium.en\n769M • 1.5G`).
  - Below the grid, add an **STT Model Details Card**:
    - Header: Selected model badge and name
    - Row 1: Parameters (e.g. `769M`), Disk Size (e.g. `~1.5 GB`), Required RAM/VRAM (e.g. `~2.6 GB`)
    - Row 2: Status indicator (`✓ Downloaded (Ready)` in green or `⚠ Not Downloaded` in amber)
    - Row 3: Action Button:
      - If cached: "Check / Update Model" (icon: `sync`)
      - If missing: "Download Model (~1.5 GB)" (icon: `cloud_download`)
      - During download: "Downloading & Verifying..." with spinning/pulsing animation (disabled while busy)
      - Invokes `Quickshell.Io.Process` running `[root.voiceBin, "--download-model", selectedModel]`
  - In Text-to-Speech (TTS) Card:
    - Display metadata for `kokoro` (82M params • 338 MB disk • ~0.5 GB RAM) vs `edge` (Cloud API • 0 MB RAM).
    - If Kokoro assets are missing, show "Download Kokoro Assets" button.

### 4. Dotfiles Parity
- Sync `integrations/quickshell/VoicePopup.qml` with `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePopup.qml`.

### 5. Verification
- Add automated pytest unit tests in `tests/test_model_specs.py` verifying `--models-info`, `--download-model`, and model metadata.
- Verify QML syntax and test with `uv run pytest`.
