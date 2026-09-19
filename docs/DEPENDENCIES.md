# Dependency and License Notes

This document tracks external system packages, Python libraries, model assets, and licensing status for **voicemode** on Arch Linux and Wayland.

The repository source code is licensed under the **MIT License**. Third-party packages, neural model weights, and system utilities retain their respective upstream licenses.

---

## Arch Linux System Packages

### `dots-hyprland` Environments (Default)

In Arch Linux systems running `dots-hyprland`, the base Wayland clipboard utilities, desktop notification daemons, PipeWire sound server, and WirePlumber session manager are pre-installed. Only **two essential packages** need to be installed:

```bash
sudo pacman -S wtype ffmpeg
```

- **`wtype`:** Injects synthetic keystrokes into focused Wayland windows via the `zwp_virtual_keyboard_v1` protocol without root permissions.
- **`ffmpeg` (with `ffplay`):** Provides low-latency, headless audio playback for synthesized speech output.

### Vanilla Arch Linux (Fresh Setup)

For a vanilla Arch Linux installation or minimal window manager setup, install the complete audio, input, and notification stack:

```bash
sudo pacman -S wtype ffmpeg wl-clipboard libnotify pipewire wireplumber
```

### System Utilities Breakdown

| Utility / Binary | Arch Package | Role | Execution Privileges | License |
|---|---|---|---|---|
| `wtype` | `wtype` | Wayland keystroke injection (active window typing) | Rootless / Unprivileged (`zwp_virtual_keyboard_v1`) | MIT |
| `ffplay` | `ffmpeg` | Headless audio playback of synthesized WAV/MP3 | Rootless / Unprivileged | LGPLv2.1+ / GPLv2+ |
| `wl-copy` / `wl-paste` | `wl-clipboard` | Primary selection capture and clipboard management | Rootless / Unprivileged | GPLv3+ |
| `wpctl` | `wireplumber` | Audio volume inspection and mute state monitoring | Rootless / Unprivileged | LGPLv2.1+ |
| `hyprctl` | `hyprland` | Dynamic compositor active window interrogation | Rootless / Unprivileged | BSD-3-Clause |
| `notify-send` | `libnotify` | Focus-safe desktop status alerts and warnings | Rootless / Unprivileged | LGPLv2.1+ |
| `ydotool` *(optional)* | `ydotool` | Secondary fallback typing backend | Optional (requires root `ydotoold` daemon) | AGPLv3 |

---

## Python Libraries (Virtual Environment via `uv`)

All Python packages are installed inside an isolated Python 3.12 virtual environment (`.venv/`):

| Package | Purpose in voicemode | License Status |
|---|---|---|
| `faster-whisper` (>=1.2.1) | Local Whisper speech-to-text inference | MIT |
| `ctranslate2` | Accelerated C++ inference runtime backing Whisper | MIT |
| `kokoro-onnx` (==0.5.0) | Local neural text-to-speech acoustic synthesis | MIT package metadata (pulls `phonemizer-fork` GPLv3+) |
| `onnxruntime` | Accelerated neural network inference runtime | MIT |
| `sounddevice` (>=0.5.0) | Asynchronous mono microphone audio capture stream | MIT |
| `numpy` (>=2.0.2) | PCM audio buffer manipulation & sine tone synthesis | BSD-3-Clause |
| `soundfile` (>=0.14.0) | WAV file export for synthesized speech | BSD-3-Clause |
| `edge-tts` (>=7.2.7) | Optional online Microsoft Edge TTS client | LGPLv3 (service terms separate) |
| `PyYAML` (>=6.0) | Optional configuration parser | MIT |

---

## Offline Neural Model Assets

All neural models operate 100% locally with zero external telemetry.

### 1. Faster-Whisper (`Systran/faster-whisper-small.en`)

- **Format:** CTranslate2 model weights (`int8` quantized).
- **Disk Footprint:** ~480 MB.
- **Location:** `~/.cache/huggingface/hub/models--Systran--faster-whisper-small.en/`
- **License:** Apache 2.0 / MIT.
- **Acquisition:** Automatically cached by `voice --check --allow-download` or during first transcription.

### 2. Kokoro-v1.0 TTS (`hexgrad/Kokoro-82M`)

- **Format:** ONNX acoustic model (`kokoro-v1.0.onnx`) and voice vectors (`voices-v1.0.bin`).
- **Disk Footprint:**
  - `kokoro-v1.0.onnx`: ~311 MB
  - `voices-v1.0.bin`: ~27 MB
- **Location:** `models/kokoro/` (local working tree or system path).
- **License:** Apache 2.0.
- **Acquisition:**
  ```bash
  scripts/download-kokoro-assets.sh
  ```

---

## Licensing Caveats

1. **`kokoro-onnx` Phonemizer Chain:** The `kokoro-onnx==0.5.0` package relies on `phonemizer-fork`, which is licensed under GPLv3+. This is fully suitable for personal, local developer workstation use on Arch Linux. If redistributing commercial binary distributions, evaluate replacing this phonemizer path with a purely permissive alternative.
2. **Microsoft Edge TTS Backend:** The `edge-tts` package is optional. When enabled (`--tts-backend edge`), audio is synthesized via Microsoft's cloud endpoints. The default configuration uses the offline Kokoro ONNX model to maintain complete data privacy.
