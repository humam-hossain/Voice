# External Integrations

**Analysis Date:** 2026-09-18

## APIs & External Services

**Online Speech Synthesis:**
- Microsoft Edge TTS Service - Optional cloud speech synthesis accessed via `edge-tts`
  - SDK/Client: `edge-tts>=7.2.7`
  - Auth: None required (connects to the public Edge browser TTS endpoint)
  - Caveat: Text selected or pasted is transmitted over the internet to Microsoft cloud endpoints; not suitable for private or confidential data

## Data Storage

**Databases:**
- None (stateless runtime architecture)

**File Storage:**
- Local filesystem state directory:
  - Default: `$XDG_RUNTIME_DIR/voice-stt/` (with fallback to `/tmp/voice-stt-<uid>/voice-stt/`)
  - Tracked state files:
    - `recorder.pid` - Process ID of active background STT recorder (`voice.py:38`)
    - `tts.pid` - Process ID of active background TTS synthesizer/player (`voice.py:39`)
    - `voice.log` - Appended log for STT events and transcription results (`voice.py:40`)
    - `tts.log` - Appended log for TTS synthesis runs and player errors (`voice.py:41`)
  - Temporary audio buffers:
    - STT audio capture: `voice-<random>.wav` (or timestamped `voice-YYYYMMDD-HHMMSS.wav` when `--save-dir` is provided)
    - TTS synthesis cache: `voice-tts-<random>.wav` (Kokoro) or `voice-tts-<random>.mp3` (Edge)
    - TTS payload text: `voice-tts-<random>.txt` (ephemeral input file passed to detached background process)
  - Local model directory:
    - `models/kokoro/kokoro-v1.0.onnx` - Kokoro neural network weights
    - `models/kokoro/voices-v1.0.bin` - Precomputed speaker embedding dictionary

**Caching:**
- Faster-Whisper / Hugging Face model cache:
  - Stored in user cache directory (`~/.cache/huggingface/hub/`)
  - Model download can be disallowed using `--no-allow-download` (default enforcement via `local_files_only=not args.allow_download`)

## Authentication & Identity

**Auth Provider:**
- Custom / Local OS desktop security context:
  - POSIX user permissions for process signaling (`SIGUSR1`, `SIGTERM`, `killpg`)
  - Desktop session access to display servers (`$DISPLAY` for X11, `$WAYLAND_DISPLAY` for Wayland)
  - D-Bus session access to configure GNOME settings via `gsettings`

## Monitoring & Observability

**Error Tracking:**
- None integrated (failures emit to stderr and local notification banners)

**Logs:**
- Local file logging under `$XDG_RUNTIME_DIR/voice-stt/`:
  - `voice.log` - STT background recording sessions, timestamps, durations, and transcript text
  - `tts.log` - TTS background invocations, parameters, and ffplay process outputs
- Live log tailing:
  - `voicemode` (default CLI invocation) executes `watch_log()`, actively tailing both log streams with size-offset seeking

## CI/CD & Deployment

**Hosting:**
- Local user workstation installation (`pip install --user -e .`)
- Direct invocation via user bin PATH (`~/.local/bin/voicemode`, `~/.local/bin/voice`)

**CI Pipeline:**
- None configured (no GitHub Actions or CI configuration in repository)

## Environment Configuration

**Required env vars:**
- None required (all parameters provide self-contained defaults)

**Optional override variables:**
- `XDG_RUNTIME_DIR` - Base path for ephemeral runtime state directory
- `DISPLAY` - Required on X11 for `xclip`, `xdotool`, and `notify-send`
- `WAYLAND_DISPLAY` - Required on Wayland for `wl-copy`, `wl-paste`, `ydotool`
- `HERMES_CONFIG` - Custom path for loading external TTS defaults (`~/.hermes/config.yaml`)

**Secrets location:**
- No API keys or secrets are stored or needed for core operation (offline local models)

## Webhooks & Callbacks

**Incoming Signals:**
- OS signals handled by background processes:
  - `SIGUSR1`: Sent to the STT background process (`recorder.pid`) by `voicemode --toggle` to trigger audio capture shutdown and begin transcription (`voice.py:849`)
  - `SIGTERM` / `SIGUSR1`: Sent to the TTS background process (`tts.pid`) by `voicemode --stop-tts` or repeated `Super+T` to cancel playback (`voice.py:677`)

**Outgoing Commands & IPC:**
- Desktop notification dispatch:
  - Invokes `notify-send` binary via `subprocess.run` to display status updates (`voice.py:325`)
- Desktop key emulation:
  - X11: `xdotool type --clearmodifiers --delay <ms> -- <text>` or `xdotool key` (`voice.py:408`)
  - Wayland: `ydotool type --key-delay <ms> -- <text>` or `ydotool key` (`voice.py:398`)
- Clipboard & Selection interrogation:
  - X11: `xclip -selection primary -o` and `xclip -selection clipboard -o` (`voice.py:480`)
  - Wayland: `wl-paste --no-newline --primary` and `wl-paste --no-newline` (`voice.py:466`)
  - Copy back to clipboard: `xclip -selection clipboard` or `wl-copy` (`voice.py:377`)
- GNOME Hotkey registration:
  - Manipulates D-Bus via `gsettings set org.gnome.settings-daemon.plugins.media-keys` (`voice.py:926`)

---

*Integration audit: 2026-09-18*
