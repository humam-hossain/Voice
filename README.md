# voicemode

Desktop-global speech-to-text dictation and text-to-speech utility for Arch Linux running Hyprland.

voicemode provides low-latency push-to-talk speech transcription typing directly into the active focused window (Kitty, Foot, Neovim, VS Code, browsers) and neural on-demand text-to-speech reading of highlighted screen text via Kokoro ONNX.

- Dedicated Guide: [`docs/ARCH_HYPRLAND.md`](docs/ARCH_HYPRLAND.md)
- Dependency Reference: [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md)

## Current Status

Fully tailored and validated for Arch Linux + Hyprland on Wayland:

```text
OS: Arch Linux
Compositor: Hyprland (Wayland)
Dotfiles: dots-hyprland (custom/keybinds.lua with GNU Stow preservation)
Python: 3.12 (via uv venv)
STT: faster-whisper (CPU int8)
TTS: Kokoro via kokoro-onnx (offline ONNX runtime)
Text injection: wtype (primary rootless Wayland virtual keyboard)
Selection reading / Clipboard: wl-clipboard (wl-copy, wl-paste)
```

## Features

- `Super+B`: toggle recording, then transcribe and insert text into the focused application.
- `Super+T`: speak selected text, with clipboard fallback.
- `Super+T` while speaking: stop current TTS playback.
- Local STT through `faster-whisper`.
- Local Kokoro TTS by default.
- Optional Microsoft Edge TTS backend for comparison.
- Audible recording cues with no external sound assets.
- Terminal monitor mode for background activity.

## Runtime Model

The installed GNOME shortcuts call the same command:

```text
Super+B -> voicemode --toggle
Super+T -> voicemode --speak-selection
```

For STT, `--toggle` starts a detached background recorder. The next toggle sends it a signal to stop recording, transcribe, and insert the recognized text.

For TTS, `--speak-selection` reads the X11 primary selection with `xclip -selection primary -o`. This is the text most X11 applications expose immediately after a mouse highlight. If the primary selection is empty, voicemode reads the clipboard instead. It then synthesizes a temporary audio file and plays it with `ffplay`.

Runtime state is stored under:

```text
$XDG_RUNTIME_DIR/voice-stt/
```

## Installation

Install system packages:

```bash
sudo apt install ffmpeg xclip xdotool ydotool wl-clipboard libportaudio2 portaudio19-dev libnotify-bin wget
```

Install the Python package in editable mode:

```bash
python3.11 -m pip install --user -e ".[kokoro]"
```

Download Kokoro model assets:

```bash
scripts/download-kokoro-assets.sh
```

Install GNOME hotkeys:

```bash
voicemode --install-hotkeys
```

The package also installs a `voice` command alias for compatibility with earlier local setup:

```bash
voice --install-hotkeys
```

## Usage

Start the monitor:

```bash
voicemode
```

Check STT backend loading:

```bash
voicemode --check
```

Check TTS configuration:

```bash
voicemode --tts-check
```

List Kokoro voices:

```bash
voicemode --list-tts-voices
```

Speak explicit text:

```bash
voicemode --speak "This is a local TTS test."
```

Speak selected text:

```bash
voicemode --speak-selection
```

Stop active TTS:

```bash
voicemode --stop-tts
```

## Default TTS Configuration

The current default TTS backend is Kokoro:

```text
backend: kokoro
voice: af_heart
speed: 2x
trim: false
secondary voice: bm_george
```

Use George manually:

```bash
voicemode --speak-selection --tts-voice bm_george
```

Use Edge TTS manually:

```bash
voicemode --tts-backend edge --tts-voice en-GB-RyanNeural --speak-selection
```

## Configuration

Common environment variables:

```text
VOICE_STT_MODEL=base
VOICE_STT_DEVICE=auto
VOICE_STT_COMPUTE_TYPE=auto
VOICE_STT_LANGUAGE=
VOICE_OUTPUT_METHOD=type
VOICE_WAYLAND_BACKEND=auto
VOICE_TYPE_DELAY=2
VOICE_PRE_TYPE_DELAY=50
VOICE_KEEP_NEWLINES=false
VOICE_BEEP=true
VOICE_RECORDING_BEEP_INTERVAL=5
VOICE_TTS_BACKEND=kokoro
VOICE_TTS_VOICE=af_heart
VOICE_TTS_SPEED=2.0
VOICE_KOKORO_MODEL=/path/to/kokoro-v1.0.onnx
VOICE_KOKORO_VOICES=/path/to/voices-v1.0.bin
VOICE_KOKORO_TRIM=false
```

### Key CLI Flags for Wayland Input Injection

- `--wayland-backend`: `auto` (default, prefers `wtype` over `ydotool`), `wtype`, or `ydotool`.
- `--type-delay`: Milliseconds between synthetic keystrokes for `--output-method type` (default: 2).
- `--pre-type-delay`: Milliseconds to wait before keystroke injection starts to allow modifier key release (default: 50).
- `--keep-newlines`: Preserve literal newlines in typed transcripts. Default behavior collapses internal newlines to spaces to prevent accidental Return dispatches.


## Privacy

STT is local when using the default faster-whisper path.

Kokoro TTS is local once model assets are downloaded.

Edge TTS is optional and sends text to Microsoft's online service through the `edge-tts` package. Do not use the Edge backend for private text unless that is acceptable.

## Repository Layout

```text
voice.py                         main command implementation
pyproject.toml                   package metadata and console scripts
scripts/download-kokoro-assets.sh local model asset downloader
docs/DEPENDENCIES.md             dependency and license notes
models/                          ignored local model files
samples/                         ignored generated audio samples
```

## License

The repository source code is MIT licensed.

Third-party packages, model weights, and system tools keep their own licenses. See `docs/DEPENDENCIES.md`.

The current Kokoro test path uses `kokoro-onnx==0.5.0`, which pulls a GPLv3+ phonemizer dependency. That is acceptable for local evaluation, but it is not a clean permissive-only dependency chain. Before publishing binary packages or claiming a strict MIT-style dependency stack, replace or isolate that dependency path.

The optional Edge backend is not an open local voice stack. The Python package is open source, but the service and voices are controlled by Microsoft.
