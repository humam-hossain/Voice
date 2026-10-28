# Phase 6: Foundations, Ledger & Status Contract - Research

**Researched:** 2026-10-28  
**Domain:** Python CLI telemetry, file-based IPC, atomic writes, PID race conditions, import-laziness  
**Confidence:** HIGH  

## Summary

Phase 6 establishes the truthful telemetry and status foundation for the v1.1 latency prediction feature. The core challenge is instrumenting honest timing data without storing transcript content, fixing race conditions in the worker lifecycle, making non-transcription commands fast (import-light), and publishing atomic status snapshots that are advisory while PID remains authoritative.

The existing codebase uses a single-file architecture (`voice.py`) with detached workers, PID state files in `$XDG_RUNTIME_DIR/voice-stt/`, and a simple `pid state` format. Phase 6 extends this with: (1) lazy imports for heavy ML libraries so `--status`, `--report`, `--toggle`, `--cancel`, `--doctor` don't load numpy/sounddevice/faster-whisper; (2) atomic PID/state writes with proper locking; (3) a new `voicemode_telemetry.py` module for ledger/status; (4) schema v1 for JSONL ledger at `$XDG_STATE_HOME/voicemode/metrics.jsonl` and atomic `status.json`; (5) early model loading and incremental chunk transcription with honest timing; (6) comprehensive race fixes around double-toggle/cold start.

**Primary recommendation:** Extract telemetry/status into `voicemode_telemetry.py`, move heavy imports behind lazy loading (inside functions/command handlers), implement atomic file writes with `os.replace()` on same filesystem, use file locking (`fcntl.flock`) for read-modify-write operations on PID state, and ensure every exit path in worker writes terminal ledger row.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Keep every run by default (no automatic time-based trim). Rollover by size remains available as a safety cap if needed, but the default is unbounded growth.
- **D-02:** Minimal fingerprint only (model/device/compute_type/beam_size/vad_filter/language/chunk_s). Do **not** store CPU model, cores, RAM, GPU name/serials/UUIDs, or OS versions.
- **D-03:** Write `status.json` every 5 s while recording (matching the existing reminder cadence). Only emit on state transitions otherwise.
- **D-04:** Primary env var is `VOICE_METRICS`. Alias `VOICE_TELEMETRY` to it for backward compatibility. Outlier corpus capture flag: `VOICE_CAPTURE_OUTLIERS` (default off). Document all three in `docs/telemetry.md`.
- **D-05:** Load the Whisper model early in the background worker (before/during recording start), not after recording stops. This pays the cold-load cost while the user is preparing to speak and removes the post-stop load cliff.
- **D-06:** Transcribe completed audio chunks incrementally as they are written to disk while recording continues. Keep the model hot across chunks. All transcripts are buffered and only pasted/inserted at the end per existing UX (no live typing to the focused window).
- **D-07:** Track per-chunk timings (audio duration, decode time covering full generator consumption, chars count) and record them in telemetry. This lets prediction handle silence/padding correctly without guessing future silence, and feeds better calibration in later phases.
- **D-08:** Keep prediction infrastructure. Even with incremental transcription, ETA remains useful (fallbacks, final chunk variance, etc.). The goal is to make it more honest, not remove it.

### the agent's Discretion
- Exact rotation implementation details (if we ever hit the safety cap), ledger file permissions (`0700`/`0600`), `status.json` atomic write details, test placement/mocking strategy, and how to parallelize chunk transcription vs recording (sequential is fine as long as model stays loaded).

### Deferred Ideas
None — discussion stayed within phase scope.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CLI argument parsing & routing | Frontend/CLI | - | Fast path for non-transcription commands must avoid heavy imports |
| PID state management (authority) | IPC/Filesystem | - | Existing `pid state` format unchanged; must be atomic and race-safe |
| Background worker lifecycle | Process management | - | Handles recording, transcription, insertion; must write terminal outcomes |
| Audio capture | Audio subsystem | PortAudio/sounddevice | Already implemented; needs integration with incremental chunking |
| Whisper transcription | ML inference | faster-whisper/CTranslate2 | Must be loaded early, kept hot across chunks, with honest timing around generator consumption |
| Telemetry/ledger | Storage/IPC | Filesystem | New `voicemode_telemetry.py`; JSONL at state dir, atomic writes, privacy-safe |
| Status publishing | IPC/Filesystem | - | Advisory `status.json` written atomically on transitions/heartbeat; expires on stale/crash |
| Text insertion | Platform integration | wtype/ydotool/xclip | Existing logic unchanged per UX requirements |

## Standard Stack

### Core (existing)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 | Runtime | Project requires >=3.12 |
| argparse | stdlib | CLI parsing | Built-in |
| pathlib | stdlib | Path handling | Built-in |
| fcntl | stdlib (Linux) | File locking | For race-safe PID operations |
| os/signal/subprocess | stdlib | Process management | Built-in |
| json | stdlib | Serialization | Built-in |

### Heavy dependencies (lazy-loaded)
| Library | Version | Purpose | When to Load |
|---------|---------|---------|--------------|
| numpy | >=2.0.2 | Audio arrays | Only in recording/transcription/cue paths |
| sounddevice | >=0.5.0 | Audio I/O | Only in recording/cue paths |
| faster-whisper | >=1.2.1 | STT inference | Only in transcription paths (loaded early in worker) |

### Supporting (existing)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| PyYAML | >=6.0 | Hermes config | Only if Hermes config used |
| edge-tts | optional | Online TTS | TTS paths only |
| kokoro-onnx | optional | Offline TTS | TTS paths only |

**Installation:** No new dependencies required. Use existing deps.

## Package Legitimacy Audit

> No new external packages are added in Phase 6 per constraints ("no new dependencies"). All packages are already declared in pyproject.toml.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| numpy | PyPI | Established | High | numpy/numpy | OK | Already used |
| sounddevice | PyPI | Established | High | spatialaudio/python-sounddevice | OK | Already used |
| faster-whisper | PyPI | Established | High | SYSTRAN/faster-whisper | OK | Already used |

**Packages removed due to [SLOP] verdict:** none  
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### Pattern 1: Lazy Imports for Import-Light Commands
**What:** Move heavy imports (numpy, sounddevice, faster-whisper) inside functions/command handlers rather than module top-level.  
**When to use:** For any command path that doesn't need ML/audio (e.g., `--status`, `--report`, `--toggle` decision logic in main path that doesn't load models).  
**Example:**
```python
# At top: keep stdlib only
# Inside function:
def some_stt_function():
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel
    ...
```
**Note:** `main()` must route to handlers without triggering heavy imports. The current code has them at top (lines 40-42 in voice.py) - this must change.

### Pattern 2: Atomic File Writes
**What:** Write to temp file in same directory, then `os.replace()` (atomic on POSIX). Set permissions appropriately.  
**When to use:** For `status.json`, PID state files, ledger appends need care (append is not atomic across processes but we need correctness).  
**Example:**
```python
def atomic_write_json(path: Path, obj: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.write(fd, json.dumps(obj).encode())
        os.close(fd)
        fd = None
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        tmp = None
    finally:
        if fd is not None: os.close(fd)
        if tmp is not None: 
            try: os.unlink(tmp)
            except: pass
```

### Pattern 3: File Locking for Race-Safe Operations
**What:** Use `fcntl.flock()` around read-modify-write sequences on PID/state files.  
**When to use:** In `toggle_background_recording()` when doing flock around read-decide-spawn; worker re-verifies PID holds its own PID.  
**Example:**
```python
import fcntl
with open(lock_path, 'r+') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    # read current state, decide, write new state
    ...
    fcntl.flock(f, fcntl.LOCK_UN)
```

### Pattern 4: Early Model Loading + Incremental Transcription
**What:** Load Whisper model in worker before/during recording start (D-05). Transcribe completed chunks as they are written while recording continues (D-06). Keep model hot across chunks.  
**When to use:** In `run_background_recording()` flow.  
**Key points:**
- Start loading model in background thread early? Or just load before starting to record? "before/during recording start" - need to pay cold load cost while user prepares to speak.
- As chunks are written to disk by Recorder, transcribe them incrementally (sequential is fine per discretion)
- Track per-chunk timings (audio duration, decode time covering full generator consumption, chars count)
- Buffer all transcripts, paste/insert only at end per existing UX

### Anti-Patterns to Avoid
- **Top-level heavy imports:** Breaks import-light requirement for non-transcription commands
- **Non-atomic PID writes:** Can lead to torn reads
- **Writing partial status:** Must be atomic
- **Storing transcript text:** Must only store character counts
- **New PID state strings:** Must only use existing vocabulary
- **Assuming status.json exists:** PID file is authority

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File locking | Custom lock files with race conditions | `fcntl.flock()` | Standard, atomic on Linux |
| Atomic writes | Write directly then rename in complex ways | `os.replace()` on same filesystem | Atomic on POSIX |
| JSON serialization with allowlist | Manual field filtering everywhere | Central serializer in telemetry module with allowlist | Prevents accidental PII leakage |
| Timing measurement | `time.time()` for durations | `time.monotonic()` for durations, `time.time()` for epoch cross-process timestamps | Correct for intervals and cross-process sync |
| Process liveness | Parsing ps output | `os.kill(pid, 0)` + `/proc/<pid>/cmdline` validation | More reliable |

## Runtime State Inventory

> Not applicable for this phase - this is adding telemetry/status infrastructure, not renaming/refactoring existing runtime state. No rename/migration of existing strings.

## Common Pitfalls

### Pitfall 1: Import-time side effects break import-light requirement
**What goes wrong:** Importing modules at top level that import heavy deps causes `--status` to load numpy/sounddevice/faster-whisper.  
**Why it happens:** Current codebase does `import numpy as np`, `import sounddevice as sd`, `from faster_whisper import WhisperModel` at module level.  
**How to avoid:** Move all heavy imports inside functions. Use lazy loading. Ensure `main()` and command handlers for non-transcription commands don't trigger them.  
**Warning signs:** `time python -c "import voice; voice.main()" --status` takes long or loads heavy modules.

### Pitfall 2: Race conditions in toggle
**What goes wrong:** Two rapid toggle presses spawn two workers.  
**Why it happens:** Read-decide-spawn not atomic; no re-verification.  
**How to avoid:** Use `fcntl.flock()` around read-decide-spawn in `toggle_background_recording()`. Worker must re-verify PID file holds its own PID before recording. Handle "starting" state with wait.  
**Warning signs:** Multiple PIDs in PID file or multiple worker processes.

### Pitfall 3: Torn PID/state file reads
**What goes wrong:** Reader sees partial content.  
**Why it happens:** Non-atomic writes.  
**How to avoid:** Write to temp file in same dir, `os.replace()`. Set permissions.  
**Warning signs:** `ValueError` parsing PID state or corrupted reads.

### Pitfall 4: Generator consumption timing
**What goes wrong:** Timing `model.transcribe()` call instead of consuming the generator.  
**Why it happens:** faster-whisper returns `(segments, info)` where segments is a generator - need to iterate over it fully to get decode time.  
**How to avoid:** Time from before iterating to after consuming all segments. Track decode_ms as full generator consumption time.  
**Warning signs:** decode_ms much smaller than actual transcription time.

### Pitfall 5: Storing PII in telemetry
**What goes wrong:** Accidentally store transcript text, paths, hostnames.  
**Why it happens:** Logging/serializing full objects.  
**How to avoid:** Use allowlist serialization in telemetry module. Only store character counts. Add regex scan test. Never log transcript content.  
**Warning signs:** Ledger contains strings that look like text.

### Pitfall 6: status.json becomes authority
**What goes wrong:** Deleting status.json changes bar state.  
**Why it happens:** Code reads status.json as source of truth.  
**How to avoid:** PID file remains authority. status.json is advisory only. Bar logic must not depend on status.json for liveness.  
**Warning signs:** Behavior changes when status.json removed.

## Code Examples

### Lazy imports pattern
```python
def run_background_recording(args: argparse.Namespace) -> int:
    # Import heavy deps inside
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel
    ...
```

### Atomic write
```python
import os, json, tempfile
from pathlib import Path

def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.write(fd, json.dumps(data, separators=(',', ':')).encode('utf-8'))
        os.close(fd)
        fd = None
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, str(path))
        tmp_path = None
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
```

### File locking for PID operations
```python
import fcntl

def toggle_background_recording_safe(args):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = STATE_DIR / ".toggle.lock"
    with open(lock_path, 'w') as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            pid, state = read_pid_state()
            if pid and process_alive(pid):
                # handle existing worker...
            # decide to spawn...
            # spawn and write pid state atomically
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)
```

### Timing decode with generator consumption
```python
import time

def transcribe_with_timing(model, wav_path, args):
    start = time.monotonic()
    segments, info = model.transcribe(str(wav_path), **kwargs)
    # Consume generator fully
    segment_list = []
    for seg in segments:
        segment_list.append(seg)
    decode_ms = (time.monotonic() - start) * 1000.0
    text = " ".join(s.text.strip() for s in segment_list).strip()
    return text, decode_ms, segment_list
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Model loaded after recording stops | Model loaded early in worker before/during recording start | Phase 6 (D-05) | Eliminates post-stop load cliff, better UX |
| Transcribe whole recording at end | Transcribe completed chunks incrementally while recording | Phase 6 (D-06) | Enables better timing instrumentation, keeps model hot |
| Top-level heavy imports | Lazy imports in functions | Phase 6 (FND-01) | Fast non-transcription commands |
| Non-atomic writes | Atomic writes with os.replace() | Phase 6 (FND-02) | No torn reads |
| No telemetry | JSONL ledger + status.json | Phase 6 (LED/STS) | Enables prediction in later phases |

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | fcntl is available on Linux (it is) | Architecture Patterns | Low - Linux only project |
| A2 | os.replace() is atomic on same filesystem on Linux | Architecture Patterns | Low - standard POSIX behavior |
| A3 | /proc/<pid>/cmdline is reliable for process validation | Don't Hand-Roll | Low - used currently |
| A4 | XDG_STATE_HOME defaults to ~/.local/state if not set | Ledger location | Medium - need to handle correctly |
| A5 | Sequential chunk transcription is fine per discretion | Architecture Patterns | Low - explicit permission given |

**If this table is empty:** No - there are assumptions above.

## Open Questions

1. **Module structure**
   - What we know: Need to add `voicemode_telemetry.py`. Can modify `voice.py`.
   - What's unclear: Exact API design between modules.
   - Recommendation: Design clean interfaces, keep telemetry logic isolated.

2. **Early model loading timing**
   - What we know: Load before/during recording start (D-05). 
   - What's unclear: Exact placement - in worker before starting recorder? In parallel thread?
   - Recommendation: Load model after entering worker but before `recorder.start()`, or in parallel thread while setting up. Need to ensure model is ready when chunks come in.

3. **Incremental transcription integration**
   - What we know: Transcribe completed chunks as written while recording continues.
   - What's unclear: How Recorder signals chunk completion - currently writes async in threads and appends to `self._chunk_paths`. Need to hook into this.
   - Recommendation: Extend Recorder to allow callback on chunk completion, or have worker poll/watch chunk files.

4. **Status.json heartbeat**
   - What we know: Write every 5s while recording (D-03), on transitions otherwise.
   - What's unclear: Exact schema details beyond what's specified.
   - Recommendation: Follow STS-02 schema exactly as specified.

5. **Terminal outcome on all exits**
   - What we know: Every abnormal exit ends in terminal outcome, SIGKILL detected by expiry.
   - What's unclear: How to detect SIGKILL vs clean exit?
   - Recommendation: On normal exit paths write terminal ledger row. On crash/SIGKILL, PID expires - need expiry mechanism in status.json and/or detection logic.

## Environment Availability

> Phase 6 involves code changes only, no external tools beyond what's already used.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | ✓ | 3.12 | - |
| fcntl | File locking | ✓ | stdlib | - |
| Existing deps | STT/TTS | ✓ | As per pyproject | - |

**Missing dependencies with no fallback:** None  
**Missing dependencies with fallback:** None

## Validation Architecture

> workflow.nyquist_validation not explicitly false in config - include section.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | unittest (stdlib) + existing tests |
| Config file | none |
| Quick run command | `python -m pytest tests/ -v` or `python -m unittest discover tests/` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FND-01 | Non-transcription commands import-light, --status <100ms warm | unit/integration | `python -m pytest tests/test_*.py -v` | ⚠️ Need new tests |
| FND-02 | PID state written atomically, no torn reads | unit | `python -m pytest tests/test_*.py -v` | ⚠️ Need new tests |
| FND-03 | Two rapid toggles -> one worker, flock, re-verify | unit/integration | `python -m pytest tests/test_*.py -v` | ⚠️ Need new tests |
| FND-04 | Every exit writes terminal ledger row, clear status/PID | integration | `python -m pytest tests/test_*.py -v` | ⚠️ Need new tests |
| FND-05 | No new PID state strings | unit | `python -m pytest tests/test_*.py -v` | ⚠️ Need new tests |
| LED-01-07 | Ledger schema v1, privacy, kill switch, permissions | unit | `python -m pytest tests/test_*.py -v` | ⚠️ Need new tests |
| DEC-01-04 | Timing semantics, generator consumption, clocks | unit | `python -m pytest tests/test_*.py -v` | ⚠️ Need new tests |
| STS-01-05 | status.json atomic, schema, authority, expiry | unit | `python -m pytest tests/test_*.py -v` | ⚠️ Need new tests |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -v` (quick)
- **Per wave merge:** Full suite
- **Phase gate:** Full suite green before verification

### Wave 0 Gaps
- [ ] `tests/test_telemetry.py` — ledger schema, privacy allowlist, permissions, kill switch
- [ ] `tests/test_status_contract.py` — status.json atomic writes, expiry, authority
- [ ] `tests/test_pid_race.py` — flock, double-toggle, torn reads
- [ ] `tests/test_import_light.py` — verify non-transcription commands don't import heavy deps
- [ ] `tests/test_timing.py` — generator consumption timing, monotonic clocks

## Security Domain

> security_enforcement enabled by default.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A - local CLI tool |
| V3 Session Management | no | N/A |
| V4 Access Control | yes | File permissions 0700/0600 on state dirs/files |
| V5 Input Validation | yes | Validate env vars, PID parsing, JSON schema |
| V6 Cryptography | no | N/A - no crypto needed |

### Known Threat Patterns for stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PID file race condition | Tampering/DoS | Use fcntl.flock(), re-verify PID ownership |
| Information disclosure in logs/telemetry | Information Disclosure | Character counts only, allowlist serialization, no transcript text/paths/hostnames |
| Symlink attacks on state files | Tampering | Use atomic writes, validate paths stay under expected dirs |
| Privilege escalation via spawned processes | Elevation of Privilege | Use start_new_session, validate cmdline, drop privileges if possible (not critical for local tool) |

## Sources

### Primary (HIGH confidence)
- Existing `voice.py` implementation - PID helpers, toggle/run flow, transcribe
- Phase 6 CONTEXT.md - locked decisions
- Phase 6 requirements (FND/LED/DEC/STS)
- Python stdlib docs - fcntl, os.replace, tempfile

### Secondary (MEDIUM confidence)
- faster-whisper docs - generator behavior of transcribe()
- Linux filesystem semantics - atomic rename

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - using existing deps and stdlib
- Architecture: HIGH - clear patterns from requirements and existing codebase
- Pitfalls: HIGH - identified from requirements and common issues
- Implementation details: MEDIUM - some discretion items need careful design

**Research date:** 2026-10-28  
**Valid until:** 2026-11-27 (30 days for stable patterns)
