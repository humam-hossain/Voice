# Phase 1: Environment & Audio Subsystem - Context

**Gathered:** 2026-09-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 establishes the Python 3.12 virtual environment via `uv`, installs all STT and TTS dependencies with full extras, configures CPU-optimized Faster-Whisper defaults (`small.en`, `int8`, `beam_size=1`, `vad_filter=True`), and verifies PortAudio/PipeWire audio capture, client node naming, and clean auditory cue feedback.
</domain>

<decisions>
## Implementation Decisions

### Python Environment & Execution Mode
- **D-01:** Project-local `.venv` created via `uv venv --python 3.12` with launcher script / symlink installed in `~/.local/bin/voicemode` for direct execution from terminal and Hyprland shortcuts without manual virtualenv activation.
- **D-02:** Full dependency installation upfront with all extras (`uv pip install -e ".[kokoro,edge]"`) ensuring Faster-Whisper STT, Kokoro ONNX TTS, and Edge-TTS dependencies are ready.
- **D-03:** Rely strictly on existing system packages already installed on Arch (`libportaudio.so.2`, `ffmpeg`, `ffplay`, `wtype`, `wl-clipboard`, `ydotool`, `notify-send`, and `uv` with Python 3.12). No package manager (`pacman`) commands required.

### Default Whisper Model & Quantization
- **D-04:** Default Whisper model configured to `small.en` on CPU `int8` (~244M params, ~460MB footprint), delivering sub-second (<1s) latency for push-to-talk dictation on Intel Alder Lake CPU.
- **D-05:** English-optimized model (`small.en`) by default, while preserving CLI flags (`--model`, `--language`) for manual multilingual overrides.
- **D-06:** Pre-download and cache `small.en` during Phase 1 verification (`voice.py --check`) to eliminate cold-start download delay on the first real dictation keypress.
- **D-07:** Greedy decoding (`beam_size=1`) used for push-to-talk transcription on CPU to maximize throughput and minimize latency.
- **D-08:** Silero Voice Activity Detection enabled (`vad_filter=True`) in transcription options to automatically trim silence and breathing artifacts before passing audio to Whisper.

### Audio Device Selection & PipeWire Integration
- **D-09:** Microphone input relies purely on PipeWire's default source (managed globally via `pavucontrol` or `wpctl`), keeping CLI flags and configuration minimal.
- **D-10:** Audio capture requests 16 kHz mono PCM directly (PipeWire resamples transparently), with graceful software fallback if PortAudio encounters a sample rate negotiation error.
- **D-11:** Audio streams explicitly labeled with application name `voicemode` via `os.environ["PULSE_PROP_application.name"] = "voicemode"` so streams are cleanly identified in `pavucontrol` and PipeWire patchbays (`qpwgraph`/`helvum`).
- **D-12:** Maximum recording safety duration extended from 120s to 300s (5 minutes) before auto-stopping transcription to allow longer dictations.

### Auditory Cue Feedback
- **D-13:** Auditory cue chimes use subtle synthesized sine waves with default volume 0.08, overridable via `VOICEMODE_CUE_VOLUME` environment variable.
- **D-14:** Start chime plays a brief (~70ms) tone synchronously prior to opening the microphone stream (preventing chime acoustic contamination in the recording), while the stop chime plays asynchronously in the background so transcription begins instantly.

### The Agent's Discretion
- Software resampling fallback implementation details in Python (e.g. using `scipy.signal` or `numpy` interpolation if 16kHz hardware capture ever fails).
- Formatting and layout of the launcher script in `~/.local/bin/voicemode`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md` — Project context, hardware profile, constraints, and architecture
- `.planning/REQUIREMENTS.md` §ENV-01, §ENV-02 — Explicit Phase 1 requirements for runtime and audio subsystem
- `.planning/ROADMAP.md` §Phase 1 — Phase 1 goals, plans, and success criteria

### Codebase & Configuration
- `pyproject.toml` — Package metadata, dependencies, and optional extras (`[kokoro]`, `[edge]`)
- `voice.py` — Core implementation of audio capture (`Recorder`), cues (`play_cue`), model loading (`load_model`), and transcription (`transcribe`)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `voice.py:Recorder` — SoundDevice streaming audio recorder class supporting real-time callback buffering
- `voice.py:play_tone`, `voice.py:play_cue` — Sine wave synthesis with cosine window fades
- `voice.py:load_model`, `voice.py:transcribe` — Faster-Whisper loader with CPU int8 fallback and segment decoding

### Established Patterns
- In-memory PCM buffer manipulation via NumPy arrays
- Process isolation and PID tracking in `$XDG_RUNTIME_DIR/voice-stt/`
- Stream configuration via `sounddevice`

### Integration Points
- PipeWire-Pulse / ALSA emulation via PortAudio (`libportaudio.so.2`)
- Hugging Face model cache in `~/.cache/huggingface/hub/`
- Virtual environment in `./.venv/`

</code_context>

<specifics>
## Specific Ideas
- Zero-activation desktop invocation via `~/.local/bin/voicemode` symlink / wrapper.
- Automatic stream tagging as `voicemode` in PipeWire via PulseAudio environment variable.
- Clean separation of start chime (synchronous lead-in) and stop chime (asynchronous) to prevent acoustic chime bleed into speech transcripts.
</specifics>

<deferred>
## Deferred Ideas
None — discussion stayed within phase scope.
</deferred>

---

*Phase: 1-Environment & Audio Subsystem*
*Context gathered: 2026-09-18*
