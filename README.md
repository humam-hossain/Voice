# voicemode

Desktop-global speech-to-text dictation and text-to-speech utility for **Arch Linux running Hyprland**.

voicemode delivers seamless, low-latency push-to-talk transcription that types directly into any focused window (terminals, code editors, browsers) and on-demand neural text-to-speech reading of highlighted screen text using local, offline models on Wayland.

- **Dedicated Architecture & Setup Guide:** [`docs/ARCH_HYPRLAND.md`](docs/ARCH_HYPRLAND.md)
- **Dependency & License Reference:** [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md)

---

## At a Glance

| Shortcut / Command | Action | Scope / Context | Audio Cue / Indicator |
|---|---|---|---|
| `SUPER + SHIFT + M` | **Push-to-Talk STT Toggle** | Global desktop | **Start:** 880 Hz (A5) high chime<br/>**Reminder:** 1046 Hz (C6) tick every 5s<br/>**Stop:** 1175 Hz -> 660 Hz falling chime |
| `SUPER + T` | **Read Selected Text (TTS)** | Global desktop | Synthesizes highlighted text (`wl-paste --primary`) via Kokoro ONNX |
| `SUPER + T` *(while speaking)* | **Stop Active Speech** | Global desktop | Immediately halts active audio playback |
| `voice --doctor` | **Pre-Flight Diagnostics** | Terminal | Inspects binaries, mic volume/mute, model weights, keybinds, and PIDs |
| `voice --verify` | **3-Tier E2E Verification** | Terminal | Runs automated pipeline self-test (~3.3s) and interactive app matrix |
| `voice --kill` | **Daemon Recovery** | Terminal | Terminates active background workers and purges stale PID locks |
| `voice --status` | **Daemon Status Check** | Terminal | Reports active recording/transcribing/idle status and PID health |

---

## Prerequisites & Installation (Arch Linux + Hyprland)

### 1. System Packages

On **`dots-hyprland`** installations, Wayland clipboard utilities, notification daemons, and PipeWire are pre-installed. You only need to install two packages:

```bash
sudo pacman -S wtype ffmpeg
```

*(On a vanilla Arch Linux installation, install the full toolchain: `sudo pacman -S wtype ffmpeg wl-clipboard libnotify pipewire wireplumber`)*

### 2. Python Virtual Environment (`uv`)

Create an isolated virtual environment and install voicemode with Kokoro TTS dependencies:

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[kokoro]"
```

Symlink the command to your `~/.local/bin/` so it is available globally:

```bash
mkdir -p ~/.local/bin
ln -sf "$(pwd)/.venv/bin/voice" ~/.local/bin/voice
ln -sf "$(pwd)/.venv/bin/voicemode" ~/.local/bin/voicemode
```

### 3. Download Local Offline Model Assets

Download Kokoro neural TTS weights (~338 MB total):

```bash
scripts/download-kokoro-assets.sh
```

Pre-cache Faster-Whisper `small.en` speech recognition weights (~480 MB):

```bash
voice --check --allow-download
```

### 4. Install Hyprland Keybindings (GNU Stow-Safe)

Install the global hotkeys into your Hyprland configuration:

```bash
voice --install-hotkey
```

> **GNU Stow Note:** If your `~/.config/hypr/custom/keybinds.lua` is a symbolic link pointing to a dotfiles repository (e.g. `~/.dotfiles/stow/hypr/...`), voicemode resolves the real canonical path and modifies it in-place without breaking or unlinking your symlink.

---

## Daily Workflows

### 1. Push-to-Talk Speech Dictation

1. Focus any window: Kitty terminal, Foot, Neovim, VS Code, or a browser input field.
2. Press `SUPER + SHIFT + M`. You will hear a crisp high chime (880 Hz) indicating recording has begun. A subtle tick sounds every 5 seconds as a reminder.
3. Speak your dictation naturally.
4. Press `SUPER + SHIFT + M` again. A descending chime sounds as Faster-Whisper transcribes your voice on CPU (~1.8s) and types the text directly into the focused application via `wtype`.

### 2. Neural Screen Reading (TTS)

1. Highlight any paragraph or snippet of text on your screen with your mouse in Firefox, Chromium, Zathura, or a terminal.
2. Press `SUPER + T`. Voicemode captures the Wayland primary selection (`wl-paste --primary`) and streams audio synthesized locally by Kokoro ONNX through `ffplay`.
3. To stop speech at any time, press `SUPER + T` again.

### 3. System Diagnostics & Recovery

If audio devices are changed or a crash occurs:

```bash
# Check all dependencies, audio devices, and models:
voice --doctor

# Kill any orphaned processes and clear stale lock files:
voice --kill

# Run the 3-tier self-test suite:
voice --verify --tier 2
```

---

## Key Configuration Options

You can customize behavior via CLI flags or environment variables:

| Setting | Flag | Environment Variable | Default |
|---|---|---|---|
| Typing delay | `--type-delay <ms>` | `VOICE_TYPE_DELAY` | `2` ms |
| Pre-type settling delay | `--pre-type-delay <ms>` | `VOICE_PRE_TYPE_DELAY` | `50` ms |
| Preserve newlines | `--keep-newlines` | `VOICE_KEEP_NEWLINES` | `false` (collapses to spaces) |
| Audio cues | `--beep` / `--no-beep` | `VOICE_BEEP` | `true` |
| Cue volume | `--beep-volume <0.0-1.0>` | `VOICEMODE_CUE_VOLUME` | `0.08` |
| Whisper STT model | `--model <name>` | `VOICE_STT_MODEL` | `small.en` |
| TTS speed multiplier | `--tts-speed <float>` | `VOICE_TTS_SPEED` | `1.2` (range: 0.5 - 2.0) |
| Primary TTS voice | `--tts-voice <id>` | `VOICE_TTS_VOICE` | `af_heart` (secondary: `bm_george`) |

---

## Privacy Guarantee

- **Speech-to-Text:** 100% offline. Audio buffers are captured locally, transcribed via Faster-Whisper CTranslate2, and temporary audio files are unlinked immediately after insertion.
- **Text-to-Speech:** Default Kokoro engine runs 100% locally via ONNX Runtime without network access.
- *(Optional: Microsoft Edge TTS can be enabled via `--tts-backend edge`, which streams to Microsoft servers. It is disabled by default.)*

---

## License

The repository source code is licensed under the [MIT License](LICENSE). Third-party packages and neural weights maintain their respective licenses; see [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).
