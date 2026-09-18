<!-- GSD:project-start source:PROJECT.md -->

## Project

**voicemode (Arch Linux / Hyprland)**

A lightweight, desktop-global speech-to-text dictation and text-to-speech utility for Linux. It provides push-to-talk transcription that types directly into the active focused window and on-demand neural text-to-speech reading of highlighted text, tailored specifically for Arch Linux running Hyprland on Wayland.

**Core Value:** Seamless, low-latency push-to-talk speech dictation and text-to-speech on Arch Linux + Hyprland using local models and native Wayland utilities.

### Constraints

- **Python Version**: Python 3.12 virtual environment via `uv` (binary wheel compatibility for AI inference runtimes).
- **Wayland Protocol**: Hyprland requires virtual keyboard protocols (`wtype`) or uinput (`ydotool`) for simulated keystrokes.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.11+ (`voice.py`, `pyproject.toml`) - Core application implementation, audio stream capture, transcription, synthesis orchestration, and CLI dispatch
- Bash / Shell (`scripts/download-kokoro-assets.sh`) - Helper script for downloading external Kokoro ONNX model weights and voice vectors

## Runtime

- CPython 3.11+ on Linux (POSIX / X11 / Wayland desktop)
- System audio subsystem via PortAudio (`libportaudio2`, `portaudio19-dev`)
- Audio synthesis and playback pipeline via FFmpeg (`ffplay`)
- `setuptools` (>=69) with `wheel` configured via `pyproject.toml`
- Lockfile: missing (relies on version bounds defined in `pyproject.toml`)

## Frameworks

- `setuptools` (>=69) - Packaging, distribution, and console script entry point definition (`voicemode = voice:main`, `voice = voice:main`)
- `faster-whisper` (>=1.2.1) - Local speech-to-text inference engine built on CTranslate2
- `kokoro-onnx` (==0.5.0, optional extra `[kokoro]`) - Local text-to-speech inference runtime using ONNX Runtime
- `sounddevice` (>=0.5.0) - PortAudio Python wrapper for microphone input streaming and synthetic tone generation
- `numpy` (>=2.0.2) - PCM buffer manipulation, clipping, scaling, and trigonometric wave synthesis for audio cues
- `soundfile` (>=0.14.0, optional extra `[kokoro]`) - WAV file encoding for Kokoro TTS audio output
- `edge-tts` (>=7.2.7, optional extra `[edge]`) - Microsoft Edge online text-to-speech streaming client
- `PyYAML` (>=6.0) - Configuration file parsing (used for Hermes TTS config fallback)
- Not detected / None configured (No test framework defined in `pyproject.toml`, no test suites present)
- `ruff` (`line-length = 120`, `target-version = "py311"` in `pyproject.toml`) - Linter and code formatter configuration

## Key Dependencies

- `faster-whisper` (`>=1.2.1`) - Core STT engine; loads Whisper weights via CTranslate2 for GPU or CPU transcription
- `sounddevice` (`>=0.5.0`) - Real-time microphone capture callback loop and audio cue tone generation
- `numpy` (`>=2.0.2`) - In-memory PCM buffer management, concatenation, normalization, and sine-wave generation
- `kokoro-onnx` (`==0.5.0`) - Default local TTS engine; performs phoneme conversion and acoustic ONNX inference
- `ctranslate2` - Native accelerated inference engine backing `faster-whisper`
- `soundfile` (`>=0.14.0`) - Audio export library for Kokoro synthesized output
- `PyYAML` (`>=6.0`) - Optional parser for `~/.hermes/config.yaml` to extract voice and speed defaults

## Configuration

- Runtime configuration is managed through environment variables with built-in fallbacks in `voice.py`:
- External configuration file:
- `pyproject.toml` - Declarative project specification, dependencies, optional extras, and entry points

## Platform Requirements

- Linux operating system (tested on Ubuntu with GNOME on X11 or Wayland)
- Python 3.11+
- System packages: `ffmpeg` (with `ffplay`), `xclip`, `xdotool`, `ydotool`, `wl-clipboard`, `libportaudio2`, `portaudio19-dev`, `libnotify-bin`, `wget`
- Desktop Linux workstation running GNOME desktop environment
- GNOME Settings Daemon custom keybindings (`org.gnome.settings-daemon.plugins.media-keys`)

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- Executable Python entry points: `snake_case.py` (`voice.py`)
- Shell scripts: `kebab-case.sh` (`scripts/download-kokoro-assets.sh`)
- Documentation: `UPPERCASE.md` (`README.md`, `LICENSE`, `docs/DEPENDENCIES.md`)
- Functions: `snake_case` verbs or descriptive actions (e.g. `load_model`, `transcribe`, `insert_text`, `play_cue`, `install_gnome_hotkey`)
- Predicates / Status queries: `snake_case` returning boolean (e.g. `process_alive`)
- Lifecycle / Action triggers: `start_<name>`, `stop_<name>`, `run_<name>`, `toggle_<name>` (e.g. `start_tts_background`, `run_background_recording`)
- Private / Internal methods: `_snake_case` with leading underscore (e.g. `_callback`, `_fd`, `_old_attrs` in `Recorder` and `TerminalKeys`)
- Local variables: `snake_case` nouns (e.g. `sample_rate`, `input_device`, `wav_path`, `model_state`)
- Constants / Globals: `SCREAMING_SNAKE_CASE` (e.g. `APP_NAME`, `STATE_DIR`, `PID_FILE`, `DEFAULT_TTS_VOICE`, `DEFAULT_KOKORO_LANG`)
- Signal / Control flags: `snake_case` boolean indicators (e.g. `stop_requested`, `should_delete`)
- Classes and Data structures: `PascalCase` (e.g. `ModelState`, `TtsDefaults`, `TerminalKeys`, `Recorder`)
- Type annotations: Standard Python typing using lowercase unions enabled by `from __future__ import annotations` (e.g. `Optional[int | str]`, `tuple[Path, float, bool]`)

## Code Style

- Tool: `ruff` (configured in `pyproject.toml`)
- Key settings:
- Indentation: 4 spaces per indentation level, Unix LF newlines
- Tool: `ruff`
- Key rules: Strict adherence to Python 3.11 syntax standards, clean type union syntax (`int | str`), avoidance of wildcard imports

## Import Organization

- None. Standard Python module imports relative to Python search path.

## Error Handling

- **Tiered Fallback Handling:**
- **Binary / Dependency Probing:**
- **Resource Cleanup in `finally` Blocks:**
- **Signal-to-Exception Transformation:**

## Logging

- Standard Python `print()` to `sys.stdout` and `sys.stderr` with `flush=True`.
- File appending to `$XDG_RUNTIME_DIR/voice-stt/voice.log` and `tts.log`.
- Explicit timestamps appended at session boundaries: `f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} start ---\n"`.
- Desktop user alerting via `notify(title, message, args)` wrapping `notify-send`.
- Polling log observer (`watch_log()`) tracking file byte offsets to print updates in real-time.

## Comments

- Module docstrings explain the high-level hotkeys and invocation model (`voice.py:1-7`).
- Inline comments explain non-obvious terminal manipulation, audio wave shaping, or OS quirks (e.g. `fade_frames` calculations, gsettings array formatting).
- Module level has comprehensive overview docstring.
- Class/function docstrings are used selectively; self-describing type signatures and clear parameter names are preferred.

## Function Design

- Single-responsibility functions ranging from 10 to 40 lines.
- Complex workflows (like `run_background_recording` or `run_terminal_mode`) encapsulate event loops within ~60 lines.
- Passing explicit `args: argparse.Namespace` across helper functions to propagate unified CLI options.
- Default arguments used for configurable parameters (e.g. `timeout: float = 0.1`, `shortcut: str = "ctrl+v"`).
- Process action functions return integer exit codes (`0` for success, `1` for error) for direct propagation to `sys.exit()` in `main()`.
- State queries return `Optional[T]` or typed tuples (e.g. `tuple[Path, float, bool]`, `tuple[str, str]`).

## Module Design

- `pyproject.toml` declares `voice:main` as the sole public console script entry point.
- Single-file module architecture without `__all__` declaration.
- Not applicable (no multi-module package structure).

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| CLI Parser & Dispatcher | Parses command-line flags, sets defaults from env/config, routes command mode | `voice.py:parse_args`, `voice.py:main` |
| Audio Capture (`Recorder`) | Captures mono microphone input asynchronously using SoundDevice streams | `voice.py:Recorder` |
| Audio Cue Synthesizer | Generates sine wave chimes with windowed fades for auditory state feedback | `voice.py:play_tone`, `voice.py:play_cue` |
| Whisper STT Transcriber | Manages Faster-Whisper model loading, compute precision fallback, and decoding | `voice.py:load_model`, `voice.py:transcribe` |
| Text Injector | Dispatches recognized transcripts to focused applications via typing or clipboard paste | `voice.py:insert_text`, `voice.py:type_text`, `voice.py:paste_clipboard` |
| Selection Reader | Extracts text currently highlighted in the GUI or from the system clipboard | `voice.py:read_x_selection`, `voice.py:selected_or_clipboard_text` |
| Kokoro TTS Synthesizer | Runs offline ONNX neural TTS and exports PCM audio to temporary WAV files | `voice.py:synthesize_kokoro_tts` |
| Edge TTS Synthesizer | Streams text to Microsoft Edge TTS online API and outputs temporary MP3 files | `voice.py:synthesize_edge_tts` |
| Audio Player | Spawns `ffplay` in headless mode to output synthesized audio to sound hardware | `voice.py:play_tts_audio` |
| Hotkey Installer | Writes GNOME Settings Daemon keybinding configurations via `gsettings` | `voice.py:install_gnome_hotkey`, `voice.py:set_gnome_custom_binding` |
| Activity Monitor | Continuously reads and displays appended lines from STT and TTS log files | `voice.py:watch_log` |

## Pattern Overview

- **Single-file Architecture:** All modules and logic reside in `voice.py` to maintain a standalone, single-command utility.
- **Detached Worker Pattern:** Background processes are spawned via `subprocess.Popen(start_new_session=True)` with redirected file logs and PID tracking in `$XDG_RUNTIME_DIR`.
- **POSIX Signal Coordination:** Uses `SIGUSR1` to trigger state transitions (recording -> stop & transcribe; speaking -> interrupt playback).
- **Graceful Hardware/Backend Fallbacks:** If GPU execution fails during Whisper transcription, automatically catches the exception and retries on CPU with `int8` quantization.

## Layers

- Purpose: Command routing, argument resolution, and environment parsing
- Location: `voice.py:1074-1232`
- Contains: `parse_args()`, `main()`, command branching
- Depends on: Standard library `argparse`, `os`, `sys`
- Used by: Desktop hotkeys, user terminal commands, background subprocesses
- Purpose: Audio capture, transcription, text extraction, speech synthesis, text injection
- Location: `voice.py:92-209`, `voice.py:275-317`, `voice.py:372-564`, `voice.py:616-720`, `voice.py:838-912`
- Contains: `Recorder`, `transcribe()`, `synthesize_tts()`, `run_background_recording()`, `run_tts_background()`
- Depends on: `faster-whisper`, `kokoro-onnx`, `edge-tts`, `sounddevice`, `numpy`, `soundfile`
- Used by: CLI and background workers
- Purpose: Interacting with display servers, desktop notifications, and keybindings
- Location: `voice.py:319-370`, `voice.py:372-502`, `voice.py:914-960`
- Contains: `display_server()`, `copy_to_clipboard()`, `type_text()`, `read_x_selection()`, `install_gnome_hotkey()`, `notify()`
- Depends on: External Linux binaries (`xclip`, `xdotool`, `ydotool`, `wl-paste`, `wl-copy`, `notify-send`, `gsettings`)
- Used by: Domain services to read GUI context and inject output

## Data Flow

### Primary STT Request Path (Dictation)

### Secondary TTS Flow Path (Read Selection)

- Stateless process execution coordinated entirely through filesystem artifacts in `$STATE_DIR` (`$XDG_RUNTIME_DIR/voice-stt/`):

## Key Abstractions

- Purpose: State machine and callback handler for continuous microphone input
- Pattern: Object-oriented wrapper around `sounddevice.InputStream` with frame buffering and WAV persistence
- Purpose: Encapsulates loaded Faster-Whisper model alongside runtime device and quantization metadata
- Pattern: Immutable dataclass
- Purpose: Interactive terminal raw key reader for local Ctrl+B mode
- Pattern: Python Context Manager altering POSIX terminal attributes with `termios` and restoring in `__exit__`

## Entry Points

- `voicemode = voice:main` (`pyproject.toml:49`)
- `voice = voice:main` (`pyproject.toml:50`)
- Invocation:

## Architectural Constraints

- **Single-Threaded Subprocess Decoupling:** Core long-running operations (recording, synthesis) run in isolated detached Python processes rather than background threads in a daemon to avoid Python GIL audio contention and crash propagation.
- **Operating System Dependency:** Hard dependency on Linux desktop environment features (POSIX signals, X11/Wayland display sockets, GNOME D-Bus).
- **Concurrency Limitation:** Single STT recorder and single TTS player at any given time, enforced by PID lockfiles.
- **Audio Device Locking:** Concurrent recording and tone cue playback require soundcard support for shared mixing (ALSA/PulseAudio/PipeWire).

## Anti-Patterns

### Heavy CLI Binary Forking for Standard Tasks

### Post-Recording Cold-Start Model Loading

### Monolithic Single-File Module

## Error Handling

- **Inference Hardware Fallback:** If GPU/auto execution crashes in `transcribe()`, automatically catches `Exception`, reloads model on CPU with `int8` quantization, and retries transcription (`voice.py:312-316`).
- **Graceful Tool Detection:** Before running system tools (`wl-copy`, `xclip`, `ydotool`, `xdotool`, `ffplay`), checks `shutil.which()` and active display variables, returning empty strings or `False` rather than raising uncaught exceptions.
- **Cleanup Guarantee:** Background scripts wrap active resources, PID files, and temporary WAV files in `try ... finally` blocks to ensure unlinking on process termination or `KeyboardInterrupt`.

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.agents/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
