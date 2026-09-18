# Phase 2: Wayland Keystroke Injection - Context

**Gathered:** 2026-09-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 implements native Wayland keystroke injection in `voice.py` using `wtype` as the primary rootless backend. It replaces reliance on root `ydotoold` for both direct typing and paste shortcuts, integrates seamless dual-action clipboard persistence (always copying to clipboard before typing), handles newlines and special characters securely via stdin piping, and implements robust settling delays and error fallbacks under Hyprland.

</domain>

<decisions>
## Implementation Decisions

### Backend Hierarchy & Fallback
- **D-01:** Prefer `wtype` as the primary Wayland typing tool; if `wtype` is not installed, fallback to `ydotool` if present; if typing fails or errors out, fallback to clipboard preservation.
- **D-02:** Use `wtype` for simulated paste shortcuts (`-M ctrl -s 20 -k v -s 20 -m ctrl` and `-M ctrl -M shift -s 20 -k v -s 20 -m shift -m ctrl`) with `ydotool` fallback, keeping Wayland shortcut simulation completely rootless.
- **D-03:** Auto-detect `wtype` with an optional override via CLI flag (`--wayland-backend {auto,wtype,ydotool}`) and environment variable (`VOICE_WAYLAND_BACKEND`).
- **D-04:** Send desktop notification via `notify-send` if typing fails, explaining that typing failed and that the transcript was preserved in the clipboard.

### Typing Delay & Pacing Calibration
- **D-05:** Default per-keystroke delay set to 2ms (`wtype -d 2`), balancing rapid text injection with zero dropped characters in Wayland/Hyprland applications.
- **D-06:** Pre-typing settling pause of 50ms before `wtype` starts typing, configurable via `VOICE_PRE_TYPE_DELAY` environment variable (default 50ms), ensuring desktop hotkey modifiers (`Super+B`) are released and active window focus is stable.
- **D-07:** Uniform typing pace maintained across the entire text without dynamic chunking or rate degradation.
- **D-08:** Maintain 150ms settling pause in `paste_clipboard` between `wl-copy` and the paste keystroke execution to guarantee Wayland clipboard readiness across all client applications.
- **D-09:** Synchronous `subprocess.run` execution for `wtype` with a 15s timeout protection so failures or hung processes are caught and handled.
- **D-10:** Clamp `--type-delay` to `max(0, delay)`, permitting explicit 0ms for instant injection while rejecting negative values.

### Special Characters & Newline Handling
- **D-11:** Pipe transcript text to `wtype` via stdin (`wtype -d <ms> -`), preventing shell argument escaping issues, CLI length limits, or leading hyphen misinterpretation.
- **D-12:** Replace internal newlines with spaces by default in speech transcripts before typing, preventing accidental message dispatch in chat applications or premature shell execution in terminals.
- **D-13:** Support `--keep-newlines` CLI flag and `VOICE_KEEP_NEWLINES` env var to allow users dictating multi-line prose or code to opt into literal Return keystrokes.
- **D-14:** Keep transcripts strictly trimmed (`strip()`) without automatic trailing spaces for predictable typing.

### Output Method & Unified Clipboard Flow
- **D-15:** Keep default `--output-method` as `type`.
- **D-16:** **Dual Behavior:** Unconditionally copy transcript to Wayland clipboard (`wl-copy`) right after transcription and prior to typing. This ensures the user's speech is always preserved in the clipboard for manual pasting anywhere, while also eliminating the need for complex reactive failover copying.
- **D-17:** When `--output-method paste` is explicitly used, leave the transcript in the clipboard without attempting to restore previous clipboard contents.

### The Agent's Discretion
- Internal timeout duration calibration for wtype processes (15s default).
- Precise CLI argument assembly and process error logging details.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md` — Project context, hardware profile, constraints, and architecture
- `.planning/REQUIREMENTS.md` §INPUT-01, §INPUT-02 — Explicit Phase 2 requirements for Wayland input injection
- `.planning/ROADMAP.md` §Phase 2 — Phase 2 goals, plans, and success criteria

### Codebase & Integrations
- `voice.py` — Core implementation of typing (`type_text`), pasting (`paste_clipboard`), text insertion (`insert_text`), clipboard manipulation (`copy_to_clipboard`), and display server detection (`display_server`)
- `.planning/codebase/INTEGRATIONS.md` — OS desktop interaction patterns, Wayland display protocols, and subprocess execution rules

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `voice.py:display_server` — Detects Wayland vs X11 from `$XDG_SESSION_TYPE` and `$WAYLAND_DISPLAY`
- `voice.py:copy_to_clipboard` — Uses `wl-copy` on Wayland with stdin piping
- `voice.py:insert_text` — Central dispatcher routing text to `type_text`, `paste_clipboard`, or `copy_to_clipboard`
- `voice.py:notify` — Dispatches desktop notifications via `notify-send`

### Established Patterns
- Subprocess execution using `shutil.which` guards before binary execution
- Passing `args: argparse.Namespace` across insertion functions
- Non-blocking notification alerts on insertion failures

### Integration Points
- `voice.py:type_text` — Integrate `wtype` backend as primary Wayland typing mechanism
- `voice.py:paste_clipboard` — Integrate `wtype` modifier/key syntax (`-M ctrl -s 20 -k v -s 20 -m ctrl`)
- `voice.py:insert_text` — Implement unconditional upfront clipboard copy for dual behavior

</code_context>

<specifics>
## Specific Ideas
- Direct rootless execution via `wtype` virtual keyboard protocol on Hyprland without requiring `ydotoold`.
- Dual behavior: Speech is always copied to clipboard and typed into active window.
- Clean newline normalization to prevent accidental message dispatch in chat/terminal apps.
</specifics>

<deferred>
## Deferred Ideas
None — discussion stayed within phase scope.
</deferred>

---

*Phase: 2-Wayland Keystroke Injection*
*Context gathered: 2026-09-19*
