# Issues & Future Improvements

## Issue 1: Missing Download Progress Bar for Faster-Whisper Models

- **Status:** Open / Deferred (to be resolved in a future update)
- **Reported:** 2026-09-19
- **Scope:** Speech-to-Text (Whisper Model Downloader / `load_model`)

### Symptoms
When downloading speech recognition models on demand via:
```bash
voice --model medium.en --check --allow-download
```
the terminal displays:
```text
Loading faster-whisper 'medium.en' on cpu (int8)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
```
After this warning, there is no progress bar, percentage indicator, download speed, or byte counter shown while files are being fetched from Hugging Face Hub.

### Impact
- Larger models like `medium.en` (~1.5 GB) or `large-v3` (~3 GB) take several minutes depending on network bandwidth.
- Without a visual progress indicator or spinner, the process appears completely frozen or unresponsive to the user.

### Root Cause
In `voice.py` (`load_model`), the application initializes `faster_whisper.WhisperModel(model_size_or_path, ...)` directly. Faster-Whisper delegates model resolution and asset fetching internally to `huggingface_hub` without enabling standard terminal progress hooks (such as `tqdm` or `hf_hub_download` progress callbacks). In contrast, Kokoro TTS assets use a dedicated helper (`download_file_with_progress`) with custom progress reporting.

### Proposed Solutions (for Future Fix)
1. **Explicit Pre-download Wrapper:**
   Use `huggingface_hub.snapshot_download` with visible progress tracking (`tqdm` / stdout progress callback) to pre-download the model snapshot into HuggingFace cache or a designated `models/whisper/` directory before initializing `WhisperModel`.
2. **Environment & Progress Hook Configuration:**
   Ensure `HF_HUB_ENABLE_HF_TRANSFER=0` and verify that `tqdm` or standard Hugging Face Hub download progress logging is not silenced or suppressed in headless/non-interactive detection.
3. **Authentication Notice:**
   Gracefully manage or soften the unauthenticated HF Hub warning, optionally providing a clean hint on configuring `HF_TOKEN` if desired for high-bandwidth downloads.
