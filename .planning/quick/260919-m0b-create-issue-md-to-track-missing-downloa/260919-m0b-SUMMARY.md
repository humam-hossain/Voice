---
id: "260919-m0b"
slug: "create-issue-md-to-track-missing-downloa"
status: complete
date: "2026-09-19"
description: "Create issue.md to track missing download progress bar"
---

# Quick Task Summary: Create issue.md to track missing download progress bar

## Accomplishments

1. **Created `issue.md`**:
   - Documented the missing progress bar / transfer status issue when fetching Faster-Whisper models (e.g. `medium.en`) via `voice --allow-download`.
   - Recorded the exact warning message regarding unauthenticated HF Hub requests.
   - Identified root cause in `load_model` (direct Faster-Whisper instantiation without explicit `huggingface_hub` progress hooks, contrasting with Kokoro's custom `download_file_with_progress`).
   - Outlined 3 viable remediation paths for future implementation.
