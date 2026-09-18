# Technology Stack

**Analysis Date:** 2026-09-18

## Languages

**Primary:**
- Python 3.11+ (`voice.py`, `pyproject.toml`) - Core application implementation, audio stream capture, transcription, synthesis orchestration, and CLI dispatch

**Secondary:**
- Bash / Shell (`scripts/download-kokoro-assets.sh`) - Helper script for downloading external Kokoro ONNX model weights and voice vectors

## Runtime

**Environment:**
- CPython 3.11+ on Linux (POSIX / X11 / Wayland desktop)
- System audio subsystem via PortAudio (`libportaudio2`, `portaudio19-dev`)
- Audio synthesis and playback pipeline via FFmpeg (`ffplay`)

**Package Manager:**
- `setuptools` (>=69) with `wheel` configured via `pyproject.toml`
- Lockfile: missing (relies on version bounds defined in `pyproject.toml`)

## Frameworks

**Core:**
- `setuptools` (>=69) - Packaging, distribution, and console script entry point definition (`voicemode = voice:main`, `voice = voice:main`)
- `faster-whisper` (>=1.2.1) - Local speech-to-text inference engine built on CTranslate2
- `kokoro-onnx` (==0.5.0, optional extra `[kokoro]`) - Local text-to-speech inference runtime using ONNX Runtime
- `sounddevice` (>=0.5.0) - PortAudio Python wrapper for microphone input streaming and synthetic tone generation
- `numpy` (>=2.0.2) - PCM buffer manipulation, clipping, scaling, and trigonometric wave synthesis for audio cues
- `soundfile` (>=0.14.0, optional extra `[kokoro]`) - WAV file encoding for Kokoro TTS audio output
- `edge-tts` (>=7.2.7, optional extra `[edge]`) - Microsoft Edge online text-to-speech streaming client
- `PyYAML` (>=6.0) - Configuration file parsing (used for Hermes TTS config fallback)

**Testing:**
- Not detected / None configured (No test framework defined in `pyproject.toml`, no test suites present)

**Build/Dev:**
- `ruff` (`line-length = 120`, `target-version = "py311"` in `pyproject.toml`) - Linter and code formatter configuration

## Key Dependencies

**Critical:**
- `faster-whisper` (`>=1.2.1`) - Core STT engine; loads Whisper weights via CTranslate2 for GPU or CPU transcription
- `sounddevice` (`>=0.5.0`) - Real-time microphone capture callback loop and audio cue tone generation
- `numpy` (`>=2.0.2`) - In-memory PCM buffer management, concatenation, normalization, and sine-wave generation
- `kokoro-onnx` (`==0.5.0`) - Default local TTS engine; performs phoneme conversion and acoustic ONNX inference

**Infrastructure:**
- `ctranslate2` - Native accelerated inference engine backing `faster-whisper`
- `soundfile` (`>=0.14.0`) - Audio export library for Kokoro synthesized output
- `PyYAML` (`>=6.0`) - Optional parser for `~/.hermes/config.yaml` to extract voice and speed defaults

## Configuration

**Environment:**
- Runtime configuration is managed through environment variables with built-in fallbacks in `voice.py`:
  - `VOICE_STT_MODEL` (default: `"base"`) - Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`)
  - `VOICE_STT_DEVICE` (default: `"auto"`) - Target hardware device (`auto`, `cuda`, `cpu`)
  - `VOICE_STT_COMPUTE_TYPE` (default: `"auto"`) - Quantization precision (`auto`, `int8`, `float16`)
  - `VOICE_STT_LANGUAGE` (default: `""`) - Language code for Whisper transcription
  - `VOICE_STT_BEAM_SIZE` (default: `5`) - Decoding beam search size
  - `VOICE_INPUT_DEVICE` (default: system default) - Sound device input index or name
  - `VOICE_OUTPUT_METHOD` (default: `"type"`) - Transcript insertion method (`type`, `paste`, `terminal-paste`, `clipboard`)
  - `VOICE_TYPE_DELAY` (default: `2`) - Keystroke delay in milliseconds for typing output
  - `VOICE_BEEP` (default: `true`) - Enable or disable audio feedback cues
  - `VOICE_RECORDING_BEEP_INTERVAL` (default: `5`) - Interval in seconds for periodic recording reminder tone
  - `VOICE_BEEP_VOLUME` (default: `0.08`) - Amplitude multiplier (0.0 to 1.0) for audio cues
  - `VOICE_BEEP_OUTPUT_DEVICE` (default: system default) - Audio output device for cues
  - `VOICE_TTS_BACKEND` (default: `"kokoro"`) - Active TTS engine (`kokoro` or `edge`)
  - `VOICE_TTS_VOICE` (default: `"af_heart"`) - Voice identifier (`af_heart`, `bm_george`, `en-GB-RyanNeural`)
  - `VOICE_TTS_SPEED` (default: `2.0`) - Speech playback speed multiplier
  - `VOICE_KOKORO_MODEL` (default: `models/kokoro/kokoro-v1.0.onnx`) - Path to Kokoro ONNX model
  - `VOICE_KOKORO_VOICES` (default: `models/kokoro/voices-v1.0.bin`) - Path to Kokoro voices bin
  - `VOICE_KOKORO_LANG` (default: `"en-us"`) - Kokoro language identifier
  - `VOICE_KOKORO_TRIM` (default: `false`) - Silence trimming toggle
- External configuration file:
  - `HERMES_CONFIG` (default: `~/.hermes/config.yaml`) - Read optionally for TTS voice and speed fallback defaults

**Build:**
- `pyproject.toml` - Declarative project specification, dependencies, optional extras, and entry points

## Platform Requirements

**Development:**
- Linux operating system (tested on Ubuntu with GNOME on X11 or Wayland)
- Python 3.11+
- System packages: `ffmpeg` (with `ffplay`), `xclip`, `xdotool`, `ydotool`, `wl-clipboard`, `libportaudio2`, `portaudio19-dev`, `libnotify-bin`, `wget`

**Production:**
- Desktop Linux workstation running GNOME desktop environment
- GNOME Settings Daemon custom keybindings (`org.gnome.settings-daemon.plugins.media-keys`)

---

*Stack analysis: 2026-09-18*
