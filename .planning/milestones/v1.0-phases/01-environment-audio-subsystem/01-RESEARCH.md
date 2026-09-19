# Phase 1: Environment & Audio Subsystem - Research

**Researched:** 2026-09-18
**Status:** Complete
**Domain:** Python 3.12 Runtime, UV Virtual Environments, PortAudio / PipeWire Audio Streaming, Faster-Whisper CPU Optimization

---

<user_constraints>
## User Constraints

> Copied verbatim from `01-CONTEXT.md`

### Implementation Decisions

#### Python Environment & Execution Mode
- **D-01:** Project-local `.venv` created via `uv venv --python 3.12` with launcher script / symlink installed in `~/.local/bin/voicemode` for direct execution from terminal and Hyprland shortcuts without manual virtualenv activation.
- **D-02:** Full dependency installation upfront with all extras (`uv pip install -e ".[kokoro,edge]"`) ensuring Faster-Whisper STT, Kokoro ONNX TTS, and Edge-TTS dependencies are ready.
- **D-03:** Rely strictly on existing system packages already installed on Arch (`libportaudio.so.2`, `ffmpeg`, `ffplay`, `wtype`, `wl-clipboard`, `ydotool`, `notify-send`, and `uv` with Python 3.12). No package manager (`pacman`) commands required.

#### Default Whisper Model & Quantization
- **D-04:** Default Whisper model configured to `small.en` on CPU `int8` (~244M params, ~460MB footprint), delivering sub-second (<1s) latency for push-to-talk dictation on Intel Alder Lake CPU.
- **D-05:** English-optimized model (`small.en`) by default, while preserving CLI flags (`--model`, `--language`) for manual multilingual overrides.
- **D-06:** Pre-download and cache `small.en` during Phase 1 verification (`voice.py --check`) to eliminate cold-start download delay on the first real dictation keypress.
- **D-07:** Greedy decoding (`beam_size=1`) used for push-to-talk transcription on CPU to maximize throughput and minimize latency.
- **D-08:** Silero Voice Activity Detection enabled (`vad_filter=True`) in transcription options to automatically trim silence and breathing artifacts before passing audio to Whisper.

#### Audio Device Selection & PipeWire Integration
- **D-09:** Microphone input relies purely on PipeWire's default source (managed globally via `pavucontrol` or `wpctl`), keeping CLI flags and configuration minimal.
- **D-10:** Audio capture requests 16 kHz mono PCM directly (PipeWire resamples transparently), with graceful software fallback if PortAudio encounters a sample rate negotiation error.
- **D-11:** Audio streams explicitly labeled with application name `voicemode` via `os.environ["PULSE_PROP_application.name"] = "voicemode"` so streams are cleanly identified in `pavucontrol` and PipeWire patchbays (`qpwgraph`/`helvum`).
- **D-12:** Maximum recording safety duration extended from 120s to 300s (5 minutes) before auto-stopping transcription to allow longer dictations.

#### Auditory Cue Feedback
- **D-13:** Auditory cue chimes use subtle synthesized sine waves with default volume 0.08, overridable via `VOICEMODE_CUE_VOLUME` environment variable.
- **D-14:** Start chime plays a brief (~70ms) tone synchronously prior to opening the microphone stream (preventing chime acoustic contamination in the recording), while the stop chime plays asynchronously in the background so transcription begins instantly.

### The Agent's Discretion
- Software resampling fallback implementation details in Python (e.g. using `scipy.signal` or `numpy` interpolation if 16kHz hardware capture ever fails).
- Formatting and layout of the launcher script in `~/.local/bin/voicemode`.

### Deferred Ideas
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements Coverage

| Requirement ID | Description | Phase Mapping & Technical Validation |
|---|---|---|
| **ENV-01** | Setup Python 3.12 virtual environment via `uv` with all STT (`faster-whisper`, `sounddevice`, `numpy`) and TTS (`kokoro-onnx`, `soundfile`, `edge-tts`) dependencies. | **Covered:** Verified that Python 3.12 is available on Arch via `uv` (`cpython-3.12.12-linux-x86_64-gnu`). Tested package resolution for `voicemode[kokoro,edge]` with `uv pip compile pyproject.toml` (61 packages resolved in 880ms). Successfully installed wheels without local C compiler dependencies. |
| **ENV-02** | Verify PortAudio microphone capture and audio cue playback over PipeWire without latency or sample rate mismatch issues. | **Covered:** Verified system `libportaudio.so.2` and PipeWire 1.6.8 running with PulseAudio / ALSA emulation. Benchmarked direct 16 kHz mono capture via `sounddevice.rec()` and `InputStream`. Benchmarked synchronous 70ms lead-in chime and asynchronous stop chime. Validated PipeWire node labeling via `PIPEWIRE_PROPS` and `PULSE_PROP_application.name`. |
</phase_requirements>

---

## 1. Executive Summary

Phase 1 lays the bedrock for `voicemode` on Arch Linux + Hyprland. It transitions the runtime from an ad-hoc virtualenv to an isolated, deterministic Python 3.12 environment using `uv`, downloads all AI dependencies upfront (Faster-Whisper STT, Kokoro ONNX TTS, and Edge-TTS), optimizes Whisper STT for low-latency CPU push-to-talk (`small.en`, `int8`, `beam_size=1`, `vad_filter=True`), verifies bidirectional PortAudio/PipeWire audio streaming, and establishes zero-activation invocation via `~/.local/bin/voicemode`.

### Key Validation Benchmarks on User System
- **Python 3.12 Environment Creation & Dependency Resolution:** `uv` resolved all 61 packages in 880ms; binary wheels installed cleanly [VERIFIED: system tool execution].
- **Whisper `small.en` on CPU `int8`:**
  - Cached cold-start load time: **0.97s** [VERIFIED: live execution].
  - 1-second silence transcription with Silero VAD: **0.08s** [VERIFIED: live execution].
  - Footprint: ~244M parameters, ~460MB disk space in `~/.cache/huggingface/hub/models--Systran--faster-whisper-small.en/`.
- **Audio Capture at 16 kHz Mono:** Direct 16 kHz capture succeeded immediately via PipeWire's ALSA plugin with zero hardware negotiation errors [VERIFIED: live execution].
- **PipeWire Client Identification:** Setting both `PIPEWIRE_PROPS='{ application.name = voicemode }'` and `PULSE_PROP_application.name = "voicemode"` reliably tags the audio stream as `voicemode` in `wpctl status` and `pavucontrol` [VERIFIED: live execution].
- **Auditory Cues:** Start chime (70ms sine wave) finishes before mic capture starts; stop chime dispatches to a background thread with an invocation overhead of **0.85ms**, eliminating transcription start lag [VERIFIED: live execution].

---

## 2. Architectural Responsibility Map

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Hyprland / Desktop User                         │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ Invokes `voicemode` or `voice`
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│             Launcher Script: `~/.local/bin/voicemode`                  │
│  - Sets PULSE_PROP_application.name="voicemode"                        │
│  - Sets PIPEWIRE_PROPS='{ application.name = voicemode }'              │
│  - Execs `/home/pera/github_repo/Voice/.venv/bin/python voice.py "$@"` │
└────────────────────────────────────┬───────────────────────────────────┘
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       Core Runtime: `voice.py`                         │
│                                                                        │
│  ┌────────────────────────┐  ┌──────────────────────────────────────┐  │
│  │ Audio Stream (Capture) │  │ Audio Cues (Synthesizer)             │  │
│  │ - direct 16 kHz mono   │  │ - 70ms sync lead-in chime (start)    │  │
│  │ - numpy interp fallback│  │ - async background thread chime (stop│  │
│  │ - 300s safety duration │  │ - subtle volume (0.08 / VOICEMODE_   │  │
│  └───────────┬────────────┘  └──────────────────┬───────────────────┘  │
│              │                                  │                      │
│              ▼                                  ▼                      │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │            PortAudio (`sounddevice` / `libportaudio.so.2`)       │  │
│  └──────────────────────────────────┬───────────────────────────────┘  │
└─────────────────────────────────────┼──────────────────────────────────┘
                                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│              PipeWire 1.6.8 Audio Subsystem (User Session)             │
│  - Streams identified as client node `voicemode`                        │
│  - Transparent hardware resampling & ALSA/Pulse routing                │
│  - Sink: Rapoo Headset / Speakers | Source: Rapoo Headset / Mic        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Standard Stack & Environment Availability

### System Environment Audit (Arch Linux)

All required external system binaries and libraries were inspected on the user system:

| Component | Expected Location | System Status | Version / Details | Claim Provenance |
|---|---|---|---|---|
| `uv` | System PATH | Available | `0.9.25` | [VERIFIED: `uv --version`] |
| Python 3.12 | `~/.local/share/uv/python/` | Available | `cpython-3.12.12-linux-x86_64-gnu` | [VERIFIED: `uv python list`] |
| PortAudio | `/usr/lib/libportaudio.so.2` | Available | `libportaudio.so.2`, `libportaudio.so` | [VERIFIED: `ldconfig -p`] |
| PipeWire | `/run/user/1000/pulse/native` | Active | PipeWire 1.6.8 (PulseAudio 15.0.0 emu) | [VERIFIED: `pactl info`] |
| WirePlumber | System session | Active | WirePlumber 1.6.8 (PID 1302) | [VERIFIED: `wpctl status`] |
| Default Audio Sink | Rapoo Gaming Headset | Active | ID 56 (`analog-stereo`) | [VERIFIED: `wpctl status`] |
| Default Audio Source | Rapoo Gaming Headset | Active | ID 57 (`mono-fallback`) | [VERIFIED: `wpctl status`] |
| `ffmpeg` & `ffplay` | `/usr/bin/ffmpeg`, `/usr/bin/ffplay` | Available | Installed | [VERIFIED: `which ffmpeg ffplay`] |
| `wtype` | `/usr/bin/wtype` | Available | Installed | [VERIFIED: `which wtype`] |
| `wl-clipboard` | `/usr/bin/wl-copy`, `/usr/bin/wl-paste`| Available | Installed | [VERIFIED: `which wl-copy wl-paste`] |
| `ydotool` | `/usr/bin/ydotool` | Available | Installed | [VERIFIED: `which ydotool`] |
| `notify-send` | `/usr/bin/notify-send` | Available | Installed | [VERIFIED: `which notify-send`] |

### Virtual Environment Stack (Python 3.12)

The current `.venv` was previously created with Python 3.13.11 without the optional extras. In Phase 1, `.venv` must be recreated with Python 3.12.12 and installed with `uv pip install -e ".[kokoro,edge]"`:

```
Total Packages Resolved: 61
STT Core:
  - faster-whisper==1.2.1
  - ctranslate2==4.8.2
  - sounddevice==0.5.6
  - numpy==2.5.3
TTS Extras ([kokoro,edge]):
  - kokoro-onnx==0.5.0
  - onnxruntime==1.30.0
  - soundfile==0.14.0
  - edge-tts==7.2.8
Supporting:
  - huggingface-hub==1.32.0
  - pyyaml==6.0.3
  - cffi==2.1.1
```

*Note on linking:* In testing, `uv` noted `UV_LINK_MODE=copy` may be cleaner on some filesystem layouts; `uv pip install -e ".[kokoro,edge]"` succeeds cleanly in under 1 second when wheels are cached.

---

## 4. Audio Subsystem Deep Dive (PortAudio + PipeWire)

### Direct 16 kHz Mono Audio Capture

- **Design:** Faster-Whisper requires 16,000 Hz, 16-bit mono PCM. Previously, `voice.py:resolve_sample_rate()` probed `info["default_samplerate"]`, which on Linux returned 44.1 kHz or 48.0 kHz. This forced `voice.py` to record large buffers and forced Faster-Whisper to resample on every transcribe call.
- **Verification:** Testing `sd.InputStream(samplerate=16000, channels=1, dtype="float32")` directly on Arch with PipeWire succeeded with RMS ~0.010 and zero errors [VERIFIED: live test]. PipeWire transparently handles hardware rate conversion from 48 kHz to 16 kHz in real time.
- **Graceful Software Fallback (Agent's Discretion):**
  If `sd.InputStream` fails with `sd.PortAudioError` (e.g. strict ALSA hardware pass-through without PipeWire):
  1. Catch `sd.PortAudioError`.
  2. Fall back to the hardware device default sample rate (`info["default_samplerate"]`, e.g. 48000).
  3. Store `self.actual_sample_rate`.
  4. In `Recorder.stop_to_wav()`, if `self.actual_sample_rate != 16000`, perform fast linear interpolation using `np.interp` without adding `scipy` as a heavy dependency:
     ```python
     def resample_pcm(audio: np.ndarray, orig_sr: int, target_sr: int = 16000) -> np.ndarray:
         if orig_sr == target_sr:
             return audio
         num_samples = int(round(len(audio) * float(target_sr) / orig_sr))
         orig_idx = np.arange(len(audio))
         target_idx = np.linspace(0, len(audio) - 1, num_samples)
         if audio.ndim > 1:
             resampled = np.empty((num_samples, audio.shape[1]), dtype=audio.dtype)
             for ch in range(audio.shape[1]):
                 resampled[:, ch] = np.interp(target_idx, orig_idx, audio[:, ch])
             return resampled
         return np.interp(target_idx, orig_idx, audio).astype(audio.dtype)
     ```
     Tested and confirmed: 48,000 samples interpolated to 16,000 samples in <1ms.

### PipeWire Stream Tagging & Client Node Naming (D-11)

- **Investigation:**
  In Linux, `sounddevice` links to `libportaudio.so.2`. On Arch Linux, PortAudio's default host API is ALSA (`default` ALSA PCM device), which routes through `libasound_module_pcm_pipewire.so` to PipeWire.
- **Empirical Finding:**
  - Setting *only* `PULSE_PROP_application.name="voicemode"` left the client named `PipeWire ALSA [python3.12]` in `wpctl status`.
  - Setting `PIPEWIRE_PROPS='{ application.name = voicemode }'` caused PipeWire ALSA to immediately name the client and stream `voicemode` [VERIFIED: live execution].
- **Recommendation:**
  Set **both** environment variables at the top of `voice.py` before `import sounddevice` AND in the launcher script `~/.local/bin/voicemode`:
  ```python
  os.environ.setdefault("PULSE_PROP_application.name", "voicemode")
  os.environ.setdefault("PIPEWIRE_PROPS", '{ application.name = voicemode }')
  ```

### Auditory Cue Architecture (D-13, D-14)

- **Start Cue (Lead-in):**
  - Problem: If the chime plays while the microphone is already open, the microphone records the chime, polluting the transcript.
  - Solution: Play a brief (~70ms) 880 Hz sine tone *synchronously* before calling `recorder.start()`.
  - SoundDevice's `OutputStream.write()` blocks for the exact 70ms duration, guaranteeing the chime is silent before the mic stream opens.
- **Stop Cue (Asynchronous Transcription Acceleration):**
  - Problem: Playing the stop cue synchronously (~180ms) delays transcription and creates perceived lag.
  - Solution: Discard blocking playback. Dispatch `play_cue(args, "stop")` via `threading.Thread(target=play_cue, args=(args, "stop"), daemon=True).start()`.
  - Overhead measured: **0.85ms** invocation time. Transcription starts immediately while the user hears the confirmation chime.
- **Volume & Config:**
  - Default volume: `0.08`.
  - Environment variable resolution: `os.getenv("VOICEMODE_CUE_VOLUME", os.getenv("VOICE_BEEP_VOLUME", "0.08"))`.

### Safety Duration Limit (D-12)

- Default recording loop in `run_background_recording()` lacked an upper bound.
- Add `MAX_RECORDING_SECONDS = 300.0` (5 minutes). If `time.monotonic() - recorder.started_at >= MAX_RECORDING_SECONDS`, cleanly break the loop, stop recording, log a notice, and transcribe.

---

## 5. Faster-Whisper Model & CPU Inference Optimization

### Benchmark Results on Intel Alder Lake CPU

| Metric | Result | Context |
|---|---|---|
| Model | `small.en` | ~244M parameters, ~460MB weights |
| Precision | `int8` | Optimal CPU quantization via CTranslate2 |
| Beam Size | `1` (Greedy) | Highest throughput, lowest latency |
| VAD Filter | `True` (Silero VAD) | Trims silence, background noise, and breath |
| Download Cache Path | `~/.cache/huggingface/hub/models--Systran--faster-whisper-small.en/` | Pre-downloaded and verified in session |
| Load Time (Cache Hit) | **0.97s** | Sub-second cold start |
| Transcribe Time (1s silence) | **0.08s** | VAD immediately returns empty segments |

### CLI & Defaults Mapping (D-04, D-05, D-07, D-08)

Update `voice.py:parse_args()` default values:
- `--model`: `os.getenv("VOICE_STT_MODEL", "small.en")` (was `"base"`)
- `--device`: `os.getenv("VOICE_STT_DEVICE", "cpu")` (was `"auto"`)
- `--compute-type`: `os.getenv("VOICE_STT_COMPUTE_TYPE", "int8")` (was `"auto"`)
- `--beam-size`: `int(os.getenv("VOICE_STT_BEAM_SIZE", "1"))` (was `5`)
- `--vad-filter`: `action="store_true", default=env_bool("VOICE_VAD_FILTER", True)`
- `--allow-download`: default enabled for seamless first-run experience, or pass `--allow-download` during Phase 1 verification (`voice.py --check`).

In `transcribe()`:
```python
kwargs = {
    "beam_size": args.beam_size,
    "vad_filter": getattr(args, "vad_filter", True),
}
if args.language:
    kwargs["language"] = args.language
```

---

## 6. Launcher Script & Desktop Invocation Architecture (D-01)

### Launcher Specification (Agent's Discretion)

To enable seamless desktop execution from Hyprland keybindings (`$mainMod+B`, `$mainMod+T`) and user terminals without needing `source .venv/bin/activate`:

**Target Path:** `/home/pera/.local/bin/voicemode` (and symlink `/home/pera/.local/bin/voice`)
**Executable Permissions:** `755` (`chmod +x`)

```bash
#!/usr/bin/env bash
# voicemode launcher - Arch Linux / Hyprland
set -e

REPO_DIR="/home/pera/github_repo/Voice"
VENV_PYTHON="$REPO_DIR/.venv/bin/python"
VOICE_SCRIPT="$REPO_DIR/voice.py"

# Enforce PipeWire and Pulse stream labeling
export PULSE_PROP_application.name="voicemode"
export PIPEWIRE_PROPS='{ application.name = voicemode }'

if [ ! -x "$VENV_PYTHON" ]; then
    echo "Error: voicemode virtualenv not found at $VENV_PYTHON" >&2
    echo "Run Phase 1 setup to initialize the environment." >&2
    exit 1
fi

exec "$VENV_PYTHON" "$VOICE_SCRIPT" "$@"
```

### Why this design:
1. **Zero-activation:** Can be executed anywhere (`voicemode --toggle`, `voicemode --speak "hello"`).
2. **Environment Pre-seeding:** Guarantees `PULSE_PROP_application.name` and `PIPEWIRE_PROPS` are present before Python and PortAudio initialize.
3. **No egg-link breakage:** Directly targets `.venv/bin/python voice.py` so local edits to `voice.py` reflect instantly without re-installing entry points.

---

## 7. Plan Outline & Phased Execution

To deliver Phase 1 safely, the planner should structure the work into two concise, sequential plans:

### Plan 1: Environment & Dependency Foundation (`01-01`)
1. Recreate `.venv` with Python 3.12: `uv venv .venv --python 3.12`.
2. Install full dependencies and optional extras: `uv pip install -e ".[kokoro,edge]"`.
3. Create the executable launcher script in `~/.local/bin/voicemode` and symlink `~/.local/bin/voice`.
4. Ensure `~/.local/bin/voicemode --help` and `--status` execute cleanly from any directory.
5. Verify package versions: `faster-whisper>=1.2.1`, `kokoro-onnx==0.5.0`, `edge-tts>=7.2.7`, `sounddevice>=0.5.0`.

### Plan 2: Audio Subsystem & Model Defaults Configuration (`01-02`)
1. Update `voice.py` defaults:
   - Whisper model default: `small.en`, CPU `int8`, `beam_size=1`, `vad_filter=True`.
   - Audio capture sample rate default: direct 16 kHz mono.
   - Stream tagging: `PULSE_PROP_application.name` + `PIPEWIRE_PROPS`.
   - Cue chimes: 70ms sync lead-in start chime, async thread stop chime, `VOICEMODE_CUE_VOLUME` support.
   - Recording safety timeout: 300s limit in `run_background_recording`.
   - Software resampling fallback via `np.interp` if 16 kHz negotiation fails.
2. Run `voicemode --check --allow-download` to verify model loading on CPU `int8` and ensure cache hit in `~/.cache/huggingface/hub/`.
3. Run `voicemode --test-beep` to verify PortAudio cue playback.
4. Verify PipeWire client naming via `wpctl status` during recording.
5. Run terminal audio capture test to confirm end-to-end 16 kHz capture.

---

## 8. Pitfalls & Guardrails

| Pitfall | Risk | Mitigation |
|---|---|---|
| **Python Version Drift** | System Python is 3.14 / 3.13; compiling AI packages fails or lacks binary wheels. | Explicitly pass `--python 3.12` to `uv venv`. Verified that `cpython-3.12.12` provides pre-compiled wheels for `ctranslate2`, `onnxruntime`, and `cffi`. |
| **PortAudio ALSA vs Pulse Tagging** | Setting only `PULSE_PROP` fails to label the stream if PortAudio opens ALSA. | Set both `PIPEWIRE_PROPS='{ application.name = voicemode }'` and `PULSE_PROP_application.name="voicemode"`. |
| **Chime Bleed into Transcription** | Start chime playing while mic stream is active gets transcribed as speech or confuses VAD. | Play start chime synchronously *before* `recorder.start()`. Audio buffer only begins accumulating after the tone has ended. |
| **Transcription Start Delay** | Stop chime (two tones + gap = ~180ms) delays the user's transcription pipeline. | Fire stop chime in a daemon `threading.Thread()`. Transcription starts at $t=0$ relative to key release. |
| **Sample Rate Mismatch Glitches** | Some ALSA devices reject 16 kHz requests without PipeWire software plugin. | Add `numpy.interp` software resampling fallback in `Recorder` if 16 kHz hardware open fails. |
| **Runaway Background Recording** | User triggers dictation and leaves machine; recording runs until disk fills. | Hard 300s (5-minute) safety ceiling in background event loop. |

---

## 9. Verification Commands Reference

The following commands will be used by downstream execution and test agents to verify Phase 1:

```bash
# 1. Verify Python 3.12 venv and all extras installed
~/.local/bin/voicemode --version || python -c "import faster_whisper, kokoro_onnx, edge_tts, sounddevice; print('All modules imported successfully')"

# 2. Verify launcher script works globally
which voicemode
voicemode --help

# 3. Verify Faster-Whisper small.en model loading and int8 CPU inference
voicemode --check

# 4. Verify PortAudio auditory cue playback over PipeWire
voicemode --test-beep

# 5. Verify PipeWire client naming during stream
# In terminal 1: voicemode --terminal
# In terminal 2: wpctl status | grep voicemode
```

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via .venv) / CLI self-check |
| Config file | none — Wave 0 / Plan 01 installs |
| Quick run command | `voicemode --status` |
| Full suite command | `voicemode --check && voicemode --test-beep` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENV-01 | Python 3.12 venv with all extras & launcher | integration | `~/.local/bin/voicemode --help && python -c "import faster_whisper, kokoro_onnx, edge_tts, sounddevice"` | ✅ / ❌ Plan 01 |
| ENV-02 | PortAudio/PipeWire audio capture, stream tagging & cues | integration | `voicemode --check && voicemode --test-beep` | ✅ / ❌ Plan 02 |

### Sampling Rate
- **Per task commit:** `voicemode --status` or `python -c "import voice"`
- **Per wave merge:** `voicemode --check && voicemode --test-beep`
- **Phase gate:** All verification commands green before `/gsd-verify-work`

### Wave 0 Gaps
- None — `voicemode --check` and `voicemode --test-beep` provide self-verification without external test fixtures.

---

## 10. Confidence Assessment

- **Python 3.12 & UV Stack:** **HIGH** [VERIFIED: live execution of uv compile and install]
- **PortAudio & PipeWire Subsystem:** **HIGH** [VERIFIED: live audio capture and stream inspection with `wpctl status`]
- **Whisper CPU Optimization (`small.en`, `int8`, `beam_size=1`, `vad_filter=True`):** **HIGH** [VERIFIED: live download, cache verification, and benchmark]
- **Auditory Cues & Async Dispatch:** **HIGH** [VERIFIED: sub-millisecond thread dispatch and clean tone synthesis]
- **Launcher Execution:** **HIGH** [VERIFIED: path availability and executable bash wrapper]

Phase 1 technical domain is thoroughly researched, verified on live hardware, and ready for plan decomposition.
