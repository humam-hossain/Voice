# Phase 3: Text-to-Speech & Model Asset Pipeline - Context

**Gathered:** 2026-09-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 establishes the offline neural Text-to-Speech (TTS) asset pipeline using Kokoro ONNX and native Wayland selection reading. It implements automated Kokoro model weights and voice embeddings retrieval and verification, Wayland primary selection text capture (`wl-paste --primary`) with fallback to standard clipboard, conservative text normalization (ANSI escape stripping, markdown cleanup, URL simplification, code identifier formatting, and smart line-break pauses), 5,000 character length bounding, PipeWire stream identification for `ffplay` audio output, and clean, silent interruption lifecycle handling under Hyprland.

</domain>

<decisions>
## Implementation Decisions

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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md` — Project context, hardware profile, constraints, and architecture
- `.planning/REQUIREMENTS.md` §TTS-01, §TTS-02 — Explicit Phase 3 requirements for Kokoro assets and Wayland selection TTS
- `.planning/ROADMAP.md` §Phase 3 — Phase 3 goals, plans, and success criteria

### Codebase & Integrations
- `voice.py` — Core implementation of TTS synthesis (`synthesize_kokoro_tts`, `synthesize_tts`), selection extraction (`read_x_selection`, `selected_or_clipboard_text`), process lifecycle (`run_tts_background`, `stop_tts`), and playback (`play_tts_audio`)
- `scripts/download-kokoro-assets.sh` — Helper script for downloading Kokoro model weights and voices
- `.planning/codebase/INTEGRATIONS.md` — Audio subsystem (PipeWire/PortAudio), display protocols (Wayland/`wl-clipboard`), and subprocess execution rules

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `voice.py:read_x_selection` — Extracts text using `wl-paste` on Wayland with `--no-newline` and optional `--primary`
- `voice.py:selected_or_clipboard_text` — Evaluates primary selection first with fallback to regular clipboard
- `voice.py:play_cue`, `voice.py:play_tone` — Synthesizes sine wave audio cue tones via NumPy and SoundDevice
- `voice.py:notify` — Desktop notification dispatcher wrapping `notify-send`
- `voice.py:synthesize_kokoro_tts` — Offline neural TTS inference via `kokoro_onnx.Kokoro`

### Established Patterns
- Headless `ffplay` audio execution via `subprocess.run([ffplay, "-nodisp", "-autoexit", ...])`
- Process tracking and signaling using PID files in `$STATE_DIR` (`$XDG_RUNTIME_DIR/voice-stt/`)
- Stream tagging using PulseAudio environment variables for PipeWire identification
- Defensive subprocess error checking and non-zero exit status reporting

### Integration Points
- `voice.py:parse_args` — Add `--download-tts-assets` flag and update default `--tts-speed` to 1.2
- `voice.py:normalize_tts_text` — Expand regex and formatting logic for code tokens, URLs, and smart pauses
- `voice.py:speak_selection` — Add upfront text truncation, error cue on empty selection, and preview toast
- `voice.py:print_tts_check` — Add full Kokoro ONNX model instantiation and voice inspection test
- `voice.py:play_tts_audio` — Add PipeWire environment variables and clean cancellation error filtering

</code_context>

<specifics>
## Specific Ideas
- Seamless toggle: Pressing the TTS hotkey (`Super+T`) while speech is playing immediately halts audio without auditory clutter.
- Single source of truth for assets: `voice.py --download-tts-assets` handles downloading and validating models directly into `models/kokoro/`.
- Safe Kokoro bounds: Speed is clamped to `[0.5, 2.0]` to guarantee zero unhandled assertion crashes inside `kokoro-onnx`.
</specifics>

<deferred>
## Deferred Ideas
None — discussion stayed within phase scope.
</deferred>

---

*Phase: 3-Text-to-Speech & Model Asset Pipeline*
*Context gathered: 2026-09-19*
