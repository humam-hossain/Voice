# Dependency and License Notes

This file tracks the non-repository components used by voicemode.

The repository source code is MIT licensed. Third-party packages, model weights, and system tools keep their own licenses.

## Python Packages

| Component | Use | License status |
| --- | --- | --- |
| faster-whisper | Local STT inference | MIT |
| ctranslate2 | Whisper inference runtime | MIT |
| numpy | Audio arrays | BSD-style permissive |
| sounddevice | Microphone and cue audio | MIT |
| PyYAML | Optional config parsing | MIT |
| kokoro-onnx | Local Kokoro TTS runtime | MIT package metadata, but current package dependency chain needs review |
| soundfile | WAV output for Kokoro TTS | BSD-style permissive |
| edge-tts | Optional Edge TTS backend | LGPLv3 package, service terms are separate |

## Wayland Input & Clipboard Stack

| Component | Package (Arch) | Role | Permissions |
|---|---|---|---|
| `wtype` | `wtype` | Rootless keystroke injection & simulated shortcuts | Unprivileged (interfaces with `zwp_virtual_keyboard_v1`) |
| `wl-clipboard` | `wl-clipboard` | Clipboard management (`wl-copy`, `wl-paste`) | Unprivileged |
| `ydotool` | `ydotool` | Secondary fallback typing backend | Optional (requires root/uinput daemon `ydotoold`) |

## TTS Backend Caveats

Kokoro is the default local TTS backend in this working tree. The model weights are distributed separately and are not committed to the repository.

The currently tested `kokoro-onnx==0.5.0` package pulls `phonemizer-fork`, which reports GPLv3+ metadata. That is acceptable for local testing, but it is not a clean permissive-only dependency chain. Before publishing binary packages or claiming a strict MIT-style stack, replace or isolate that dependency path.

The Edge backend is optional. It uses the open-source `edge-tts` package, but sends text to Microsoft's online Edge TTS service. It should not be treated as an open local TTS engine.

## Local Assets

The following paths are intentionally ignored by git:

```text
models/
samples/
```

Use this helper to restore Kokoro assets after cloning:

```bash
scripts/download-kokoro-assets.sh
```
