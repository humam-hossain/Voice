# Codebase Structure

**Analysis Date:** 2026-09-18

## Directory Layout

```text
/home/pera/github_repo/Voice/
├── .planning/codebase/           # Project codebase mapping and analysis documents
│   ├── ARCHITECTURE.md
│   ├── CONCERNS.md
│   ├── CONVENTIONS.md
│   ├── INTEGRATIONS.md
│   ├── STACK.md
│   ├── STRUCTURE.md
│   └── TESTING.md
├── docs/                         # Project documentation and reference notes
│   └── DEPENDENCIES.md           # External package licenses and dependency caveats
├── models/                       # (Ignored) Local model weights storage
│   └── kokoro/                   # Downloaded Kokoro ONNX model and voices
├── samples/                      # (Ignored) Audio test and evaluation artifacts
├── scripts/                      # Operational and maintenance shell scripts
│   └── download-kokoro-assets.sh # Script to download Kokoro v1.0 model and voices
├── LICENSE                       # MIT License declaration
├── README.md                     # Comprehensive project guide, setup, and usage documentation
├── pyproject.toml                # Build system metadata, package dependencies, and console scripts
└── voice.py                      # Core application source: monolithic CLI, STT, and TTS engine
```

## Directory Purposes

**`docs/`:**
- Purpose: Architecture notes, licensing documentation, and external component caveats
- Contains: Markdown documentation files
- Key files: `docs/DEPENDENCIES.md` (documents third-party package licensing, Kokoro GPLv3 phonemizer caveat, and Edge privacy considerations)

**`scripts/`:**
- Purpose: Automation scripts for environment setup and asset provisioning
- Contains: POSIX bash shell scripts
- Key files: `scripts/download-kokoro-assets.sh` (fetches `kokoro-v1.0.onnx` and `voices-v1.0.bin` via wget)

**`models/` (Gitignored):**
- Purpose: Storage for heavy neural network model weights that should not be committed to git
- Contains: ONNX model graphs and binary voice embedding arrays

**`samples/` (Gitignored):**
- Purpose: Destination for experimental audio output or recordings
- Contains: WAV and MP3 audio clips

**`.planning/codebase/`:**
- Purpose: GSD codebase intelligence documents describing stack, architecture, structure, quality, and concerns
- Contains: Markdown reference specifications

## Key File Locations

**Entry Points:**
- `voice.py`: Main executable file containing `main()` (`voice.py:1183`), invoked as `voicemode` or `voice`

**Configuration:**
- `pyproject.toml`: Package build definitions, dependency specifications (`[project.dependencies]`, `[project.optional-dependencies]`), and ruff configuration (`[tool.ruff]`)
- `voice.py`: Global constants and default configuration variables (`voice.py:35-58`)
- `~/.hermes/config.yaml` / `$HERMES_CONFIG`: Optional external configuration file parsed for TTS defaults (`voice.py:186`)

**Core Logic:**
- `voice.py:92-160`: `Recorder` class for microphone streaming via sounddevice
- `voice.py:227-273`: Tone generator for user audio cues
- `voice.py:285-317`: Faster-Whisper model loading and transcription
- `voice.py:372-460`: Text insertion and clipboard integration
- `voice.py:461-503`: Display server selection reading (`xclip`, `wl-paste`)
- `voice.py:505-553`: TTS synthesis dispatch (Kokoro and Edge backends)
- `voice.py:565-720`: TTS background worker execution and interruption
- `voice.py:812-912`: STT background recorder lifecycle and signal management
- `voice.py:914-960`: GNOME desktop shortcut installation

**Testing:**
- Currently missing. No dedicated test directory or test suites exist in the repository.

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (currently single `voice.py`)
- Shell scripts: `kebab-case.sh` (`scripts/download-kokoro-assets.sh`)
- Documentation: `UPPERCASE.md` (`README.md`, `LICENSE`, `docs/DEPENDENCIES.md`)

**Directories:**
- Top-level directories: `lowercase/` (`docs/`, `scripts/`, `models/`, `samples/`)
- Hidden system/planning directories: `.lowercase/` (`.planning/`, `.git/`)

**Symbols in Code (`voice.py`):**
- Global constants: `SCREAMING_SNAKE_CASE` (e.g. `APP_NAME`, `STATE_DIR`, `DEFAULT_TTS_VOICE`)
- Classes / Dataclasses: `PascalCase` (e.g. `Recorder`, `ModelState`, `TtsDefaults`, `TerminalKeys`)
- Functions and methods: `snake_case` (e.g. `resolve_sample_rate`, `transcribe`, `insert_text`)
- Private helper attributes/methods: `_leading_underscore` (e.g. `_callback`, `_fd`, `_old_attrs`)

## Where to Add New Code

**New Feature (e.g. New TTS Engine, Audio Preprocessor, or Hotkey Backend):**
- Add backend selection and implementation logic in `voice.py` (or refactor into a new `voicemode/` package).
- For a new TTS backend:
  - Add optional dependency in `pyproject.toml` under `[project.optional-dependencies]`.
  - Add synthesis function in `voice.py` following `synthesize_kokoro_tts()` and `synthesize_edge_tts()`.
  - Add backend choice to `parser.add_argument("--tts-backend", ...)`.

**New Component/Module (Package Refactoring):**
- If breaking up `voice.py` into a multi-file Python package:
  - Create `src/voicemode/` or `voicemode/`:
    - `voicemode/__init__.py`
    - `voicemode/cli.py` (CLI argument parsing and main dispatcher)
    - `voicemode/stt.py` (Recorder and Faster-Whisper transcription)
    - `voicemode/tts/` (`base.py`, `kokoro.py`, `edge.py`)
    - `voicemode/platform/` (`display.py`, `clipboard.py`, `gnome.py`)
    - `voicemode/audio.py` (tones, cues, sounddevice helpers)
  - Update `pyproject.toml` `py-modules = ["voice"]` -> `packages = ["voicemode"]` or standard package discovery.

**Testing:**
- Place new automated unit and integration tests in a new `tests/` directory at repository root:
  - `tests/test_recorder.py`: Unit tests for audio capture
  - `tests/test_cli.py`: Argument parser and flag resolution tests
  - `tests/test_platform.py`: Display server and clipboard mocks

**Utilities:**
- Shared helper functions belong near the top of the relevant functional section in `voice.py` or within a dedicated utility module `voicemode/utils.py`.

## Special Directories

**`.planning/`:**
- Purpose: Project planning, task orchestration, and codebase knowledge maps
- Generated: Semi-automated by GSD tools
- Committed: Yes

**`models/`:**
- Purpose: Stores local model weights (such as `models/kokoro/kokoro-v1.0.onnx`)
- Generated: Downloaded on-demand by `scripts/download-kokoro-assets.sh`
- Committed: No (explicitly ignored in `.gitignore`)

**`samples/`:**
- Purpose: Output directory for test recordings and audio benchmarks
- Generated: Created during evaluation
- Committed: No (explicitly ignored in `.gitignore`)

---

*Structure analysis: 2026-09-18*
