# Testing Patterns

**Analysis Date:** 2026-09-18

## Test Framework

**Runner:**
- Not detected / None configured. The repository does not currently include an automated test framework or runner configuration in `pyproject.toml`.

**Assertion Library:**
- None configured (standard `assert` or `unittest` would be the Python default).

**Run Commands (Target / Proposed):**
```bash
pytest                                    # Proposed run command when tests are added
pytest --cov=voice --cov-report=term-missing # Coverage check
```

## Current Verification Workflows

In lieu of automated CI unit tests, the codebase relies on built-in diagnostic and testing CLI flags implemented directly in `voice.py`:

```bash
# 1. Verify Faster-Whisper model loading and hardware backend selection:
voicemode --check

# 2. Verify TTS runtime dependencies, models, and voices:
voicemode --tts-check

# 3. Check Kokoro voice embedding parsing and available voices:
voicemode --list-tts-voices

# 4. Verify sounddevice audio output by playing synthetic chime cues:
voicemode --test-beep

# 5. List available system audio input and output devices:
voicemode --list-devices

# 6. Test speech synthesis and ffplay playback:
voicemode --speak "This is a local TTS test."

# 7. Test interactive terminal dictation without desktop hotkeys:
voicemode --terminal
```

## Test File Organization

**Location:**
- Proposed location: `tests/` at repository root.
- Currently, zero test files exist (`tests/` directory is absent).

**Naming Convention:**
- `test_*.py` (e.g. `tests/test_recorder.py`, `tests/test_cli.py`, `tests/test_tts.py`)

**Proposed Structure:**
```text
tests/
├── conftest.py                   # Pytest fixtures and environment mocks
├── test_cli.py                   # Argument parsing and environment resolution tests
├── test_recorder.py              # Audio capture and PCM conversion unit tests
├── test_transcription.py         # Whisper model loading and fallback logic tests
├── test_tts.py                   # Text normalization and Kokoro/Edge dispatcher tests
└── test_platform.py              # X11/Wayland selection and key injection tests
```

## Test Structure

When writing automated tests for `voicemode`, follow this standard suite pattern:

```python
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import voice

class TestTextNormalization:
    def test_normalize_tts_text_replaces_em_dashes(self):
        raw = "Hello—world! It’s great."
        expected = "Hello, world! It's great."
        assert voice.normalize_tts_text(raw) == expected

    def test_normalize_tts_text_collapses_whitespace(self):
        raw = "Line one\n\n  line two   three"
        expected = "Line one line two three"
        assert voice.normalize_tts_text(raw) == expected
```

## Mocking

**Framework:**
- Standard library `unittest.mock` (`patch`, `MagicMock`, `PropertyMock`) or `pytest-mock`.

**Patterns:**

```python
@patch("voice.sd.InputStream")
def test_recorder_captures_frames(mock_input_stream):
    recorder = voice.Recorder(sample_rate=16000, input_device=None)
    recorder.start()
    assert recorder.recording is True
    mock_input_stream.assert_called_once()
```

**What to Mock:**
- Hardware access: `sounddevice.InputStream`, `sounddevice.OutputStream`, `sounddevice.query_devices`
- External processes: `subprocess.run`, `subprocess.Popen` (avoid invoking `xclip`, `xdotool`, `ydotool`, `ffplay`, `notify-send`, `gsettings` during tests)
- Heavy ML models: `faster_whisper.WhisperModel`, `kokoro_onnx.Kokoro`
- Network requests: `edge_tts.Communicate`

**What NOT to Mock:**
- Text processing: `normalize_tts_text()`, `edge_rate_from_speed()`, `parse_gsettings_list()`
- Audio math: `numpy` trigonometric sine wave math in `play_tone()`, PCM byte conversions in `Recorder.stop_to_wav()`
- State directory path computations: `STATE_DIR`, `voice_root()`

## Fixtures and Factories

**Test Data:**
- Synthetic audio frames created via `np.zeros((1600, 1), dtype=np.float32)` or synthetic sine arrays
- Mocked primary/clipboard selection strings

**Location:**
- Reusable fixtures should live in `tests/conftest.py`

## Coverage

**Requirements:**
- None enforced currently. Target baseline for future additions should be >80% coverage for CLI resolution, text normalization, and state management.

**View Coverage:**
```bash
pytest --cov=voice --cov-report=html
```

## Test Types

**Unit Tests:**
- Focus on pure utility functions:
  - `parse_device()`
  - `env_bool()`
  - `edge_rate_from_speed()`
  - `normalize_tts_text()`
  - `parse_gsettings_list()`
  - `tts_audio_suffix()`

**Integration Tests:**
- Validate file-based IPC and PID lifecycle:
  - `write_pid()`, `read_pid()`, `remove_pid()`, `process_alive()`
  - State directory generation under custom `XDG_RUNTIME_DIR`
  - Temporary audio file cleanup in `run_tts_background()` and `run_background_recording()`

**E2E Tests:**
- Manual execution only (using `--terminal`, `--check`, and `--tts-check`) due to requirement for physical Linux sound hardware and active graphical display sessions (X11/Wayland).

## Common Patterns

**Async Testing:**
- Use `pytest-asyncio` or standard `asyncio.run` when testing `synthesize_edge_tts`:

```python
import asyncio
from unittest.mock import patch, AsyncMock
import voice

def test_edge_tts_dispatch(tmp_path):
    with patch("edge_tts.Communicate") as mock_communicate:
        instance = mock_communicate.return_value
        instance.save = AsyncMock()
        asyncio.run(voice.synthesize_edge_tts("Test", tmp_path / "out.mp3", args))
        instance.save.assert_awaited_once()
```

**Error Testing:**
- Verify exception handling during backend fallback:

```python
def test_transcription_cpu_fallback_on_gpu_error(tmp_path):
    # Verify transcribe() retries on CPU int8 when model.transcribe raises an error
    pass
```

---

*Testing analysis: 2026-09-18*
