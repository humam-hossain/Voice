# voicemode

Desktop-global speech-to-text dictation and text-to-speech utility for **Arch Linux running Hyprland**.

`voicemode` delivers low-latency push-to-talk transcription that types recognized speech directly into the active focused window (terminals, code editors, browsers) and on-demand neural text-to-speech reading of mouse-highlighted screen text using local, offline models on Wayland.

Both `voice` and `voicemode` command names are installed as identical entry points.

- **Dedicated Architecture & Setup Guide:** [`docs/ARCH_HYPRLAND.md`](docs/ARCH_HYPRLAND.md)
- **Dependency & License Reference:** [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md)
- **Local Telemetry & Storage Baseline:** [`docs/telemetry.md`](docs/telemetry.md)

---

## At a Glance

| Shortcut / Command | Action | Scope / Context | Audio Cue / Indicator |
|---|---|---|---|
| `SUPER + SHIFT + M` | **Push-to-Talk STT Toggle** | Global desktop | **Start:** 880 Hz (A5) high chime<br/>**Reminder:** 1046 Hz (C6) tick every 5s<br/>**Stop:** 1175 Hz → 660 Hz falling chime |
| `SUPER + T` | **Read Selected Text (TTS)** | Global desktop | Synthesizes highlighted text (`wl-paste --primary`) via Kokoro ONNX |
| `SUPER + T` *(while speaking)* | **Stop Active Speech** | Global desktop | Immediately halts active audio playback |
| `voice --report` | **Latency Performance Report** | Terminal | Displays stage timing breakdown, median wait, P90, and RTF metrics |
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
# Or alternatively via CLI:
voice --download-tts-assets
```

Pre-cache Faster-Whisper `medium.en` speech recognition weights (~1.5 GB):

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

## CLI Command Reference

Below is a complete reference of all operational modes and commands you can run via `voice` or `voicemode`.

### 1. Dictation & Speech-to-Text

| Command | Description | Example |
|---|---|---|
| `voice --toggle` | Toggle push-to-talk recording. Starts recording if idle; if recording, stops, transcribes audio, and types/pastes text into the focused window. | `voice --toggle` |
| `voice --cancel` | Immediately cancel active background recording without transcribing or typing text. Cleans up audio buffers and lock files. | `voice --cancel` |
| `voice --terminal` | Run in interactive terminal-only mode. Press `Ctrl+B` to start recording, press `Ctrl+B` again to transcribe and paste. Press `Ctrl+C` to exit. | `voice --terminal` |
| `voice --watch` | Default action when no mode flag is given. Continuously monitors and streams background STT and TTS activity logs in real time. | `voice --watch` |
| `voice --check` | Test Faster-Whisper model loading and print the selected device and quantization backend, then exit. | `voice --check --allow-download` |

### 2. Text-to-Speech (TTS)

| Command | Description | Example |
|---|---|---|
| `voice --speak <text>` | Synthesize and speak the specified text. Pass `"-"` to stream text from standard input. | `voice --speak "Build completed successfully"`<br/>`cat note.txt \| voice --speak -` |
| `voice --speak-selection` | Synthesize and read text currently highlighted with the mouse (`wl-paste --primary`), falling back to system clipboard. If speech is already playing, toggles it off. | `voice --speak-selection` |
| `voice --stop-tts` | Immediately halt any active TTS audio playback process and clean up temporary files. | `voice --stop-tts` |
| `voice --list-tts-voices` | Print an alphabetical table of all available Kokoro voice IDs with language codes, gender, and default/secondary markers. | `voice --list-tts-voices` |
| `voice --tts-check` | Inspect TTS configuration, installed engines (`kokoro-onnx`, `edge-tts`), model paths, and voice tensor files. | `voice --tts-check` |
| `voice --download-tts-assets` | Download and verify Kokoro ONNX model weights and voice embeddings into `models/kokoro/`. | `voice --download-tts-assets` |

### 3. Latency & Performance Reporting

| Command | Options | Description | Example |
|---|---|---|---|
| `voice --report` | `[--format text\|html\|csv\|json]`<br/>`[--output PATH]`<br/>`[--open]`<br/>`[--since TIME]`<br/>`[--last N]`<br/>`[--model NAME]`<br/>`[--device DEV]` | Generate speech transcription latency report. Displays summary card (total runs, median wait, P90, mean RTF) and stage breakdowns (Load, Decode, Finalize, Insert). | `voice --report`<br/>`voice --report --open`<br/>`voice --report --format csv --output report.csv`<br/>`voice --report --since 24h`<br/>`voice --report --last 50` |
| `voice --metrics` | `[--json]` or `[--json-status]` | Print telemetry ledger summary (file path, disk size, total recorded rows, archives, median wait, P90 latency, mean RTF). Use `--json` for machine-readable output. | `voice --metrics`<br/>`voice --metrics --json` |

### 4. Diagnostics, Testing & Verification

| Command | Options | Description | Example |
|---|---|---|---|
| `voice --doctor` | `[--json]`<br/>`[--export-markdown PATH]` | Run system pre-flight diagnostic probe. Checks external binaries (`wtype`, `wl-clipboard`, `ffmpeg`, etc.), PipeWire/WirePlumber mic volume/mute state, model weights, keybind status, and daemon PIDs. | `voice --doctor`<br/>`voice --doctor --json` |
| `voice --verify` | `[--tier 1\|2\|3\|all]`<br/>`[--json]`<br/>`[--export-markdown PATH]` | Run end-to-end verification suite:<br/>• **Tier 1:** Static binary & permission checks<br/>• **Tier 2:** Automated synthetic audio loopback test (~3.3s)<br/>• **Tier 3:** Interactive window typing matrix<br/>• **all:** Runs all tiers sequentially | `voice --verify`<br/>`voice --verify --tier 2`<br/>`voice --verify --tier 1 --json` |
| `voice --status` | `[--json-status]` | Print active daemon status (`recording`, `transcribing`, or `idle`). With `--json-status`, prints structured JSON contract. | `voice --status`<br/>`voice --status --json-status` |
| `voice --test-beep` | — | Test audio cue feedback by sequentially playing start chime, reminder tick, and stop chime. | `voice --test-beep` |
| `voice --list-devices` | — | Query PortAudio hardware and list all available recording and playback audio devices with index numbers. | `voice --list-devices` |

### 5. Desktop Shortcuts & Keybinding Setup

| Command | Description | Example |
|---|---|---|
| `voice --install-hotkey` / `--install-hotkeys` | Automatically detect the desktop environment (Hyprland or GNOME) and install standard shortcuts. | `voice --install-hotkey` |
| `voice --install-hyprland` | Specifically append keybindings to `~/.config/hypr/custom/keybinds.lua` (preserving Stow symlinks) and reload Hyprland. | `voice --install-hyprland` |
| `voice --print-hyprland` | Print the exact Lua configuration block for Hyprland to stdout without modifying files. | `voice --print-hyprland` |

### 6. Emergency Recovery & Reset

| Command | Description | Example |
|---|---|---|
| `voice --kill` | Terminate active background workers (`SIGTERM` followed by `SIGKILL` after 2s), purge stale PID locks, and release virtual keys. | `voice --kill` |
| `voice --reset-keys` | Emergency release of any stuck virtual keyboard keys via `ydotool` (useful if typing was interrupted). | `voice --reset-keys` |

---

## Parameters & Configuration Reference

Every parameter can be passed directly as a command-line flag or defined globally in your environment (e.g. in `~/.bashrc`, `~/.zshrc`, or `~/.config/hypr/hyprland.conf`). Command-line flags always take precedence over environment variables.

### 1. Speech-to-Text (Whisper STT)

| Parameter / CLI Flag | Environment Variable | Type / Valid Range | Default | Description |
|---|---|---|---|---|
| `--model <name>` | `VOICE_STT_MODEL` | String: `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large-v1`, `large-v2`, `large-v3`, `turbo`, or custom HuggingFace repo / local directory path | `medium.en` | Faster-Whisper model size or path for speech recognition. |
| `--device <device>` | `VOICE_STT_DEVICE` | `cpu`, `cuda`, `auto` | `cpu` | Computation device for Whisper CTranslate2 inference. |
| `--compute-type <type>` | `VOICE_STT_COMPUTE_TYPE` | `int8`, `int8_float16`, `int16`, `float16`, `float32`, `auto` | `int8` | Model weight quantization precision (`int8` recommended for CPU). |
| `--language <lang>` | `VOICE_STT_LANGUAGE` | ISO-639-1 code (e.g. `en`, `es`, `fr`, `de`, `ja`, `zh`) or empty string for auto-detect | `en` | Spoken language for transcription. |
| `--beam-size <int>` | `VOICE_STT_BEAM_SIZE` | Integer $\ge 1$ (typically `1` to `5`) | `1` | Beam search width during Whisper decoding (`1` = greedy/fastest). |
| `--vad-filter` / `--no-vad-filter` | `VOICE_VAD_FILTER` | Boolean (`true` / `false`) | `true` | Silero VAD (Voice Activity Detection) filter to trim silence before STT inference. |
| `--chunk-seconds <sec>` | `VOICE_CHUNK_SECONDS` | Float $\ge 1.0$ seconds | `180.0` (3 min) | Audio chunk duration for background recording and concurrent processing. |
| — | `VOICE_MAX_RECORDING_SECONDS` | Float $> 0.0$ seconds | `1800.0` (30 min) | Safety hard cutoff ceiling for a single continuous recording session. |
| — | `VOICE_STT_TIMEOUT_SECONDS` | Float $> 0.0$ seconds | `300.0` (5 min) | Watchdog timeout for background transcription processes before aborting. |
| `--allow-download` | — | Flag (boolean) | `false` | Allow Faster-Whisper to download missing model weights from Hugging Face. |

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

### 6. Local Telemetry, Performance & Storage

| Parameter / Variable | Type | Default | Description |
|---|---|---|---|
| `VOICE_METRICS` | Boolean string (`on`/`off`, `1`/`0`) | `on` (enabled) | Primary kill switch for telemetry ledger. Set to `off`, `0`, `false`, or `no` to disable all ledger/status writes. |
| `VOICE_TELEMETRY` | Boolean string | Consulted if `VOICE_METRICS` is unset | Backward-compatible alias for `VOICE_METRICS`. |
| `XDG_STATE_HOME` | Directory path | `~/.local/state` | Root directory for persistent telemetry data (`$XDG_STATE_HOME/voicemode/metrics.jsonl`). |
| `XDG_RUNTIME_DIR` | Directory path | `/tmp/voice-stt-$UID` | Ephemeral runtime directory for daemon state (`$XDG_RUNTIME_DIR/voice-stt/status.json`, logs, and PID locks). |

---

## Daily Workflows & Usage Examples

### 1. Push-to-Talk Speech Dictation

```bash
# Toggle recording via CLI (same as pressing SUPER + SHIFT + M)
voice --toggle

# Cancel active recording if you change your mind:
voice --cancel

# Use a faster, smaller model on lower-spec machines:
voice --toggle --model small.en

# Paste instead of typing for complex text or web forms:
voice --toggle --output-method paste
```

### 2. Neural Screen Reading (TTS)

```bash
# Read mouse-selected text aloud (press again to stop):
voice --speak-selection

# Speak a custom message:
voice --speak "All system packages have been updated"

# Pipe text from any command into speech:
curl -s https://wttr.in?format=3 | voice --speak -

# Read text with a faster British voice:
voice --speak "Analyzing logs" --tts-voice bm_george --tts-speed 1.4

# Immediately stop speech playback:
voice --stop-tts
```

### 3. Monitoring & Latency Reporting

```bash
# View terminal summary report:
voice --report

# Open the fluid, dark-mode HTML latency dashboard in your browser:
voice --report --open

# Export the last 7 days of runs to a canonical CSV file:
voice --report --format csv --since 7d --output ~/latency.csv

# View quick metrics summary in terminal:
voice --metrics

# Query active daemon status as JSON (great for scripts or Waybar/Quickshell):
voice --status --json-status
```

### 4. Diagnostics & Recovery

```bash
# Run complete system probe:
voice --doctor

# Run automated synthetic loopback pipeline test:
voice --verify --tier 2

# Kill any orphaned processes and clear stale lock files:
voice --kill

# Emergency unstick keyboard keys if typing was interrupted:
voice --reset-keys
```

---

## Privacy Guarantee

- **Speech-to-Text:** 100% offline. Audio buffers are captured locally, transcribed via Faster-Whisper CTranslate2, and temporary audio files are unlinked immediately after insertion.
- **Text-to-Speech:** Default Kokoro engine runs 100% locally via ONNX Runtime without network access.
- *(Optional: Microsoft Edge TTS can be enabled via `--tts-backend edge`, which streams to Microsoft servers. It is disabled by default.)*
- **Telemetry:** Strictly local performance timing metrics (stage durations, character counts, model configuration). No transcript text, audio, clipboard content, or prompts are ever recorded or transmitted. See [`docs/telemetry.md`](docs/telemetry.md).

---

## License

The repository source code is licensed under the [MIT License](LICENSE). Third-party packages and neural weights maintain their respective licenses; see [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).
