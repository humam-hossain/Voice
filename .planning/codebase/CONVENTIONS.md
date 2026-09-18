# Coding Conventions

**Analysis Date:** 2026-09-18

## Naming Patterns

**Files:**
- Executable Python entry points: `snake_case.py` (`voice.py`)
- Shell scripts: `kebab-case.sh` (`scripts/download-kokoro-assets.sh`)
- Documentation: `UPPERCASE.md` (`README.md`, `LICENSE`, `docs/DEPENDENCIES.md`)

**Functions & Methods:**
- Functions: `snake_case` verbs or descriptive actions (e.g. `load_model`, `transcribe`, `insert_text`, `play_cue`, `install_gnome_hotkey`)
- Predicates / Status queries: `snake_case` returning boolean (e.g. `process_alive`)
- Lifecycle / Action triggers: `start_<name>`, `stop_<name>`, `run_<name>`, `toggle_<name>` (e.g. `start_tts_background`, `run_background_recording`)
- Private / Internal methods: `_snake_case` with leading underscore (e.g. `_callback`, `_fd`, `_old_attrs` in `Recorder` and `TerminalKeys`)

**Variables:**
- Local variables: `snake_case` nouns (e.g. `sample_rate`, `input_device`, `wav_path`, `model_state`)
- Constants / Globals: `SCREAMING_SNAKE_CASE` (e.g. `APP_NAME`, `STATE_DIR`, `PID_FILE`, `DEFAULT_TTS_VOICE`, `DEFAULT_KOKORO_LANG`)
- Signal / Control flags: `snake_case` boolean indicators (e.g. `stop_requested`, `should_delete`)

**Types & Data Classes:**
- Classes and Data structures: `PascalCase` (e.g. `ModelState`, `TtsDefaults`, `TerminalKeys`, `Recorder`)
- Type annotations: Standard Python typing using lowercase unions enabled by `from __future__ import annotations` (e.g. `Optional[int | str]`, `tuple[Path, float, bool]`)

## Code Style

**Formatting:**
- Tool: `ruff` (configured in `pyproject.toml`)
- Key settings:
  - `line-length = 120` (`pyproject.toml:56`)
  - `target-version = "py311"` (`pyproject.toml:57`)
- Indentation: 4 spaces per indentation level, Unix LF newlines

**Linting:**
- Tool: `ruff`
- Key rules: Strict adherence to Python 3.11 syntax standards, clean type union syntax (`int | str`), avoidance of wildcard imports

## Import Organization

**Order:**
1. Future import: `from __future__ import annotations` (`voice.py:9`)
2. Standard library modules in alphabetical order (`argparse`, `ast`, `asyncio`, `os`, `re`, `select`, `shutil`, `signal`, `subprocess`, `sys`, `tempfile`, `termios`, `time`, `tty`, `wave`, `dataclasses`, `pathlib`, `typing`)
3. Third-party core dependencies (`numpy as np`, `sounddevice as sd`, `from faster_whisper import WhisperModel`)
4. Lazy / Local dynamic imports: Heavy or optional libraries are imported inside specific worker functions rather than top-level:
   - `import yaml` in `load_hermes_tts_defaults()` (`voice.py:191`)
   - `import edge_tts` in `synthesize_edge_tts()` (`voice.py:506`)
   - `import soundfile as sf`, `from kokoro_onnx import Kokoro` in `synthesize_kokoro_tts()` (`voice.py:518-519`)
   - `import importlib.metadata as importlib_metadata` in `print_tts_check()` (`voice.py:751`)

**Path Aliases:**
- None. Standard Python module imports relative to Python search path.

## Error Handling

**Patterns:**
- **Tiered Fallback Handling:**
  - When GPU/auto Whisper transcription fails, catches `Exception`, logs a warning, falls back to CPU with `int8` quantization, and retries (`voice.py:309-316`).
- **Binary / Dependency Probing:**
  - Before invoking system commands (`xclip`, `xdotool`, `ydotool`, `wl-paste`, `notify-send`, `ffplay`), executes `shutil.which()` and checks display environment variables (`$DISPLAY`, `$WAYLAND_DISPLAY`), failing safely with a fallback or false status rather than crashing (`voice.py:374-388`, `voice.py:463-477`).
- **Resource Cleanup in `finally` Blocks:**
  - Temporary files (`NamedTemporaryFile`), background streams, and PID tracking files are explicitly removed in `finally` blocks to guarantee no stale state remains on exit or failure (`voice.py:708-718`, `voice.py:900-911`).
- **Signal-to-Exception Transformation:**
  - In background workers, POSIX signals `SIGTERM` and `SIGUSR1` are mapped to raising `KeyboardInterrupt` or setting an atomic boolean flag (`stop_requested = True`) to allow graceful unwinding of streams (`voice.py:674-678`, `voice.py:845-850`).

## Logging

**Framework:**
- Standard Python `print()` to `sys.stdout` and `sys.stderr` with `flush=True`.
- File appending to `$XDG_RUNTIME_DIR/voice-stt/voice.log` and `tts.log`.

**Patterns:**
- Explicit timestamps appended at session boundaries: `f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} start ---\n"`.
- Desktop user alerting via `notify(title, message, args)` wrapping `notify-send`.
- Polling log observer (`watch_log()`) tracking file byte offsets to print updates in real-time.

## Comments

**When to Comment:**
- Module docstrings explain the high-level hotkeys and invocation model (`voice.py:1-7`).
- Inline comments explain non-obvious terminal manipulation, audio wave shaping, or OS quirks (e.g. `fade_frames` calculations, gsettings array formatting).

**Docstrings:**
- Module level has comprehensive overview docstring.
- Class/function docstrings are used selectively; self-describing type signatures and clear parameter names are preferred.

## Function Design

**Size:**
- Single-responsibility functions ranging from 10 to 40 lines.
- Complex workflows (like `run_background_recording` or `run_terminal_mode`) encapsulate event loops within ~60 lines.

**Parameters:**
- Passing explicit `args: argparse.Namespace` across helper functions to propagate unified CLI options.
- Default arguments used for configurable parameters (e.g. `timeout: float = 0.1`, `shortcut: str = "ctrl+v"`).

**Return Values:**
- Process action functions return integer exit codes (`0` for success, `1` for error) for direct propagation to `sys.exit()` in `main()`.
- State queries return `Optional[T]` or typed tuples (e.g. `tuple[Path, float, bool]`, `tuple[str, str]`).

## Module Design

**Exports:**
- `pyproject.toml` declares `voice:main` as the sole public console script entry point.
- Single-file module architecture without `__all__` declaration.

**Barrel Files:**
- Not applicable (no multi-module package structure).

---

*Convention analysis: 2026-09-18*
