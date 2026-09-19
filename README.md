# voicemode

Desktop-global speech-to-text dictation and text-to-speech utility for **Arch Linux running Hyprland**.

voicemode delivers seamless, low-latency push-to-talk transcription that types directly into any focused window (terminals, code editors, browsers) and on-demand neural text-to-speech reading of highlighted screen text using local, offline models on Wayland.

- **Dedicated Architecture & Setup Guide:** [`docs/ARCH_HYPRLAND.md`](docs/ARCH_HYPRLAND.md)
- **Dependency & License Reference:** [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md)

---

## Parameters & Configuration Reference

Complete reference of all parameters, CLI flags, environment variables, default values, and valid ranges.

### 1. Speech-to-Text (Whisper STT)

| Parameter / CLI Flag | Environment Variable | Type / Valid Range | Default | Description |
|---|---|---|---|---|
| `--model <name>` | `VOICE_STT_MODEL` | String: `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large-v1`, `large-v2`, `large-v3`, `turbo`, or custom HuggingFace repo / local directory path | `small.en` | Faster-Whisper model size or path for speech recognition. |
| `--device <device>` | `VOICE_STT_DEVICE` | `cpu`, `cuda`, `auto` | `cpu` | Computation device for Whisper CTranslate2 inference. |
| `--compute-type <type>` | `VOICE_STT_COMPUTE_TYPE` | `int8`, `int8_float16`, `int16`, `float16`, `float32`, `auto` | `int8` | Model weight quantization precision (`int8` recommended for CPU). |
| `--language <lang>` | `VOICE_STT_LANGUAGE` | ISO-639-1 code (e.g. `en`, `es`, `fr`, `de`, `ja`, `zh`) or empty for auto-detect | `en` | Spoken language for transcription. |
| `--beam-size <int>` | `VOICE_STT_BEAM_SIZE` | Integer $\ge 1$ (typically `1` to `5`) | `1` | Beam search width during Whisper decoding (`1` = greedy/fastest). |
| `--vad-filter` / `--no-vad-filter` | `VOICE_VAD_FILTER` | Boolean (`true` / `false`) | `true` | Silero VAD (Voice Activity Detection) filter to trim silence before STT inference. |
| `--allow-download` | — | Flag (boolean) | `false` | Allow Faster-Whisper to download missing model weights from Hugging Face. |
| — | `VOICE_MAX_RECORDING_SECONDS` | Float $> 0.0$ seconds | `300.0` (5 min) | Safety hard cutoff for a single continuous recording session. |

### 2. Text-to-Speech (TTS)

| Parameter / CLI Flag | Environment Variable | Type / Valid Range | Default | Description |
|---|---|---|---|---|
| `--tts-backend <backend>` | `VOICE_TTS_BACKEND` | `kokoro`, `edge` | `kokoro` | Speech synthesis engine (`kokoro` = 100% offline ONNX, `edge` = Microsoft online). |
| `--tts-voice <id>` | `VOICE_TTS_VOICE` | String (Kokoro voice ID or Edge voice ID) | Kokoro: `af_heart`<br/>Edge: `en-GB-RyanNeural` | Voice identifier for speech generation. Kokoro secondary: `bm_george`. Run `voice --list-tts-voices` for all available voices. |
| `--tts-speed <float>` | `VOICE_TTS_SPEED` | Float `0.5` to `2.0` (strictly clamped) | `1.2` | Speed multiplier for synthesized speech. |
| `--kokoro-model <path>` | `VOICE_KOKORO_MODEL` | File path | `models/kokoro/kokoro-v1.0.onnx` | Path to Kokoro ONNX model weights. |
| `--kokoro-voices <path>` | `VOICE_KOKORO_VOICES` | File path | `models/kokoro/voices-v1.0.bin` | Path to Kokoro voice embeddings tensor file. |
| `--kokoro-lang <code>` | `VOICE_KOKORO_LANG` | `en-us`, `en-gb`, `ja`, `zh`, `es`, `fr`, `hi`, `it`, `pt-br` | `en-us` | Language code for Kokoro phonemizer. |
| `--kokoro-trim` / `--kokoro-no-trim` | `VOICE_KOKORO_TRIM` | Boolean (`true` / `false`) | `false` (`--kokoro-no-trim`) | Trim leading and trailing silence on Kokoro audio chunks. |
| — | `VOICE_TTS_MAX_CHARS` | Integer $\ge 1$ | `5000` | Max character limit before bounding TTS text with a notification warning. |
| — | `HERMES_CONFIG` | File path | `~/.hermes/config.yaml` | Optional config file providing fallback voice and speed defaults. |

### 3. Audio Capture & Hardware

| Parameter / CLI Flag | Environment Variable | Type / Valid Range | Default | Description |
|---|---|---|---|---|
| `--input-device <id/name>` | `VOICE_INPUT_DEVICE` | Integer (device index) or String (substring match) | `None` (system default) | Microphone audio input device. Run `voice --list-devices` to view available devices. |
| `--sample-rate <hz>` | — | Integer Hz (e.g. `16000`, `44100`, `48000`) | Native hardware rate (auto-resampled to 16 kHz) | Recording sample rate in Hz. |
| `--save-dir <dir>` | — | Directory path | `None` (temp file unlinked after STT) | Save directory to retain recorded `.wav` files instead of deleting. |
| `--list-devices` | — | Flag | — | List all PortAudio input and output sound devices and exit. |

### 4. Text Injection & Keystroke Typing

| Parameter / CLI Flag | Environment Variable | Type / Valid Range | Default | Description |
|---|---|---|---|---|
| `--output-method <method>` | `VOICE_OUTPUT_METHOD` | `type`, `paste`, `terminal-paste`, `clipboard` | `type` | How recognized text is injected into the active window. `type` simulates keystrokes; `paste` sends via clipboard + `Ctrl+V`; `terminal-paste` sends via `Ctrl+Shift+V`; `clipboard` copies to clipboard only. |
| `--wayland-backend <backend>` | `VOICE_WAYLAND_BACKEND` | `auto`, `wtype`, `ydotool` | `auto` | Wayland typing backend (`auto` prefers `wtype`, falls back to `ydotool`). |
| `--type-delay <ms>` | `VOICE_TYPE_DELAY` | Integer $\ge 0$ ms | `2` ms | Inter-keystroke synthetic delay for `--output-method type`. |
| `--pre-type-delay <ms>` | `VOICE_PRE_TYPE_DELAY` | Integer $\ge 0$ ms | `50` ms | Window-settling delay in milliseconds before typing begins. |
| `--keep-newlines` / `--no-keep-newlines` | `VOICE_KEEP_NEWLINES` | Boolean (`true` / `false`) | `false` (`--no-keep-newlines`) | Preserve literal newlines in typed text (default collapses newlines to single spaces). |
| `--paste` / `--no-paste` | — | Boolean (`true` / `false`) | `true` (`--paste`) | Enable or disable automatic text insertion into focused application. |

### 5. Auditory Cues & Desktop Notifications

| Parameter / CLI Flag | Environment Variable | Type / Valid Range | Default | Description |
|---|---|---|---|---|
| `--beep` / `--no-beep` | `VOICE_BEEP` | Boolean (`true` / `false`) | `true` (`--beep`) | Play audio feedback tones for start, reminder ticks, stop, and error. |
| `--beep-volume <float>` | `VOICEMODE_CUE_VOLUME`<br/>(fallback: `VOICE_BEEP_VOLUME`) | Float `0.0` to `1.0` (clamped: `0.0` = mute, `1.0` = max) | `0.08` | Volume level of auditory sine-wave cues. |
| `--recording-beep-interval <sec>` | `VOICE_RECORDING_BEEP_INTERVAL` | Float $\ge 0.0$ seconds (`0.0` disables ticks) | `5.0` s | Interval between periodic 1046 Hz reminder ticks while recording is active. |
| `--beep-output-device <id/name>` | `VOICE_BEEP_OUTPUT_DEVICE` | Integer (device index) or String (substring match) | `None` (system default) | Audio output device for chime playback. |
| `--notify` / `--no-notify` | — | Boolean (`true` / `false`) | `true` (`--notify`) | Display desktop notification toasts via `notify-send`. |
| `--test-beep` | — | Flag | — | Test auditory cues by playing start chime, reminder tick, and stop chime, then exit. |

### 6. Control Commands & Operational Modes

| Command / CLI Flag | Arguments | Scope | Description |
|---|---|---|---|
| `--toggle` | — | Global desktop | Toggle push-to-talk recording: start recording if idle; stop, transcribe, and type if active. |
| `--speak-selection` | — | Global desktop | Synthesize and speak currently selected text (`wl-paste --primary`), falling back to clipboard. Halts speech if already active. |
| `--speak <text>` | Text string or `-` (stdin) | CLI / Scripting | Speak the provided text string using TTS (use `-` to pipe from stdin). |
| `--stop-tts` | — | Global desktop | Immediately halt active TTS playback and clean up temporary audio files. |
| `--status` | — | Diagnostics | Print current status of STT and TTS background worker processes and PID locks. |
| `--kill` | — | Recovery | Terminate active background workers and purge stale PID locks. |
| `--doctor` | — | Diagnostics | Run pre-flight diagnostic probe (binaries, mic volume/mute, model weights, keybinds, PIDs). |
| `--verify` | `[--tier 1\|2\|3\|all]` | Testing | Run 3-tier end-to-end verification suite (`tier 1` static, `tier 2` synthetic loopback, `tier 3` interactive matrix). |
| `--json` | — | Output modifier | Format `--doctor` or `--verify` results as JSON. |
| `--export-markdown <path>` | File path | Output modifier | Export verification or diagnostic report to a markdown file. |
| `--check` | — | Diagnostics | Test Faster-Whisper model loading and print selected compute backend. |
| `--tts-check` | — | Diagnostics | Inspect TTS configuration, installed packages (`kokoro-onnx`, `edge-tts`), and voice assets. |
| `--list-tts-voices` | — | Discovery | List all available Kokoro voice names sorted alphabetically with default/secondary markers. |
| `--download-tts-assets` | — | Setup | Download and verify Kokoro ONNX model and voice weights into `models/kokoro/`. |
| `--terminal` | — | Interactive | Run in terminal-only mode with `Ctrl+B` push-to-talk toggle. |
| `--watch` | — | Monitoring | Follow and stream STT and TTS background activity logs in real time. |
| `--install-hotkey` / `--install-hotkeys` | — | Setup | Install desktop keybindings (auto-detects Hyprland or GNOME). |
| `--install-hyprland` | — | Setup | Append keybinds to `~/.config/hypr/custom/keybinds.lua` and reload Hyprland. |
| `--print-hyprland` | — | Setup | Print Hyprland Lua keybind configuration block to stdout. |

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

## Configuration Quick Reference

For the comprehensive list of all STT, TTS, audio capture, text injection, cue, and command parameters, see the [Parameters & Configuration Reference](#parameters--configuration-reference) at the top of this document.

| Common Setting | Flag | Environment Variable | Default | Valid Range / Options |
|---|---|---|---|---|
| Typing delay | `--type-delay <ms>` | `VOICE_TYPE_DELAY` | `2` ms | $\ge 0$ ms |
| Pre-type settling delay | `--pre-type-delay <ms>` | `VOICE_PRE_TYPE_DELAY` | `50` ms | $\ge 0$ ms |
| Preserve newlines | `--keep-newlines` | `VOICE_KEEP_NEWLINES` | `false` | `true`, `false` |
| Audio cues | `--beep` / `--no-beep` | `VOICE_BEEP` | `true` | `true`, `false` |
| Cue volume | `--beep-volume <0.0-1.0>` | `VOICEMODE_CUE_VOLUME` | `0.08` | `0.0` - `1.0` |
| Whisper STT model | `--model <name>` | `VOICE_STT_MODEL` | `small.en` | `tiny.en` ... `large-v3`, `turbo` |
| TTS speed multiplier | `--tts-speed <float>` | `VOICE_TTS_SPEED` | `1.2` | `0.5` - `2.0` |
| Primary TTS voice | `--tts-voice <id>` | `VOICE_TTS_VOICE` | `af_heart` | Any Kokoro or Edge voice ID |

---

## Privacy Guarantee

- **Speech-to-Text:** 100% offline. Audio buffers are captured locally, transcribed via Faster-Whisper CTranslate2, and temporary audio files are unlinked immediately after insertion.
- **Text-to-Speech:** Default Kokoro engine runs 100% locally via ONNX Runtime without network access.
- *(Optional: Microsoft Edge TTS can be enabled via `--tts-backend edge`, which streams to Microsoft servers. It is disabled by default.)*

---

## License

The repository source code is licensed under the [MIT License](LICENSE). Third-party packages and neural weights maintain their respective licenses; see [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).
