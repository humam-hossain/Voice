# Phase 3: Text-to-Speech & Model Asset Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-19
**Phase:** 3-Text-to-Speech & Model Asset Pipeline
**Areas discussed:** Asset Management, Selection Capture, Voice & Speech Defaults, Audio Playback & Lifecycle

---

## Asset Management

### Q1: Model Storage Location
| Option | Description | Selected |
|--------|-------------|----------|
| In the repository at `models/kokoro/` | Matches current `voice.py` defaults and download script; keeps project self-contained | ✓ |
| In XDG data directory `~/.local/share/voicemode/models/` | Standard Linux user data location; keeps large binaries out of repo tree | |
| In user cache `~/.cache/voicemode/kokoro/` | Parallels Whisper STT model caching in `~/.cache/huggingface/` | |

**User's choice:** In the repository at `models/kokoro/`
**Notes:** Keeps workspace self-contained and matches existing path conventions in `voice.py`.

### Q2: Download Invocation
| Option | Description | Selected |
|--------|-------------|----------|
| Provide both dedicated CLI command and helper script | `voice.py --download-tts-assets` and standalone `scripts/download-kokoro-assets.sh` | ✓ |
| Dedicated helper script only | `scripts/download-kokoro-assets.sh` with wget/curl | |
| Automatic on-demand download | Download automatically inside `voice.py` when first invoked if assets are missing | |

**User's choice:** Provide both dedicated CLI command and standalone helper script
**Notes:** Refined during review: Python CLI is canonical implementation with progress bar; bash script acts as a lightweight wrapper.

### Q3: Model Asset Integrity Verification
| Option | Description | Selected |
|--------|-------------|----------|
| Existence + size guard + full ONNX test during `--tts-check` | Fast during normal runs; `--tts-check` instantiates Kokoro and inspects voice vector keys | ✓ |
| Strict SHA256 checksum validation during download | Validates byte-for-byte integrity against upstream hashes | |
| Lightweight existence and non-zero size checks only | Minimal overhead, skips model initialization | |

**User's choice:** Existence + size guard + full ONNX runtime test during `--tts-check`
**Notes:** Fast startup on regular runs (>300MB onnx, >20MB voices) and comprehensive verification during `--tts-check`.

### Q4: Download Client Implementation
| Option | Description | Selected |
|--------|-------------|----------|
| Dual support: Python streaming + curl/wget auto-detection | Python-native streaming for `--download-tts-assets`, plus curl/wget in bash script | ✓ |
| Shell-driven: Python invokes bash script | Relies on system utilities | |
| Pure Python: Python stdlib only | Strict Python execution | |

**User's choice:** Dual support: Python-native streaming with progress bar for `--download-tts-assets`, plus curl/wget auto-detection in bash script.

---

## Selection Capture

### Q1: Primary Selection vs Clipboard Priority
| Option | Description | Selected |
|--------|-------------|----------|
| Primary selection first, fallback to clipboard | Speaks highlighted text; if nothing highlighted, speaks recent clipboard | ✓ |
| Primary selection ONLY | Strictly speaks highlighted text; avoids stale clipboard contents | |
| Configurable source with default auto | `--selection-source auto\|primary\|clipboard` | |

**User's choice:** Primary selection first, fallback to clipboard.

### Q2: Maximum Text Length Bounding
| Option | Description | Selected |
|--------|-------------|----------|
| 5,000 character limit (~1,000 words / ~6 min speech) | Desktop warning notification if truncated; configurable via `VOICE_TTS_MAX_CHARS` | ✓ |
| Shorter 2,000 character limit (~400 words) | Quick paragraph reading | |
| No length cap | Synthesize entire selection, relying on user to interrupt | |

**User's choice:** 5,000 character limit with desktop warning toast.

### Q3: Feedback on Empty Selection
| Option | Description | Selected |
|--------|-------------|----------|
| Desktop notification + brief auditory error chime | Instant feedback when hotkey is pressed without looking at screen | ✓ |
| Desktop notification only | Banner via notify-send only | |
| Auditory chime only | Sound only, no visual toast | |

**User's choice:** Desktop notification + brief auditory error chime.

### Q4: Text Normalization & Cleaning
| Option | Description | Selected |
|--------|-------------|----------|
| Conservative enhancement | Strip ANSI escapes, strip raw markdown symbols, simplify long URLs | ✓ |
| Minimal / Current behavior | Only collapse whitespace and em-dashes | |
| Extensive preprocessing | Strip code blocks, convert markdown links, expand acronyms | |

**User's choice:** Conservative enhancement.

### Q5: Wayland `wl-paste` Timeout
| Option | Description | Selected |
|--------|-------------|----------|
| Add 1.0s timeout to `wl-paste` calls | Matches `xclip`'s 1.0s timeout; prevents voicemode hanging on frozen windows | ✓ |
| Add 2.0s timeout | More lenient for slow Electron apps | |
| No timeout | Unbounded subprocess call | |

**User's choice:** Add 1.0s timeout to `wl-paste` calls.

### Q6: Playback Start Notification Detail
| Option | Description | Selected |
|--------|-------------|----------|
| Informative toast: Distinguish source and preview text | `Speaking selection: "..."` vs `Speaking clipboard (fallback): "..."` | ✓ |
| Generic toast | Simple "Speaking selected text..." | |
| Silent background start | No start toast, only errors or stop events | |

**User's choice:** Informative toast with source differentiation and text preview.

### Q7: Clipboard Overwrite Policy
| Option | Description | Selected |
|--------|-------------|----------|
| Leave standard clipboard untouched | Reading primary selection does not overwrite user's copied clipboard buffer | ✓ (refined) |
| Synchronize to clipboard | Copy spoken selection into regular clipboard | Initial pick |

**User's choice:** Refined during architectural audit: Reading primary selection leaves regular clipboard untouched to avoid destroying user's active Ctrl+C contents (passwords, code). Spoken selection is already in Wayland primary selection for middle-click.

### Q8: Binary / Non-Text Data Guard
| Option | Description | Selected |
|--------|-------------|----------|
| Standard `wl-paste` with binary sanity check | Reject if output contains null bytes or binary garbage; fallback gracefully | ✓ |
| Strict plain-text targeting (`--type text/plain`) | Reject rich HTML/binary outright | |
| Unfiltered | Current behavior | |

**User's choice:** Standard `wl-paste` with binary sanity check.

### Q9: Line-Break Pacing on Unpunctuated Lines
| Option | Description | Selected |
|--------|-------------|----------|
| Smart line-break pauses | If line ends without punctuation, treat newline as pause/period | ✓ |
| Raw collapse | Replace all newlines with spaces directly | |
| Strict comma pauses | Convert every newline into comma pause | |

**User's choice:** Smart line-break pauses.

### Q10: On-Screen Highlight Preservation
| Option | Description | Selected |
|--------|-------------|----------|
| Leave highlight intact on screen | Native Wayland convention; user sees what is being read and can re-read | ✓ |
| Clear primary selection after reading starts | Prevents accidental re-reading | |
| Clear only upon successful playback | Clear on completion | |

**User's choice:** Leave highlight intact on screen.

### Q11: Stdin Text Piping
| Option | Description | Selected |
|--------|-------------|----------|
| Support `--speak -` to read from stdin | Enables shell pipelines (`cat file \| voicemode --speak -`) | ✓ |
| Keep CLI argument only | `--speak "text"`, no stdin piping | |
| Auto-detect piped stdin | Implicit reading when stdin is a pipe | |

**User's choice:** Support `--speak -` to read from stdin.

### Q12: Code Identifier Formatting
| Option | Description | Selected |
|--------|-------------|----------|
| Fluent text formatting | Convert underscores to spaces (`snake_case` -> "snake case"), slashes to pauses | ✓ |
| Raw verbatim | Leave symbols as-is | |
| Literal syntax reading | Explicitly speak "underscore", "slash" | |

**User's choice:** Fluent text formatting.

---

## Voice & Speech Defaults

### Q1: Default Kokoro Voice Profile
| Option | Description | Selected |
|--------|-------------|----------|
| Keep `af_heart` (American female) as default | Benchmark high-clarity voice; secondary remains `bm_george` | ✓ |
| Switch default to American male | `am_adam` or `am_michael` | |
| Switch default to British voice | `bm_george` (male) or `bf_emma` (female) | |

**User's choice:** Keep `af_heart` as default voice.

### Q2: Default Playback Speed Multiplier
| Option | Description | Selected |
|--------|-------------|----------|
| 1.2x speed | Brisk and time-efficient for screen reading without losing clarity | ✓ |
| 1.0x speed | Natural baseline conversational pacing | |
| 1.5x speed | Fast skimming speed | |
| 2.0x speed | Hermes default double-speed | |

**User's choice:** 1.2x speed. Clamped to `[0.5, 2.0]` for Kokoro safety.

### Q3: Cloud Fallback Policy
| Option | Description | Selected |
|--------|-------------|----------|
| Strict offline privacy | Never auto-fallback to cloud Edge TTS without user opt-in; notify that Kokoro assets are missing | ✓ |
| Auto-fallback to Edge TTS | Use cloud TTS when local assets are missing | |
| Prompt user to choose | Modal/prompt | |

**User's choice:** Strict offline privacy.

### Q4: Inter-Sentence Silence Trimming
| Option | Description | Selected |
|--------|-------------|----------|
| Keep `trim=False` default | Preserves natural breathing pauses between sentences | ✓ |
| Set `trim=True` default | Eliminates inter-chunk silence | |
| Smart trim | Trim only at start/end of audio file | |

**User's choice:** Keep `trim=False` default.

---

## Audio Playback & Lifecycle

### Q1: PipeWire Stream Tagging
| Option | Description | Selected |
|--------|-------------|----------|
| Tag PipeWire stream as `voicemode` | `PULSE_PROP_application.name="voicemode"`, `media.name="voicemode-tts"` in `ffplay` | ✓ |
| Default ffplay behavior | Shows up as "ffplay" | |
| Custom volume/channel mapping | ALSA/Pulse env vars | |

**User's choice:** Tag PipeWire stream as `voicemode`.

### Q2: Interruption / Stop Feedback
| Option | Description | Selected |
|--------|-------------|----------|
| Silent cut-off + desktop toast | Audio immediately halts; "Speech stopped" toast confirms cancellation | ✓ |
| Auditory stop chime + desktop toast | Plays stop chime upon interruption | |
| Completely silent | No chime and no notification | |

**User's choice:** Silent cut-off + desktop toast.

### Q3: `ffplay` Exit Handling on SIGTERM
| Option | Description | Selected |
|--------|-------------|----------|
| Clean cancellation filter | Catch `CalledProcessError` (-15, -2, 255) from `ffplay` as clean termination | ✓ |
| Propagate all errors | Send failure toast on non-zero exit | |
| Ignore returncode entirely | Always consider finished | |

**User's choice:** Clean cancellation filter.

### Q4: Temporary File Garbage Collection
| Option | Description | Selected |
|--------|-------------|----------|
| Opportunistic garbage collection | Purge orphaned `voice-tts-*` files in `STATE_DIR` older than 30 min on startup/stop | ✓ |
| Rely only on `try...finally` | No sweeping | |
| Dedicated `--cleanup` flag | Manual trigger only | |

**User's choice:** Opportunistic garbage collection.

---

## The Agent's Discretion
- Concrete frequencies and durations for the new `"error"` cue in `play_cue`.
- Console progress bar formatting for `voice.py --download-tts-assets`.

## Deferred Ideas
None — discussion stayed within phase scope.
