# Debug Session: Missing Status Pill Live Transcription & Dual-Timer Progress

**Discovered:** During Phase 07 UAT Test 7
**Status:** Root Cause Found

---

## Symptoms
1. When push-to-talk recording runs on Hyprland, the desktop bar pill does not show any ETA countdown or parallel transcription progress.
2. The user sees only the legacy recording duration timer.
3. Desired behavior requested by user:
   - While recording audio, parallel chunk transcription progress must be visible.
   - Dual clock display: `X:XX | X:XX` (first: audio recording time | second: audio transcribed to text so far).
   - During transcription after release: remaining ETA countdown (`~2s`, `1s`, `Finishing…`) displayed in the pill.

---

## Investigation Findings

### 1. Quickshell Desktop UI (`Voice.qml` & `VoicePill.qml`)
- **File:** `~/.config/quickshell/ii/services/Voice.qml`
  - Currently only monitors `$XDG_RUNTIME_DIR/voice-stt/recorder.pid` and `tts.pid`.
  - Never parses or reads `$XDG_RUNTIME_DIR/voice-stt/status.json`.
  - Exposes only a single `formattedDuration` timer computed from process start time.
- **File:** `~/.config/quickshell/ii/modules/ii/bar/VoicePill.qml`
  - `displayText` has static branches:
    - `"recording"`: returns `Voice.formattedDuration`
    - `"transcribing"`: hardcoded to `Translation.tr("Transcribing...")`
  - Completely unaware of `eta_remaining_s`, `transcribed_audio_s`, or dual timers.

### 2. Status Contract & Worker Publishing (`voice.py` & `voicemode_telemetry.py`)
- **File:** `voicemode_telemetry.py`
  - `STATUS_V1_KEYS` has `audio_s`, `segments`, `segments_done`, `eta_remaining_s`, but lacks an explicit `transcribed_audio_s` field representing total duration of audio chunks already transcribed to text.
- **File:** `voice.py`
  - In `worker_consumer()` (lines 2484-2489), `_publish_status("transcribing", "decode", ...)` is only published when `capture_closed.is_set()` (after recording stops).
  - While recording is active and chunks finish transcribing in parallel, status is never published to update `transcribed_audio_s` or `segments_done`.

---

## Root Cause
1. **Producer Side (`voice.py`, `voicemode_telemetry.py`):**
   - Live parallel transcription progress (`transcribed_audio_s` / `segments_done`) is not published to `status.json` while `recording` is still actively streaming audio chunks.
   - `STATUS_V1_KEYS` does not formalize `transcribed_audio_s`.
2. **Consumer Side (`Voice.qml`, `VoicePill.qml`):**
   - Quickshell `Voice.qml` does not parse `$XDG_RUNTIME_DIR/voice-stt/status.json`.
   - `VoicePill.qml` only displays `Voice.formattedDuration` and static `"Transcribing..."`, lacking dual-timer formatting (`X:XX | X:XX`) during recording and ETA pill formatting during transcribing.

---

## Suggested Fix Direction
1. In `voicemode_telemetry.py`: Add `transcribed_audio_s` to `STATUS_V1_KEYS` and status builder.
2. In `voice.py`: In `worker_consumer()`, publish updated `transcribed_audio_s` and `segments_done` to `status.json` whenever a chunk finishes decoding during active recording.
3. In `Voice.qml`: Add a `FileView` observer for `status.json` (or read via poll) to parse `transcribed_audio_s`, `eta_remaining_s`, `eta_source`, and `overrun`.
4. In `VoicePill.qml`: Format `displayText` as `X:XX | X:XX` during recording when parallel transcription is active, and show the ETA countdown pill (`~Xs` / `Finishing…`) during `transcribing`.
