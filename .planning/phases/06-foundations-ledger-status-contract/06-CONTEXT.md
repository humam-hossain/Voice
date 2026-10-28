# Phase 6: Foundations, Ledger & Status Contract - Context

**Gathered:** 2026-10-28
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase makes telemetry and status truthful: freeze schema v1, add `voicemode_telemetry.py`, write the JSONL ledger and atomic `status.json`, fix the duplicate-worker race and lifecycle races, instrument honest stage timings (including the faster-whisper lazy generator seam), make non-transcription commands import-light, and reserve TTS fields. No new PID state strings, no new dependencies, no transcript text stored.
</domain>

<decisions>
## Implementation Decisions

### History retention
- **D-01:** Keep every run by default (no automatic time-based trim). Rollover by size remains available as a safety cap if needed, but the default is unbounded growth. — **Reversibility:** costly — changing this later affects report history and disk usage expectations.

### Machine fingerprint
- **D-02:** Minimal fingerprint only (model/device/compute_type/beam_size/vad_filter/language/chunk_s). Do **not** store CPU model, cores, RAM, GPU name/serials/UUIDs, or OS versions. — **Reversibility:** costly — altering the key hierarchy affects calibration lookups for historical runs.

### Recording heartbeat
- **D-03:** Write `status.json` every 5 s while recording (matching the existing reminder cadence). Only emit on state transitions otherwise. — **Reversibility:** reversible — purely a consumer-facing freshness/cadence choice.

### Config names
- **D-04:** Primary env var is `VOICE_METRICS`. Alias `VOICE_TELEMETRY` to it for backward compatibility. Outlier corpus capture flag: `VOICE_CAPTURE_OUTLIERS` (default off). Document all three in `docs/telemetry.md`. — **Reversibility:** reversible — aliases avoid breaking existing usage.

### the agent's Discretion
- Exact rotation implementation details (if we ever hit the safety cap), ledger file permissions (`0700`/`0600`), `status.json` atomic write details, and test placement/mocking strategy.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone
- `.planning/REQUIREMENTS.md` — FND/LED/DEC/STS requirements (21)
- `.planning/ROADMAP.md` — Phase 6 goal and success criteria
- `.planning/research/SUMMARY.md` — Frozen contracts and non-negotiable fixes
- `.planning/research/PITFALLS.md` — Race, timing seam, atomicity, clocks

### Codebase
- `voice.py` — PID helpers, `toggle_background_recording`, `run_background_recording`, `transcribe`, imports
- `.planning/codebase/ARCHITECTURE.md` — IPC/state machine
- `.planning/codebase/TESTING.md` — Test patterns
- `.planning/codebase/STACK.md` — Dependencies
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- PID file helpers in `voice.py` (state authority)
- Existing signal handling and process management
- Test patterns for mocking subprocesses

### Established Patterns
- Detached worker processes with PID tracking
- File-based IPC in `$XDG_RUNTIME_DIR/voice-stt/`
- Monolithic single-file architecture

### Integration Points
- `toggle_background_recording()` — race fix
- `run_background_recording()` — instrumentation + status writes
- `transcribe()` — timing seam fix
- Module imports — lazy loading
</code_context>

<specifics>
## Specific Ideas

- Keep everything by default (user explicitly chose "Keep everything" over rolling/12-month). No auto-trim in Phase 6.
- Minimal fingerprint only for portability keys.
- 5 s heartbeat while recording.
- `VOICE_METRICS` primary with `VOICE_TELEMETRY` alias.
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---
*Phase: 06-Foundations, Ledger & Status Contract*
*Context gathered: 2026-10-28*
