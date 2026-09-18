# Phase 1: Environment & Audio Subsystem - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-18
**Phase:** 1-Environment & Audio Subsystem
**Areas discussed:** Python Environment & Execution Mode, Default Whisper Model & Quantization, Audio Device Selection & PipeWire Handling, Auditory Cue Feedback

---

## Python Environment & Execution Mode

| Option | Description | Selected |
|--------|-------------|----------|
| In-tree .venv with a launcher script/symlink in ~/.local/bin | Enables direct execution like 'voicemode --toggle' from terminal and Hyprland shortcuts without needing manual venv activation | ✓ |
| In-tree .venv invoked explicitly with 'uv run voicemode' | Clean, keeps all execution tied to project directory and uv | |
| Global user tool installation via 'uv tool install --editable .' | Installs voicemode into uv's isolated tool bin path ~/.local/bin | |

**User's choice:** In-tree .venv with launcher script/symlink in `~/.local/bin`.
**Notes:** Allows seamless calling from window manager keybindings and desktop environments without requiring explicit path activation.

---

## Package Dependencies

| Option | Description | Selected |
|--------|-------------|----------|
| Full installation with all extras ('uv pip install -e \".[kokoro,edge]\"') | Ensures both Faster-Whisper STT and Kokoro/Edge TTS dependencies are fully satisfied upfront | ✓ |
| Minimal core first ('uv pip install -e .') | Only installs faster-whisper, sounddevice, and numpy; TTS extras added later | |
| Full installation plus developer tooling | Includes ruff and development tools for testing/formatting | |

**User's choice:** Full installation with all extras (`[kokoro,edge]`).

---

## System Prerequisites

| Option | Description | Selected |
|--------|-------------|----------|
| User preference: check existing packages setup on machine | User requested checking what is already set up to avoid unnecessary installations | ✓ |

**User's choice:** Check machine setup; do not install system packages via pacman.
**Notes:** Probing confirmed `libportaudio.so.2`, `ffmpeg`, `ffplay`, `wtype`, `wl-clipboard`, `ydotool`, `notify-send`, and `uv` (with `cpython-3.12.12` installed) are already present.

---

## Default Whisper Model & Quantization

| Option | Description | Selected |
|--------|-------------|----------|
| 'small.en' / 'small' (~244M params, ~460MB) | Sweet spot for CPU dictation; near-instant transcription latency (<1s) with strong English accuracy | ✓ |
| 'distil-large-v3' (~756M params, ~1.5GB) | Highest accuracy, existing default in voice.py, but higher CPU latency (2–4s per sentence) | |
| 'base.en' (~74M params, ~140MB) | Ultra-lightweight and fastest possible response, but lower recognition accuracy | |

**User's choice:** `small.en` on CPU `int8`.

---

## Whisper Language & Caching

| Option | Description | Selected |
|--------|-------------|----------|
| English-only ('small.en') | Optimized specifically for English dictation, smaller memory footprint and faster inference | ✓ |
| Multilingual ('small') | Supports multilingual dictation | |

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-download and cache 'small.en' during verification ('voice.py --check') | Eliminates cold-start download delay on first actual dictation keypress | ✓ |
| On-demand download | Download on first dictation toggle | |

**User's choice:** English-only `small.en`, pre-downloaded and verified in Phase 1.

---

## Whisper Decoding & Filtering

| Option | Description | Selected |
|--------|-------------|----------|
| Greedy decoding ('beam_size=1') | ~2-3x faster transcription on CPU; ideal for low-latency push-to-talk | ✓ |
| Standard beam search ('beam_size=5') | Default in Faster-Whisper; higher CPU latency | |

| Option | Description | Selected |
|--------|-------------|----------|
| Enable Silero VAD filter ('vad_filter=True') | Trims leading/trailing silence and breaths, preventing hallucinations | ✓ |
| Disable VAD filter ('vad_filter=False') | Transcribes raw captured audio directly | |

**User's choice:** `beam_size=1` and `vad_filter=True`.

---

## Audio Device & PipeWire Integration

| Option | Description | Selected |
|--------|-------------|----------|
| Rely purely on PipeWire default source | User switches active input in system audio mixer like pavucontrol/wpctl | ✓ |
| Rely on default source + provide '--list-devices' flag | Adds CLI flag to inspect sounddevice indices | |

| Option | Description | Selected |
|--------|-------------|----------|
| 16 kHz direct capture with fallback | Request 16 kHz directly as PipeWire natively resamples, with software fallback | ✓ |
| Strict 16 kHz only | Rely on PipeWire-Pulse always handling 16 kHz negotiation | |

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit application name ('voicemode') for audio streams | Shows up cleanly labeled in pavucontrol and PipeWire patchbays | ✓ |
| Default PortAudio client name | Generated by PortAudio | |

| Option | Description | Selected |
|--------|-------------|----------|
| Longer cutoff: 300 seconds (5 minutes) | Allows dictating longer thoughts or uninterrupted speeches | ✓ |
| Keep 120-second cutoff | Default 2 minutes | |

**User's choice:** PipeWire default source, 16kHz with fallback, explicit `voicemode` client name, 300-second safety cutoff.

---

## Auditory Cue Feedback & Synchronization

| Option | Description | Selected |
|--------|-------------|----------|
| Subtle synthesized sine tones (0.08) with VOICEMODE_CUE_VOLUME override | Configurable volume for desktop speakers / headphones | ✓ |
| Synchronous start chime (~70ms) + Asynchronous stop chime | Prevents start chime sound from bleeding into microphone recording; stop chime is non-blocking | ✓ |

**User's choice:** Subtle sine tones (volume 0.08) with brief synchronous start chime to avoid mic contamination, and asynchronous stop chime.

---

## The Agent's Discretion

- Implementation of software fallback if PortAudio sample rate negotiation fails.
- Symlink vs shell wrapper script format in `~/.local/bin/voicemode`.

## Deferred Ideas

None — discussion stayed within phase scope.
