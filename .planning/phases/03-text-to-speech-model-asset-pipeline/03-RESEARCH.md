# Phase 3: Text-to-Speech & Model Asset Pipeline - Research

**Researched:** 2026-09-19
**Domain:** Offline Neural Text-to-Speech (Kokoro ONNX), Wayland Selection Capture, and Headless Audio Playback
**Confidence:** HIGH

---

## User Constraints

*(The following implementation decisions are quoted verbatim from `03-CONTEXT.md` §decisions)*

### Kokoro Model Asset Management
- **D-01:** Store Kokoro ONNX model weights (`kokoro-v1.0.onnx`, ~330MB) and voice embeddings (`voices-v1.0.bin`, ~28MB) in the repository at `models/kokoro/`, maintaining a self-contained local workspace.
- **D-02:** Provide a single canonical Python downloader `voice.py --download-tts-assets` using `urllib.request` streaming with console progress reporting. `scripts/download-kokoro-assets.sh` serves as a lightweight shell wrapper with curl/wget auto-detection.
- **D-03:** Fast existence and size guards (>300MB onnx, >20MB voices) for standard runtime checks, combined with a comprehensive full ONNX model instantiation and voice key inspection during `voice.py --tts-check`.

### Wayland Selection Capture & Text Normalization
- **D-04:** Prioritize Wayland primary selection (`wl-paste --primary`) with fallback to standard clipboard (`wl-paste`) when no text is highlighted.
- **D-05:** Enforce a strict 1.0s timeout on all `wl-paste` commands to protect against unresponsive or hanging Wayland client applications.
- **D-06:** Bound maximum text length to 5,000 characters (~1,000 words / ~6 min speech) with a desktop warning toast if truncated, configurable via `VOICE_TTS_MAX_CHARS`.
- **D-07:** Implement a conservative text normalization pipeline (`normalize_tts_text`):
  - Strip ANSI terminal escape sequences.
  - Strip markdown symbols (backticks, code fences, heading hashes, list bullets).
  - Simplify long URLs to domain summaries (e.g. read domain rather than raw query strings).
  - Format code identifiers: convert underscores in `snake_case` to spaces and slashes in paths to pauses.
  - Smart line pauses: convert unpunctuated line breaks into pauses/periods before collapsing whitespace.
- **D-08:** Execute normalization, length validation, and empty-string checks upfront in the parent process before spawning the background worker. Abort immediately with feedback if the resulting text is empty.
- **D-09:** Leave the regular Wayland clipboard untouched when reading highlighted primary text (protecting existing copied passwords/code). Leave highlighted on-screen selection intact.
- **D-10:** Support `--speak -` to read and speak text piped directly from standard input (stdin).

### User Feedback & Notifications
- **D-11:** Empty selection or missing text triggers both a desktop notification and a subtle low double-tone auditory error chime (`play_cue(args, "error")`).
- **D-12:** Display an informative desktop toast when playback starts, distinguishing text source and providing a preview snippet (e.g. `Speaking selection: "..."` vs `Speaking clipboard (fallback): "..."`).

### Voice & Speech Defaults
- **D-13:** Default Kokoro voice set to `af_heart` (American female); secondary voice remains `bm_george` (British male).
- **D-14:** Default speech playback speed set to `1.2x` (fallback when not configured via `~/.hermes/config.yaml` or `VOICE_TTS_SPEED`). Explicitly clamp speed to `[0.5, 2.0]` for the Kokoro backend to satisfy ONNX runtime assertions.
- **D-15:** Strict offline-first privacy: Never automatically fall back to cloud Microsoft Edge TTS when Kokoro models are missing; notify that local assets are missing with download guidance.
- **D-16:** Keep `trim=False` default for Kokoro to preserve natural inter-sentence breathing pauses.

### Audio Playback & Lifecycle Management
- **D-17:** Tag `ffplay` audio streams in PipeWire with `PULSE_PROP_application.name = "voicemode"` and `PULSE_PROP_media.name = "voicemode-tts"`, matching Phase 1 STT conventions.
- **D-18:** Provide silent cut-off upon interruption (`Super+T` or `--stop-tts`) with a brief "Speech stopped" desktop notification toast.
- **D-19:** Clean `ffplay` termination filter: Catch `subprocess.CalledProcessError` with returncodes `-15` (SIGTERM), `-2` (SIGINT), or `255` during intentional user interruption and treat as clean completion to suppress bogus error toasts.
- **D-20:** Opportunistic garbage collection: Purge orphaned temporary audio and text files (`voice-tts-*.{wav,mp3,txt}`) in `STATE_DIR` older than 30 minutes on startup and idle stops.

### The Agent's Discretion
- Concrete frequency and duration values for the new `"error"` cue chime in `play_cue` (e.g. 300Hz for 80ms, 200Hz for 100ms).
- Layout and styling of the console progress indicator in `voice.py --download-tts-assets`.

---

## Standard Stack & Dependencies

### Core Python Runtime & Packages
- **Python**: CPython 3.12 managed via `uv` in `.venv` [VERIFIED: `AGENTS.md` line 13, `pyproject.toml` line 10 `requires-python = ">=3.12"`].
- **kokoro-onnx**: `0.5.0` [VERIFIED: `pyproject.toml` line 36 `"kokoro-onnx==0.5.0"`, confirmed installed in virtualenv via `voice.py --tts-check`]. Backed by ONNX Runtime (`onnxruntime==1.20.1`) and `espeak-ng` phonemizer python bindings.
- **soundfile**: `>=0.14.0` [VERIFIED: `pyproject.toml` line 37 `"soundfile>=0.14.0"`, confirmed installed version `0.14.0`]. Used to write 24kHz float32 NumPy arrays from Kokoro into temporary WAV containers (`soundfile.write(output_path, audio, sample_rate)`).
- **sounddevice**: `>=0.5.0` [VERIFIED: `pyproject.toml` line 31 `"sounddevice>=0.5.0"`]. PortAudio bindings for synthesizing cue tones (`play_tone`, `play_cue`).
- **numpy**: `>=2.0.2` [VERIFIED: `pyproject.toml` line 29 `"numpy>=2.0.2"`]. Array operations, trigonometric sine wave generation for cues, and loading Kokoro voice vectors (`np.load(voices_path)`).
- **urllib.request**: Python 3 standard library [VERIFIED: built-in]. Canonical HTTP streaming client for asset downloads with automatic 302 redirect following.

### System Binaries & Display Tools
- **ffplay**: `/usr/bin/ffplay` [VERIFIED: `which ffplay` returned `/usr/bin/ffplay`]. Headless audio player for temporary WAV files spawned with `-nodisp -autoexit -hide_banner -loglevel error`.
- **wl-clipboard (`wl-paste`, `wl-copy`)**: `/usr/bin/wl-paste`, `/usr/bin/wl-copy` [VERIFIED: `which wl-paste wl-copy` returned `/usr/bin/wl-paste` and `/usr/bin/wl-copy`]. Native Wayland tools for clipboard and primary selection extraction.
- **notify-send**: `/usr/bin/notify-send` from `libnotify-bin` [VERIFIED: `which notify-send` returned `/usr/bin/notify-send`]. Desktop notifications for feedback toasts.
- **curl & wget**: `/usr/bin/curl`, `/usr/bin/wget` [VERIFIED: `which curl wget` returned `/usr/bin/curl` and `/usr/bin/wget`]. Auto-detected fallback tools in `scripts/download-kokoro-assets.sh`.

### Model Assets & Endpoints
- **Model weights path**: `models/kokoro/kokoro-v1.0.onnx` [VERIFIED: `voice.py` line 264 `default_kokoro_model_path()`, `scripts/download-kokoro-assets.sh` line 9].
  - **Remote URL**: `https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx` [VERIFIED: `scripts/download-kokoro-assets.sh` line 10].
  - **Content-Length**: `325,532,387` bytes (~325.5 MB) [VERIFIED: curl HTTP/2 HEAD request returned `content-length: 325532387`].
  - **Runtime Size Guard**: `> 300,000,000` bytes (>300 MB) [VERIFIED: `03-CONTEXT.md` D-03].
- **Voice embeddings path**: `models/kokoro/voices-v1.0.bin` [VERIFIED: `voice.py` line 268 `default_kokoro_voices_path()`, `scripts/download-kokoro-assets.sh` line 12].
  - **Remote URL**: `https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin` [VERIFIED: `scripts/download-kokoro-assets.sh` line 13].
  - **Content-Length**: `28,214,398` bytes (~28.2 MB) [VERIFIED: curl HTTP/2 HEAD request returned `content-length: 28214398`].
  - **Runtime Size Guard**: `> 20,000,000` bytes (>20 MB) [VERIFIED: `03-CONTEXT.md` D-03].
- **Storage Strategy**: Stored under repository `models/kokoro/` [VERIFIED: `03-CONTEXT.md` D-01]. The directory `models/` is already ignored in `.gitignore` line 21 [VERIFIED: `.gitignore` line 21 `models/`].

---

## Architecture & Implementation Patterns

### 1. Unified Asset Downloader & Verification (`voice.py --download-tts-assets` & `scripts/download-kokoro-assets.sh`)
- **Canonical Python Downloader**:
  - Add `--download-tts-assets` flag to `voice.py:parse_args`.
  - Downloads assets using `urllib.request.urlopen(req)` with a custom User-Agent (`voicemode/0.1.0`).
  - Streams chunks (e.g. 64 KiB chunks) directly into `.tmp` sibling files (`kokoro-v1.0.onnx.tmp`, `voices-v1.0.bin.tmp`).
  - Displays dynamic console progress with carriage return `\r` (e.g. `[kokoro-v1.0.onnx] 124.5 MB / 325.5 MB [38.2%] 14.2 MB/s`).
  - Upon download completion, performs strict byte count verification against size guards (`> 300MB` for model, `> 20MB` for voices).
  - Uses atomic replacement (`temp_path.replace(dest_path)`) to guarantee uncorrupted files on disk.
  - Automatically verifies the downloaded models by instantiating `kokoro_onnx.Kokoro` and reading voice vectors.
- **Shell Wrapper**:
  - `scripts/download-kokoro-assets.sh` detects Python virtualenv (`${VENV_PYTHON}`) and invokes `python voice.py --download-tts-assets`.
  - If Python is unavailable, falls back to `curl -L -C - -o` or `wget -c -O` with automatic binary detection.

### 2. Upfront Selection Processing & Normalization Flow
```
User presses Super+T (or runs `voice --speak-selection`)
  │
  ├─> Active TTS playing? (read_pid(TTS_PID_FILE))
  │     └─> YES: stop_tts() immediately (silent kill, notify "Speech stopped"), exit 0 [Toggle behavior]
  │
  ├─> Capture Text:
  │     ├─> wl-paste --no-newline --primary (timeout=1.0s)
  │     └─> Fallback: wl-paste --no-newline (timeout=1.0s)
  │
  ├─> Text Empty?
  │     └─> YES: play_cue("error"), notify("Voice TTS", "No selected text..."), exit 1
  │
  ├─> Normalize Text: normalize_tts_text(raw_text)
  │     ├─> Strip ANSI sequences
  │     ├─> Markdown link extraction: [text](url) -> text
  │     ├─> URL simplification: https://domain.com/path -> domain.com
  │     ├─> Markdown formatting cleanup: headings, bullets, code fences, bold/italic
  │     ├─> Smart line pauses: line ends without punctuation -> append ". "
  │     ├─> Snake_case formatting: identifier_name -> identifier name
  │     ├─> Path slashes: /dir/file -> dir, file
  │     └─> Collapse multiple spaces & trim
  │
  ├─> Normalized Text Empty?
  │     └─> YES: play_cue("error"), notify("Voice TTS", "No text to speak."), exit 1
  │
  ├─> Length Bounding (DEFAULT_TTS_MAX_CHARS = 5000):
  │     └─> len(text) > 5000: truncate to 5000, notify warning toast
  │
  ├─> Asset Guard (when tts_backend == "kokoro"):
  │     └─> Model or voices missing or below size guard?
  │           └─> notify error with download guidance, play_cue("error"), exit 1 [Strict offline privacy]
  │
  ├─> Visual Feedback:
  │     └─> notify("Voice TTS", f'Speaking {source}: "{preview}"')
  │
  └─> Spawn Background Worker (start_tts_background):
        ├─> Write normalized text to STATE_DIR/voice-tts-<uuid>.txt
        └─> Detach subprocess: python voice.py --tts-background ... (start_new_session=True)
```

### 3. Background Inference & Headless Playback Architecture
- **Worker Process (`run_tts_background`)**:
  - Registers `SIGTERM` and `SIGUSR1` signal handlers to raise `KeyboardInterrupt`.
  - Writes PID to `TTS_PID_FILE` (`$STATE_DIR/tts.pid`).
  - Reads text from temporary file in `STATE_DIR`.
  - Clamps `tts_speed` explicitly to `[0.5, 2.0]` [VERIFIED: `03-CONTEXT.md` D-14, avoids Kokoro ONNX assertion error].
  - Calls `synthesize_kokoro_tts` (`kokoro.create(text, voice=args.tts_voice, speed=args.tts_speed, lang=args.kokoro_lang, trim=args.kokoro_trim)`).
  - Encodes 24kHz audio via `soundfile.write(audio_path, audio, 24000)` into `STATE_DIR/voice-tts-<uuid>.wav`.
  - Launches `play_tts_audio(audio_path)` with PipeWire Pulse tags:
    - `env["PULSE_PROP_application.name"] = "voicemode"`
    - `env["PULSE_PROP_media.name"] = "voicemode-tts"`
  - Executes `ffplay -nodisp -autoexit -hide_banner -loglevel error <audio_path>`.
  - In `finally:` block, guarantees unlinking of both temporary text and WAV files, and removes `TTS_PID_FILE`.

### 4. Silent Interruption & Process Group Signaling
- When `--stop-tts` or toggle (`Super+T`) is invoked:
  - Reads PID from `TTS_PID_FILE`.
  - Because `start_tts_background` runs with `start_new_session=True`, the worker process is its own process group leader (`pgid == pid`).
  - Sends `os.killpg(pid, signal.SIGTERM)`.
  - Both the Python background worker and the running `ffplay` child receive `SIGTERM`.
  - **Clean termination filter (D-19)**: In `play_tts_audio`, catches `subprocess.CalledProcessError`. If `exc.returncode in (-signal.SIGTERM, -signal.SIGINT, -15, -2, 255, 143, 130)`, converts the exception to `KeyboardInterrupt`.
  - `run_tts_background` handles `KeyboardInterrupt` as clean exit code `0`, avoiding error toasts or tracebacks.
  - Notifies user with desktop toast: `"Speech stopped."` [VERIFIED: `03-CONTEXT.md` D-18].

### 5. Opportunistic State Garbage Collection (`cleanup_stale_tts_files`)
- On startup and in `stop_tts`:
  - Scans `STATE_DIR` (`$XDG_RUNTIME_DIR/voice-stt/` or `~/.local/state/voice-stt/`).
  - Identifies files matching `voice-tts-*.{wav,mp3,txt}`.
  - Checks modification time (`st_mtime`). If older than 1800 seconds (30 minutes), removes the file safely in a `try...except OSError` block [VERIFIED: `03-CONTEXT.md` D-20].

---

## Validation Architecture

### Dimension 8 Test Commands & Verification Points

```bash
# 1. Run complete unit test suite (STT + TTS pipelines)
uv run python -m unittest discover tests

# 2. Verify TTS flags and asset check output
uv run python voice.py --tts-check

# 3. Download and verify Kokoro ONNX model weights and voice embeddings
uv run python voice.py --download-tts-assets

# 4. List all available Kokoro voices
uv run python voice.py --list-tts-voices

# 5. Test pipeline text synthesis via stdin
echo "Kokoro neural text to speech is running on Arch Linux." | uv run python voice.py --speak -

# 6. Test speech synthesis with explicit voice and speed
uv run python voice.py --speak "Testing speed clamping and PipeWire stream tagging." --tts-voice af_heart --tts-speed 1.2

# 7. Test immediate playback cancellation
uv run python voice.py --speak "This is a long passage of text intended to be interrupted immediately by the stop command." &
sleep 1
uv run python voice.py --stop-tts

# 8. Test Wayland primary selection reading (simulate highlight in terminal/editor)
wl-copy --primary "Selected text from Wayland primary clipboard."
uv run python voice.py --speak-selection
```

### Verification Points Matrix
| Success Criteria | Manual / Automated Test | Expected Result |
|---|---|---|
| **CRIT-1**: Kokoro weights & voices downloaded and verified | `voice.py --tts-check` | Returns exit code 0. Reports `kokoro onnx status: verified (50+ voices loaded)`. Model >300MB, voices >20MB. |
| **CRIT-2**: Primary selection captured and played back | `wl-copy --primary "Hello" && voice.py --speak-selection` | `wl-paste --primary` captures text; desktop toast `"Speaking selection: 'Hello'"` appears; audio outputs via PipeWire to `ffplay`. |
| **CRIT-2a**: Fallback to standard clipboard | `wl-copy "Fallback text"` (empty primary) `&& voice.py --speak-selection` | Desktop toast `"Speaking clipboard (fallback): 'Fallback text'"` appears; audio synthesizes and plays. |
| **CRIT-2b**: Empty selection handling | Run with empty primary & clipboard | Dual-tone error chime (300Hz -> 200Hz) plays; desktop notification `"No selected text or clipboard text."`; returns code 1; no worker spawned. |
| **CRIT-2c**: Stdin `--speak -` support | `echo "Stdin speech" \| voice.py --speak -` | Reads stdin, normalizes, announces `"Speaking stdin: 'Stdin speech'"`, synthesizes and plays. |
| **CRIT-3**: Immediate halt via `--stop-tts` | `voice.py --stop-tts` while playing | Active `ffplay` process halts immediately; desktop notification `"Speech stopped."`; returns code 0 without error toasts. |
| **CRIT-3a**: Seamless toggle on hotkey | `voice.py --speak-selection` while playing | Detects existing TTS PID; halts active playback cleanly; exits code 0. |
| **NORM-1**: Text normalization | Unit tests in `tests/test_tts_pipeline.py` | ANSI stripped; markdown stripped; URLs simplified to domains; snake_case spaced; path slashes paused; unpunctuated line breaks given periods. |
| **BOUND-1**: 5000 character length limit | Unit tests with 6000 character string | Truncated to 5000 characters; warning toast issued. |
| **OFFLINE-1**: Privacy guarantee | Asset missing check | When Kokoro model absent, prints guidance to run `--download-tts-assets`; never falls back to Edge TTS. |

---

## Don't Hand-Roll

| Problem | Recommended Solution | Anti-Pattern to Avoid |
|---|---|---|
| HTTP file streaming with progress | Use standard library `urllib.request.urlopen` with chunk loop and carriage return `\r` | Adding heavy dependencies (`requests`, `httpx`, `tqdm`); running unbounded `urllib.request.urlretrieve` without progress or size checks. |
| Atomic file persistence | Write to `.tmp` file and call `Path.replace()` | Writing directly to target path; interrupted downloads leave corrupted half-downloaded ONNX models on disk. |
| Voice enumeration | Call `kokoro.get_voices()` or `np.load(voices_path).keys()` | Hardcoding voice lists in Python dicts or scraping README files. |
| Audio playback to PipeWire | Execute `ffplay` with `-nodisp -autoexit` and `PULSE_PROP_*` environment variables | Hand-rolling custom PortAudio playback loops in Python (causes GIL contention and buffer underruns during disk I/O). |
| Text normalization | Conservative sequential regex passes (ANSI -> Markdown -> URLs -> Punctuation -> Code -> Slashes) | Using full pandoc/mistune AST parsers that strip semantic text content or fail on malformed terminal buffers. |
| Interruption handling | POSIX process group `os.killpg(pid, signal.SIGTERM)` with `start_new_session=True` | Killing only parent Python PID, leaving orphaned `ffplay` processes continuing to play audio. |

---

## Common Pitfalls & Edge Cases

### 1. Kokoro Speed Parameter Assertion Crash
- **Pitfall**: `kokoro-onnx` contains an explicit Python assertion in `create()`:
  `assert speed >= 0.5 and speed <= 2.0, "Speed should be between 0.5 and 2.0"` [VERIFIED: `kokoro_onnx/__init__.py:create`].
  If a user configures `VOICE_TTS_SPEED=2.5` or `0.3`, `kokoro-onnx` raises an uncaught `AssertionError` which crashes background synthesis.
- **Remedy**: Always clamp `speed` before passing to `kokoro.create()`:
  `clamped_speed = max(0.5, min(2.0, float(args.tts_speed)))` [VERIFIED: `03-CONTEXT.md` D-14].

### 2. Upstream wtype / wl-paste Hanging Wayland Clients
- **Pitfall**: If an unresponsive Wayland application holds the selection clipboard or crashes, `wl-paste --primary` can hang indefinitely, locking the user's terminal or hotkey trigger.
- **Remedy**: In `read_x_selection`, enforce `timeout=1.0` on `subprocess.run` [VERIFIED: `03-CONTEXT.md` D-05]. Catch `subprocess.TimeoutExpired` and return `""`.

### 3. Bogus Desktop Error Toasts on User Interruption (`SIGTERM`)
- **Pitfall**: When the user presses `Super+T` or runs `--stop-tts` while `ffplay` is playing, `os.killpg` delivers `SIGTERM` (signal 15) to `ffplay`. `subprocess.run(check=True)` catches exit code `-15` and raises `subprocess.CalledProcessError`. Without filtering, `run_tts_background` treats this as an unhandled error and displays an obnoxious desktop notification: `"Command '['ffplay', ...] died with <Signals.SIGTERM: 15>"`.
- **Remedy**: Filter `exc.returncode in (-signal.SIGTERM, -signal.SIGINT, -15, -2, 255, 143, 130)` in `play_tts_audio` and transform into `KeyboardInterrupt`, allowing `run_tts_background` to exit cleanly with code 0 [VERIFIED: `03-CONTEXT.md` D-19].

### 4. Markdown Italic Regex Mangling `snake_case` Variables
- **Pitfall**: A naive markdown italic regex `_([^_]+)_` matches underscores inside programming identifiers:
  e.g. `calculate_total_amount(order_id)` -> `calculate total amount(orderid)`.
- **Remedy**: Require word boundaries for markdown emphasis `(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)` or convert `snake_case` identifiers `(?<=\w)_(?=\w)` to spaces BEFORE handling markdown formatting.

### 5. URL Slash Mangling
- **Pitfall**: If path slash replacement `/(?=[a-zA-Z])` runs before URL simplification, URLs like `https://github.com/repo` become `https:, github.com, repo` and are no longer matched by the URL regex.
- **Remedy**: Enforce strict pass ordering: Markdown links `[text](url)` -> Raw URLs `https://...` simplified to domain -> Path slashes `/path/to` converted to comma pauses.

### 6. Leftover Lockfiles and Orphaned WAV Files
- **Pitfall**: If the system reboots or the process is forcefully killed (`SIGKILL`), stale PID files or gigabytes of temporary WAV files accumulate in `STATE_DIR`.
- **Remedy**: Implement opportunistic cleanup `cleanup_stale_tts_files` to purge `voice-tts-*` files older than 30 minutes on startup and shutdown [VERIFIED: `03-CONTEXT.md` D-20]. Always check `process_alive(pid)` before trusting `TTS_PID_FILE`.

---

## Code Examples & API Signatures

### 1. Kokoro Model Instantiation & Audio Synthesis
```python
# [VERIFIED: kokoro_onnx 0.5.0 API via python inspect]
from kokoro_onnx import Kokoro
import soundfile as sf
import numpy as np

# Instantiation
model_path = "/home/pera/github_repo/Voice/models/kokoro/kokoro-v1.0.onnx"
voices_path = "/home/pera/github_repo/Voice/models/kokoro/voices-v1.0.bin"
kokoro = Kokoro(model_path, voices_path)

# Enumerate voices
voice_names: list[str] = kokoro.get_voices()  # returns list of strings like ['af_heart', 'bm_george', ...]

# Generate audio (SAMPLE_RATE is 24000 Hz)
audio, sample_rate = kokoro.create(
    text="Synthesized text to speak",
    voice="af_heart",
    speed=1.2,       # Clamped between 0.5 and 2.0
    lang="en-us",
    trim=False,      # D-16: preserve natural inter-sentence breathing pauses
)

# audio is np.ndarray with dtype=float32
sf.write("output.wav", audio, sample_rate)
```

### 2. PipeWire Stream Tagged Playback with Interruption Filter
```python
# [VERIFIED: 03-CONTEXT.md D-17, D-19]
import os
import signal
import subprocess
from pathlib import Path

def play_tts_audio(audio_path: Path) -> None:
    ffplay = shutil.which("ffplay")
    if not ffplay:
        raise RuntimeError("ffplay is required to play TTS audio")
    
    pulse_env = os.environ.copy()
    pulse_env["PULSE_PROP_application.name"] = "voicemode"
    pulse_env["PULSE_PROP_media.name"] = "voicemode-tts"
    
    cmd = [ffplay, "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "error", str(audio_path)]
    try:
        subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL, env=pulse_env)
    except subprocess.CalledProcessError as exc:
        # Catch SIGTERM (-15), SIGINT (-2), 255, 143 from intentional stop_tts
        if exc.returncode in (-signal.SIGTERM, -signal.SIGINT, -15, -2, 255, 143, 130):
            raise KeyboardInterrupt from exc
        raise
```

### 3. Text Normalization Pipeline
```python
# [VERIFIED: 03-CONTEXT.md D-07]
import re

def normalize_tts_text(text: str) -> str:
    """Normalize text conservatively for natural speech synthesis."""
    if not text:
        return ""

    # 1. Strip ANSI escape sequences
    ansi_regex = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    text = ansi_regex.sub("", text)

    # 2. Markdown links: [anchor text](http://...) -> anchor text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 3. Simplify raw URLs: https://domain.com/path?query -> domain.com
    url_regex = re.compile(r"https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(?:/[^\s]*)?")
    text = url_regex.sub(r"\1", text)

    # 4. Code identifiers: convert snake_case underscores to spaces before markdown emphasis
    text = re.sub(r"(?<=\w)_(?=\w)", " ", text)

    # 5. Markdown syntax cleanup
    text = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"(?<!\w)__([^_]+)__(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)

    # 6. Slashes in paths: convert internal path slashes to pauses (comma space)
    # Strip leading slashes on paths (e.g. /home/user -> home, user)
    text = re.sub(r"(?:^|(?<=\s))/+([a-zA-Z0-9])", r"\1", text)
    text = re.sub(r"(?<=[a-zA-Z0-9])/(?=[a-zA-Z0-9])", ", ", text)

    # 7. Smart line pauses: line break after unpunctuated char -> period + space
    text = re.sub(r"([a-zA-Z0-9])\s*\n+", r"\1. ", text)

    # 8. Unicode punctuation normalization
    text = (
        text.replace("—", ", ")
        .replace("–", ", ")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )

    # 9. Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()
```

### 4. Downloader Implementation Pattern (`voice.py --download-tts-assets`)
```python
# [VERIFIED: 03-CONTEXT.md D-01, D-02, D-03]
import sys
import time
import urllib.request
from pathlib import Path

KOKORO_ASSETS = [
    {
        "name": "kokoro-v1.0.onnx",
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
        "min_size": 300_000_000,
        "expected_desc": "~325 MB",
    },
    {
        "name": "voices-v1.0.bin",
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        "min_size": 20_000_000,
        "expected_desc": "~28 MB",
    },
]

def download_file_with_progress(url: str, dest_path: Path, min_size: int, label: str) -> None:
    temp_path = dest_path.with_suffix(".tmp")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if dest_path.exists() and dest_path.stat().st_size >= min_size:
        print(f"✓ {label} already exists ({dest_path.stat().st_size / (1024*1024):.1f} MB). Skipping.")
        return

    req = urllib.request.Request(url, headers={"User-Agent": "voicemode/0.1.0"})
    start_time = time.monotonic()
    with urllib.request.urlopen(req) as resp, open(temp_path, "wb") as out_f:
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 128 * 1024  # 128 KiB
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out_f.write(chunk)
            downloaded += len(chunk)
            elapsed = max(0.001, time.monotonic() - start_time)
            speed_mb = (downloaded / (1024 * 1024)) / elapsed
            pct = (downloaded / total * 100) if total > 0 else 0
            sys.stdout.write(
                f"\rDownloading {label}: {downloaded/(1024*1024):.1f}MB / {total/(1024*1024):.1f}MB "
                f"[{pct:5.1f}%] {speed_mb:.1f} MB/s"
            )
            sys.stdout.flush()
    print()

    # Size check
    actual_size = temp_path.stat().st_size
    if actual_size < min_size:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded file {label} failed size guard ({actual_size} < {min_size} bytes)")

    temp_path.replace(dest_path)
    print(f"✓ Saved {dest_path.name} ({actual_size / (1024*1024):.1f} MB)")
```

### 5. Wayland Primary Selection Capture with Timeout
```python
# [VERIFIED: 03-CONTEXT.md D-04, D-05]
def read_x_selection(selection: str) -> str:
    if display_server() == "wayland":
        wl_paste = shutil.which("wl-paste")
        if not os.getenv("WAYLAND_DISPLAY") or not wl_paste:
            return ""
        command = [wl_paste, "--no-newline"]
        if selection == "primary":
            command.append("--primary")
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=1.0,  # D-05 strict timeout
            )
        except Exception:
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""
```

---

*Research document compiled for Phase 3: Text-to-Speech & Model Asset Pipeline.*
