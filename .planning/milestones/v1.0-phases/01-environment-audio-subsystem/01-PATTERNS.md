# Phase 1: Environment & Audio Subsystem - Pattern Map

**Generated:** 2026-09-18  
**Status:** Ready for planning  
**Domain:** Python 3.12 Runtime, UV Packaging, PortAudio/PipeWire Audio Streaming, Faster-Whisper CPU Optimization  

---

## 1. Overview & File Catalog

This document defines the architectural patterns, concrete analogs, and code patterns to copy when implementing Phase 1. Downstream planners and executors must adhere to these established patterns to maintain codebase consistency.

### Target Files to Create / Modify

| File Path | Action | Role | Closest Analog |
|---|---|---|---|
| `~/.local/bin/voicemode` | Create | Desktop execution wrapper & launcher | [`scripts/download-kokoro-assets.sh`](file:///home/pera/github_repo/Voice/scripts/download-kokoro-assets.sh) |
| `~/.local/bin/voice` | Create (Symlink) | Convenience symlink to `voicemode` | N/A (Filesystem symlink) |
| `voice.py` | Modify | Core STT/TTS runtime, audio streaming, cue engine | [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) (Self) |
| `pyproject.toml` | Modify | Package dependencies, metadata, and extras | [`pyproject.toml`](file:///home/pera/github_repo/Voice/pyproject.toml) (Self) |
| `.venv/` | Recreate | Isolated Python 3.12 virtualenv via `uv` | System `uv` virtualenv pattern |

---

## 2. File Pattern Mappings

### 2.1. Desktop Launcher Script (`~/.local/bin/voicemode`)

#### Role & Data Flow
Desktop environment wrapper invoked directly by Hyprland hotkeys (`$mainMod+B`, `$mainMod+T`) or terminal users without activating `.venv`.
- **Inflow:** CLI flags (`$@`) and user session environment variables.
- **Processing:** Injects PipeWire client identification variables into the environment, verifies the Python 3.12 interpreter exists in `.venv`, and replaces the shell process via `exec`.
- **Outflow:** Execution of `voice.py` under the project-local `.venv`.

#### Closest Analog
[`scripts/download-kokoro-assets.sh`](file:///home/pera/github_repo/Voice/scripts/download-kokoro-assets.sh#L1-L16)
Existing pattern: Bash script with `set -euo pipefail`, explicit repository root path resolution, and error reporting to stderr.

```bash
# Existing analog pattern from scripts/download-kokoro-assets.sh:1-5
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
```

#### Pattern to Implement (`~/.local/bin/voicemode`)
```bash
#!/usr/bin/env bash
# voicemode launcher - Arch Linux / Hyprland
set -euo pipefail

REPO_DIR="/home/pera/github_repo/Voice"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
VOICE_SCRIPT="${REPO_DIR}/voice.py"

# Enforce PipeWire and PulseAudio client node labeling (D-11)
export PULSE_PROP_application.name="voicemode"
export PIPEWIRE_PROPS='{ application.name = voicemode }'

if [ ! -x "${VENV_PYTHON}" ]; then
    echo "Error: voicemode virtualenv not found at ${VENV_PYTHON}" >&2
    echo "Run Phase 1 setup to initialize the Python 3.12 virtualenv." >&2
    exit 1
fi

exec "${VENV_PYTHON}" "${VOICE_SCRIPT}" "$@"
```

#### Key Rules & Pitfalls
- Must have executable permissions (`chmod +x ~/.local/bin/voicemode` -> 0755).
- Create symlink `ln -sf ~/.local/bin/voicemode ~/.local/bin/voice`.
- Use `exec` to avoid dangling bash wrapper processes during long-running background sessions.
- Export both `PULSE_PROP_application.name` and `PIPEWIRE_PROPS` to guarantee node identification across both ALSA-PipeWire and PulseAudio emulation layers.

---

### 2.2. Stream Naming & Early Environment Pre-seeding (`voice.py`)

#### Role & Data Flow
Ensures that direct invocations (e.g. `python voice.py` or test scripts) also tag PipeWire client nodes cleanly as `voicemode`.

#### Existing Code
[`voice.py:1-33`](file:///home/pera/github_repo/Voice/voice.py#L1-L33)
Currently imports `sounddevice` directly at module level without pre-seeding client node environment variables.

```python
# Existing code in voice.py:1-33
#!/usr/bin/python3.11
"""Desktop-global voice command for STT and TTS..."""
from __future__ import annotations

import argparse
...
import os
...
import sounddevice as sd
from faster_whisper import WhisperModel
```

#### Pattern to Implement
Pre-seed environment variables **before** importing `sounddevice` (which initializes PortAudio upon import). Also modernize the shebang to Python 3.

```python
#!/usr/bin/env python3
"""Desktop-global voice command for STT and TTS.

Press Super+B to start recording, press Super+B again to stop and transcribe.
Press Super+T to speak selected text, press Super+T again to stop speaking.
Ctrl+C exits.
"""

from __future__ import annotations

import os

# Pre-seed PipeWire and PulseAudio node properties before PortAudio/sounddevice initializes (D-11)
os.environ.setdefault("PULSE_PROP_application.name", "voicemode")
os.environ.setdefault("PIPEWIRE_PROPS", '{ application.name = voicemode }')

import argparse
import ast
import asyncio
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import threading
import time
import tty
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
```

---

### 2.3. Audio Capture Subsystem & Software Resampling Fallback (`voice.py`)

#### Role & Data Flow
Captures microphone PCM stream from PipeWire default source, optimizes for Faster-Whisper's native 16,000 Hz requirement, and provides a zero-dependency software fallback (`np.interp`) if PortAudio hardware negotiation fails.
- **Inflow:** PortAudio `sd.InputStream` chunks (float32 array, mono).
- **Processing:** Direct 16 kHz stream request; on failure, queries device native sample rate, captures at native rate, and resamples to 16 kHz on completion.
- **Outflow:** 16-bit mono 16 kHz WAV file for Whisper inference.

#### Existing Code
[`voice.py:92-175`](file:///home/pera/github_repo/Voice/voice.py#L92-L175)
Currently, `resolve_sample_rate` probes `info["default_samplerate"]`, which returns 44.1 kHz or 48.0 kHz on PipeWire, forcing unnecessary resampling inside Faster-Whisper.

```python
# Existing code in voice.py:167-175
def resolve_sample_rate(input_device: Optional[int | str], override: Optional[int]) -> int:
    if override:
        return override
    try:
        info = sd.query_devices(input_device, "input") if input_device is not None else sd.query_devices(kind="input")
        return int(info["default_samplerate"])
    except Exception:
        return 16000
```

#### Pattern to Implement
1. **Sample Rate Resolver:** Default directly to 16,000 Hz (D-10) since PipeWire resamples transparently.
2. **Software Resampling Helper (`resample_pcm`):** Fast linear interpolation using `np.interp` (0.8ms for 1s audio, zero additional dependencies).
3. **Resilient Recorder (`Recorder`):** Attempts 16 kHz mono; falls back to hardware native rate if PortAudio raises `sd.PortAudioError`.

```python
# Software resampling fallback using numpy interpolation (Agent's Discretion / D-10)
def resample_pcm(audio: np.ndarray, orig_sr: int, target_sr: int = 16000) -> np.ndarray:
    """Resample 1D or 2D audio array from orig_sr to target_sr using linear interpolation."""
    if orig_sr == target_sr:
        return audio
    num_samples = int(round(len(audio) * float(target_sr) / orig_sr))
    orig_idx = np.arange(len(audio))
    target_idx = np.linspace(0, len(audio) - 1, num_samples)
    if audio.ndim > 1:
        resampled = np.empty((num_samples, audio.shape[1]), dtype=audio.dtype)
        for ch in range(audio.shape[1]):
            resampled[:, ch] = np.interp(target_idx, orig_idx, audio[:, ch])
        return resampled
    return np.interp(target_idx, orig_idx, audio).astype(audio.dtype)


def resolve_sample_rate(input_device: Optional[int | str], override: Optional[int]) -> int:
    """Resolve audio input sample rate, defaulting to 16000 Hz for Faster-Whisper."""
    if override:
        return override
    return 16000


class Recorder:
    def __init__(self, sample_rate: int = 16000, input_device: Optional[int | str] = None) -> None:
        self.target_sample_rate = sample_rate
        self.actual_sample_rate = sample_rate
        self.input_device = input_device
        self.frames: list[np.ndarray] = []
        self.statuses: list[str] = []
        self.stream: Optional[sd.InputStream] = None
        self.started_at: Optional[float] = None

    @property
    def recording(self) -> bool:
        return self.stream is not None

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.statuses.append(str(status))
        self.frames.append(indata.copy())

    def start(self) -> None:
        self.frames = []
        self.statuses = []
        try:
            self.stream = sd.InputStream(
                samplerate=self.target_sample_rate,
                channels=1,
                dtype="float32",
                device=self.input_device,
                callback=self._callback,
            )
            self.actual_sample_rate = self.target_sample_rate
        except sd.PortAudioError:
            # Fallback to device hardware rate if 16 kHz negotiation fails (D-10)
            try:
                info = (
                    sd.query_devices(self.input_device, "input")
                    if self.input_device is not None
                    else sd.query_devices(kind="input")
                )
                self.actual_sample_rate = int(info["default_samplerate"])
            except Exception:
                self.actual_sample_rate = 44100

            self.stream = sd.InputStream(
                samplerate=self.actual_sample_rate,
                channels=1,
                dtype="float32",
                device=self.input_device,
                callback=self._callback,
            )
        self.stream.start()
        self.started_at = time.monotonic()

    def stop_to_wav(self, save_dir: Optional[Path]) -> tuple[Path, float, bool]:
        if self.stream is None or self.started_at is None:
            raise RuntimeError("recording is not active")

        stream = self.stream
        self.stream = None
        stream.stop()
        stream.close()

        duration = time.monotonic() - self.started_at
        self.started_at = None

        if not self.frames:
            raise RuntimeError("no audio frames were captured")

        audio = np.concatenate(self.frames, axis=0)
        audio = np.clip(audio, -1.0, 1.0)

        # Resample to target 16 kHz if recorded at hardware fallback rate
        if self.actual_sample_rate != self.target_sample_rate:
            audio = resample_pcm(audio, self.actual_sample_rate, self.target_sample_rate)

        pcm = (audio * 32767.0).astype(np.int16)

        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
            wav_path = save_dir / time.strftime("voice-%Y%m%d-%H%M%S.wav")
            should_delete = False
        else:
            temp = tempfile.NamedTemporaryFile(prefix="voice-", suffix=".wav", delete=False)
            wav_path = Path(temp.name)
            temp.close()
            should_delete = True

        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.target_sample_rate)
            wav.writeframes(pcm.tobytes())

        return wav_path, duration, should_delete
```

---

### 2.4. Auditory Cue Synthesis & Threading (`voice.py`)

#### Role & Data Flow
Generates auditory feedback on start, reminder, and stop actions.
- **Start Chime:** Synchronous, blocking 70ms sine wave executed **prior** to `recorder.start()`. Audio buffer only begins capturing after the tone has ended, preventing chime bleed into the transcript (D-14).
- **Stop Chime:** Asynchronous, non-blocking playback dispatched in a daemon `threading.Thread`. Transcription pipeline begins immediately with sub-millisecond invocation lag (D-14).
- **Volume:** Default 0.08, reading `VOICEMODE_CUE_VOLUME` or `VOICE_BEEP_VOLUME` (D-13).

#### Existing Code
[`voice.py:227-273`](file:///home/pera/github_repo/Voice/voice.py#L227-L273)
Currently uses a two-tone 190ms start pattern and synchronous stop pattern that blocks the main thread.

```python
# Existing code in voice.py:262-267
patterns = {
    "start": ((880, 0.07), (0, 0.03), (1175, 0.09)),
    "recording": ((1046, 0.055),),
    "stop": ((1175, 0.07), (0, 0.03), (660, 0.11)),
    "error": ((220, 0.12), (0, 0.04), (220, 0.12)),
}
```

#### Pattern to Implement
1. **Start Pattern:** Single 880 Hz tone for 70ms: `"start": ((880, 0.07),)`
2. **Cue Volume Fallback:**
   ```python
   def cue_volume(args: argparse.Namespace) -> float:
       vol = getattr(args, "beep_volume", None)
       if vol is None:
           vol_str = os.getenv("VOICEMODE_CUE_VOLUME", os.getenv("VOICE_BEEP_VOLUME", "0.08"))
           vol = float(vol_str)
       return max(0.0, min(float(vol), 1.0))
   ```
3. **Async Dispatch Pattern:**
   ```python
   def play_cue_async(args: argparse.Namespace, cue: str) -> None:
       """Dispatch auditory cue asynchronously in a background daemon thread."""
       if not getattr(args, "beep", True):
           return
       threading.Thread(target=play_cue, args=(args, cue), daemon=True).start()
   ```

#### Invocation Sequence in `run_background_recording()` and `run_terminal_mode()`
```python
# START SEQUENCE (Synchronous lead-in cue before mic opens):
play_cue(args, "start")  # Blocks ~70ms; guarantees silence before capture
recorder.start()         # Microphone stream begins strictly after tone ends

# ... recording loop ...

# STOP SEQUENCE (Asynchronous stop cue concurrently with transcription):
wav_path, duration, should_delete = recorder.stop_to_wav(args.save_dir)
play_cue_async(args, "stop")  # Dispatches in 0.8ms; user hears chime while Whisper loads
notify(APP_NAME, "Transcribing...", args)
model_state = load_model(args)
text, _ = transcribe(model_state, wav_path, args)
```

---

### 2.5. Safety Recording Duration Ceiling (`voice.py`)

#### Role & Data Flow
Prevents runaway background processes from filling disk or consuming CPU if the user forgets to stop recording (D-12).

#### Existing Code
[`voice.py:868-873`](file:///home/pera/github_repo/Voice/voice.py#L868-L873)
Recording loop currently only checks `while not stop_requested:` without duration ceiling.

```python
# Existing loop in voice.py:868-873
while not stop_requested:
    if next_recording_cue is not None and time.monotonic() >= next_recording_cue:
        play_cue(args, "recording")
        next_recording_cue = time.monotonic() + args.recording_beep_interval
    time.sleep(0.05)
```

#### Pattern to Implement
Add a global ceiling constant and break cleanly out of the loop if exceeded:

```python
MAX_RECORDING_SECONDS = 300.0  # 5-minute safety ceiling (D-12)

# Inside run_background_recording():
while not stop_requested:
    if recorder.started_at and (time.monotonic() - recorder.started_at) >= MAX_RECORDING_SECONDS:
        print(f"Safety ceiling: reached maximum duration ({int(MAX_RECORDING_SECONDS)}s). Stopping recording.", flush=True)
        notify(APP_NAME, f"Max recording duration ({int(MAX_RECORDING_SECONDS)}s) reached. Transcribing...", args)
        break

    if next_recording_cue is not None and time.monotonic() >= next_recording_cue:
        play_cue(args, "recording")
        next_recording_cue = time.monotonic() + args.recording_beep_interval
    time.sleep(0.05)
```

---

### 2.6. Faster-Whisper Model Defaults & Silero VAD (`voice.py`)

#### Role & Data Flow
Configures default STT parameters for sub-second CPU transcription on Intel Alder Lake hardware (D-04, D-05, D-07, D-08).
- Model: `small.en` (CPU `int8`, ~244M params, ~460MB download)
- Beam size: `1` (Greedy decoding for maximum throughput)
- VAD filter: `True` (Silero Voice Activity Detection to trim silence)

#### Existing Code
[`voice.py:1077-1081`](file:///home/pera/github_repo/Voice/voice.py#L1077-L1081) and [`voice.py:300-305`](file:///home/pera/github_repo/Voice/voice.py#L300-L305)

```python
# Existing defaults in voice.py:1077-1081
parser.add_argument("--model", default=os.getenv("VOICE_STT_MODEL", "base"))
parser.add_argument("--device", default=os.getenv("VOICE_STT_DEVICE", "auto"))
parser.add_argument("--compute-type", default=os.getenv("VOICE_STT_COMPUTE_TYPE", "auto"))
parser.add_argument("--language", default=os.getenv("VOICE_STT_LANGUAGE", ""))
parser.add_argument("--beam-size", type=int, default=int(os.getenv("VOICE_STT_BEAM_SIZE", "5")))
```

#### Pattern to Implement
In `parse_args()`:
```python
parser.add_argument("--model", default=os.getenv("VOICE_STT_MODEL", "small.en"))
parser.add_argument("--device", default=os.getenv("VOICE_STT_DEVICE", "cpu"))
parser.add_argument("--compute-type", default=os.getenv("VOICE_STT_COMPUTE_TYPE", "int8"))
parser.add_argument("--language", default=os.getenv("VOICE_STT_LANGUAGE", "en"))
parser.add_argument("--beam-size", type=int, default=int(os.getenv("VOICE_STT_BEAM_SIZE", "1")))
parser.add_argument(
    "--vad-filter",
    dest="vad_filter",
    action="store_true",
    default=env_bool("VOICE_VAD_FILTER", True),
    help="Enable Silero VAD filter to trim silence (default: True).",
)
parser.add_argument(
    "--no-vad-filter",
    dest="vad_filter",
    action="store_false",
    help="Disable Silero VAD filter.",
)
parser.add_argument(
    "--beep-volume",
    type=float,
    default=float(os.getenv("VOICEMODE_CUE_VOLUME", os.getenv("VOICE_BEEP_VOLUME", "0.08"))),
    help="Cue volume from 0.0 to 1.0 (default: 0.08).",
)
```

In `transcribe()`:
```python
def transcribe(model_state: ModelState, wav_path: Path, args: argparse.Namespace) -> tuple[str, ModelState]:
    kwargs = {
        "beam_size": args.beam_size,
        "vad_filter": getattr(args, "vad_filter", True),
    }
    if args.language:
        kwargs["language"] = args.language

    try:
        segments, info = model_state.model.transcribe(str(wav_path), **kwargs)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, model_state
    except Exception as exc:
        if model_state.requested_device == "cpu":
            raise
        print(f"GPU/auto transcription failed ({exc}); retrying on CPU int8...", flush=True)
        cpu_state = load_model(args, force_cpu=True)
        segments, info = cpu_state.model.transcribe(str(wav_path), **kwargs)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, cpu_state
```

---

### 2.7. Project Packaging Metadata (`pyproject.toml`)

#### Role & Data Flow
Defines project requirements and dependencies for `uv pip install -e ".[kokoro,edge]"`.

#### Existing Code
[`pyproject.toml:10-47`](file:///home/pera/github_repo/Voice/pyproject.toml#L10-L47)
Currently declares `requires-python = ">=3.11"`. Since Python 3.12 is the mandated project standard (ENV-01), ensure `requires-python = ">=3.12"` and verify dependencies.

```toml
# Pattern to ensure in pyproject.toml:
[project]
name = "voicemode"
version = "0.1.0"
description = "Desktop-global speech-to-text and text-to-speech hotkeys for Linux."
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "faster-whisper>=1.2.1",
  "numpy>=2.0.2",
  "PyYAML>=6.0",
  "sounddevice>=0.5.0"
]

[project.optional-dependencies]
kokoro = [
  "kokoro-onnx==0.5.0",
  "soundfile>=0.14.0"
]
edge = [
  "edge-tts>=7.2.7"
]
all = [
  "kokoro-onnx==0.5.0",
  "soundfile>=0.14.0",
  "edge-tts>=7.2.7"
]

[project.scripts]
voicemode = "voice:main"
voice = "voice:main"
```

---

## 3. Cross-Cutting Patterns & Conventions

### 3.1. Process State & PID File Management
State files reside under `$XDG_RUNTIME_DIR/voice-stt/` (fallback `/tmp/voice-stt-$UID/`).
- Follow the established `write_pid()` and `remove_pid()` pattern in `finally` blocks ([`voice.py:851, 911`](file:///home/pera/github_repo/Voice/voice.py#L851-L911)).
- Ensure directory creation handles concurrency cleanly via `STATE_DIR.mkdir(parents=True, exist_ok=True)`.

### 3.2. Error Reporting & User Notifications
- Follow the two-channel reporting pattern:
  1. Detailed technical logs to `sys.stderr` and `LOG_FILE` ([`voice.py:898`](file:///home/pera/github_repo/Voice/voice.py#L898)).
  2. Concise visual toast via `notify(APP_NAME, message, args)` using `notify-send` ([`voice.py:319-326`](file:///home/pera/github_repo/Voice/voice.py#L319-L326)).
  3. Auditory cue on failure via `play_cue(args, "error")` ([`voice.py:896`](file:///home/pera/github_repo/Voice/voice.py#L896)).

### 3.3. Memory & Resource Cleanup
- Always stop and close the `sd.InputStream` within `stop_to_wav()` before saving or transcribing.
- Temporary WAV files generated with `delete=False` must be deleted in a `try...finally` block if `should_delete` is `True`.

---

## 4. Verification Pattern Reference

Each task plan in Phase 1 should use these exact command invocation patterns:

| Verification Target | Command Pattern | Expected Outcome |
|---|---|---|
| Virtual Environment & Imports | `.venv/bin/python -c "import faster_whisper, kokoro_onnx, edge_tts, sounddevice, numpy; print('OK')"` | Prints `OK` with exit 0 |
| Launcher Script Access | `~/.local/bin/voicemode --help` | Displays help message without venv activation |
| Symlink Resolution | `~/.local/bin/voice --status` | Executes launcher transparently |
| Model Pre-download & Cache | `voicemode --check --allow-download` | Loads `small.en` on CPU `int8`, caches model weights |
| Auditory Cue Playback | `voicemode --test-beep` | Plays start, reminder, stop cues without clipping |
| PipeWire Stream Labeling | `wpctl status \| grep voicemode` | Displays `voicemode` client stream during active capture |

---

*Phase 1 Pattern Map complete. Ready for task decomposition in Plan 01 and Plan 02.*
