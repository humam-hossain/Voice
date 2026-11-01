# Quickshell Voice Integration

This directory contains vendored reference copies of the Quickshell integration components for the `voicemode` speech-to-text dictation and text-to-speech system on Arch Linux / Hyprland.

> [!IMPORTANT]
> **Authoritative Source Hierarchy:**
> The live dotfiles repository at `/home/pera/github_repo/.dotfiles/restow/quickshell/` (symlinked via GNU Stow into `~/.config/quickshell/`) is the **authoritative source** for these components.
> The files in this directory (`integrations/quickshell/`) are vendored reference copies maintained for version tracking, reproducibility, and upstream distribution.

---

## Architecture Overview

The integration consists of two decoupled QML components:

```
┌────────────────────────────────────────────────────────┐
│                   voice.py Backend                     │
│  (STT Recorder, Whisper Inference, Text Injection)     │
└────────────┬─────────────────────────────┬─────────────┘
             │ writes status.json & PID     │ generates report.html
             ▼                             ▼
┌────────────────────────────────────────────────────────┐
│  Voice.qml (Quickshell Service Singleton)              │
│  - FileView observers for status.json & PID locks      │
│  - Ingests telemetry & computes multi-bar timers       │
│  - Exposes openReport() launcher with path validation  │
└────────────────────────────┬───────────────────────────┘
                             │ reactive property bindings
                             ▼
┌────────────────────────────────────────────────────────┐
│  VoicePill.qml (Quickshell Bar Pill Component)         │
│  - Dual progress timer during recording                │
│  - 3-bar progress timer during tail decode & typing    │
│  - Sky Blue (#38bdf8) & Neon Green (#4ade80) styling   │
│  - Breathing pulse during concurrent chunk decode      │
│  - Glyph shifts: graphic_eq -> edit (pen) for typing   │
│  - Tabular numeral font features (jitter-free layout)  │
│  - Click-through to view latency report.html           │
└────────────────────────────────────────────────────────┘
```

### 1. `Voice.qml` (Service Singleton)
- **Location in dotfiles:** `restow/quickshell/.config/quickshell/ii/services/Voice.qml`
- **Location in system:** `~/.config/quickshell/ii/services/Voice.qml`
- **Role:** Non-visual service singleton. Continuously observes filesystem state files in `$XDG_RUNTIME_DIR/voice-stt/` using Quickshell's event-driven `FileView` and a 2500ms idle / 100ms active poll fallback.
- **Computed Timers:**
  - `formattedRecordedDuration`: Time audio was actively captured. Frozen when recording stops.
  - `formattedTranscribedDuration`: Decoded audio duration (`transcribed_audio_s`), progressing incrementally during concurrent chunk decode and tail decode.
  - `formattedTotalDuration`: Total wall-clock elapsed time from dictation start through typing completion.

### 2. `VoicePill.qml` (Bar Pill Component)
- **Location in dotfiles:** `restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml`
- **Location in system:** `~/.config/quickshell/ii/modules/ii/bar/VoicePill.qml`
- **Role:** Visual bar pill rendered on the Hyprland desktop status bar.
- **Visual States & Styling:**
  - **Recording (Capturing only):** `colPrimary` color, `graphic_eq` glyph, 2-bar timer (`recorded | transcribed`).
  - **Recording (Concurrent Decode):** Smooth breathing color pulse alternating between `colPrimary` and Sky Blue (`#38bdf8`) with 600ms easing.
  - **Transcribing (Tail Decode):** Dedicated Sky Blue (`#38bdf8`) across icon and text, `graphic_eq` glyph, 3-bar progress timer (`recorded | transcribed | total`).
  - **Typing / Text Insertion:** Dedicated Neon Green (`#4ade80`) across icon and text, `edit` Material Symbol glyph (pen icon), retaining the 3-bar progress timer.
  - **Wrap-up (1.5s linger):** Retains Neon Green styling and final 3-bar timer before smooth collapse to idle.
  - **Speaking (TTS):** `colSecondary` color, `graphic_eq` glyph, single elapsed timer.

---

## IPC and Telemetry Contract

Communication between `voice.py` and Quickshell occurs via atomic filesystem state in `$XDG_RUNTIME_DIR/voice-stt/` (default: `/run/user/1000/voice-stt/`).

### State Files
| File | Role | Format |
|---|---|---|
| `recorder.pid` | STT worker process lock | `<pid> [state]` (`recording`, `transcribing`, `typing`) |
| `tts.pid` | TTS worker process lock | `<pid>` |
| `status.json` | Real-time telemetry snapshot | Atomic JSON validated against `STATUS_V1_KEYS` |
| `report.html` | Pre-rendered latency report | Self-contained HTML report with accuracy metrics |

### `status.json` Schema (v1)
All snapshots adhere strictly to `STATUS_V1_KEYS` without unknown keys:
```json
{
  "schema": 1,
  "pid": 12345,
  "run_id": "20261101_140000_12345",
  "state": "transcribing",
  "phase": "decode",
  "started_at": 1730469600.123,
  "updated_at": 1730469605.456,
  "expires_at": 1730469635.456,
  "audio_s": 6.5,
  "segments": 2,
  "segments_done": 2,
  "transcribed_audio_s": 6.5,
  "report_path": "/run/user/1000/voice-stt/report.html"
}
```

### Output Method Recommendation
- **Recommended Default:** `--output-method paste` (or `--paste`). Fast clipboard insertion finishes in ~20ms, eliminating slow letter-by-letter typing delays while `typingLingerTimer` (1000ms) and `wrapUpTimer` (1500ms) preserve the visual Neon Green typing indicator and pen glyph on the bar.

### Report Click-Through Security
Clicking the pill during `transcribing`, `typing`, or `wrapup` triggers `Voice.openReport()`.
- Validates that `target.startsWith(runtimeDir)` and `target.endsWith("report.html")`.
- Rejects path traversals (`../`) or external schemes (`http://`, `file:///etc/`).
- Dispatches via `Qt.openUrlExternally("file://" + target)` with fallback to `Quickshell.execDetached(["xdg-open", target])`.

---

## Synchronization Workflow

When making modifications to the Quickshell integration:

1. **Edit in Dotfiles:**
   Always modify the authoritative files in the dotfiles repository:
   - `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml`
   - `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml`

2. **Test Live Desktop:**
   Reload Quickshell to verify visual appearance and interactions:
   ```bash
   qs -c ii
   ```

3. **Mirror to Vendored Copies:**
   Copy the updated files into the Voice repository:
   ```bash
   cp /home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml integrations/quickshell/Voice.qml
   cp /home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml integrations/quickshell/VoicePill.qml
   ```

4. **Verify Parity & Test Suite:**
   Confirm zero divergence and run automated simulation tests:
   ```bash
   diff -u /home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml integrations/quickshell/Voice.qml
   diff -u /home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml integrations/quickshell/VoicePill.qml
   uv run pytest tests/test_pill_integration_simulation.py -x
   ```
