# Phase 2: Wayland Keystroke Injection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-19
**Phase:** 2-Wayland Keystroke Injection
**Areas discussed:** Backend hierarchy & fallback cascade, Typing delay & pacing calibration, Special characters & newline handling, Output method preferences & clipboard fallback

---

## Backend hierarchy & fallback cascade

### Question 1: Wayland Tool Selection Hierarchy
| Option | Description | Selected |
|--------|-------------|----------|
| Prefer wtype with ydotool & clipboard fallback | Prefer wtype, fallback to ydotool if installed, then copy to clipboard and notify if typing fails | ✓ |
| Strict wtype only | Fail and notify if wtype is missing without falling back to ydotool | |
| You decide | Determine the cleanest fallback chain automatically | |

**User's choice:** Prefer wtype, fallback to ydotool if installed, then copy to clipboard and notify if typing fails
**Notes:** Ensures robust execution without breaking on setups without ydotool.

### Question 2: Paste Shortcut Execution via wtype
| Option | Description | Selected |
|--------|-------------|----------|
| Use wtype for paste shortcuts | Use wtype for paste shortcuts (-M ctrl -k v -m ctrl) with ydotool fallback | ✓ |
| Keep ydotool for shortcuts | Keep ydotool exclusively for key combinations, using wtype only for literal text | |
| You decide | Let the agent choose the best shortcut simulation approach | |

**User's choice:** Use wtype for paste shortcuts (-M ctrl -k v -m ctrl) with ydotool fallback, keeping Wayland completely rootless
**Notes:** Makes the entire Wayland dictation pipeline rootless.

### Question 3: Wayland Backend Selection Flag
| Option | Description | Selected |
|--------|-------------|----------|
| Flag and env var override | Auto-detect wtype with optional override via --wayland-backend and VOICE_WAYLAND_BACKEND | ✓ |
| Auto-detect only | Auto-detect only without introducing new CLI flags or env vars | |
| You decide | Structure tool detection in whatever way minimizes friction | |

**User's choice:** Auto-detect wtype with an optional override via CLI flag (--wayland-backend {auto,wtype,ydotool}) and env var (VOICE_WAYLAND_BACKEND)

### Question 4: Alerting on Typing Failure
| Option | Description | Selected |
|--------|-------------|----------|
| Desktop notification and log warning | Send desktop notification explaining typing failed and text was preserved in clipboard | ✓ |
| Silent clipboard fallback | Silently fallback to clipboard with log warning only | |
| You decide | Structure notification alerts based on failure severity | |

**User's choice:** Send desktop notification explaining typing failed and text was preserved in clipboard, alongside log warning

---

## Typing delay & pacing calibration

### Question 1: Default Keystroke Delay (-d)
| Option | Description | Selected |
|--------|-------------|----------|
| 2ms per keystroke | Balance between fast injection and zero dropped characters | ✓ |
| 0ms | Instantaneous typing, relying on compositor queueing | |
| 5ms | Extra conservative for slower GUI/Electron apps | |
| You decide | Calibrate optimal default based on standard Hyprland responsiveness | |

**User's choice:** Default to 2ms per keystroke (balance between fast injection and zero dropped characters)

### Question 2: Pre-Typing Settling Pause
| Option | Description | Selected |
|--------|-------------|----------|
| 50ms settling pause | Brief settling pause before typing to ensure hotkey modifier release and focus stability | ✓ |
| 0ms pre-delay | Type immediately with 0ms pre-delay to minimize latency | |
| You decide | Let the agent choose a safe settling pause | |

**User's choice:** Add a brief settling pause (~50ms) before typing to ensure hotkey modifier release and window focus stability

### Question 3: Long Transcript Pacing
| Option | Description | Selected |
|--------|-------------|----------|
| Uniform delay | Uniform delay across entire text; users adjust --type-delay or use clipboard paste for large texts | ✓ |
| Dynamic scaling | Reduce delay to 1ms for text over 500 characters | |
| You decide | Implement the most robust and predictable timing model | |

**User's choice:** Uniform delay across the entire text; users can adjust --type-delay or use clipboard paste for large texts

### Question 4: Paste Clipboard Settling Delay
| Option | Description | Selected |
|--------|-------------|----------|
| 150ms delay | Keep 150ms delay between clipboard copy and paste keystroke to guarantee Wayland clipboard readiness | ✓ |
| 75ms delay | Reduce paste delay to 75ms for snappier paste responsiveness | |
| You decide | Determine optimal clipboard paste settling delay | |

**User's choice:** Keep 150ms delay between clipboard copy and paste keystroke to guarantee Wayland clipboard readiness across all apps

### Question 5: Settling Delay Configuration
| Option | Description | Selected |
|--------|-------------|----------|
| Env var only | Expose VOICE_PRE_TYPE_DELAY environment variable (default: 50ms) without cluttering CLI flags | ✓ |
| Flag and env var | Add both CLI flag (--pre-type-delay) and env var | |
| Internal constant | Keep it as an internal constant (50ms) without extra configuration | |
| You decide | Structure configuration to keep CLI options clean | |

**User's choice:** Expose VOICE_PRE_TYPE_DELAY environment variable (default: 50ms) without cluttering CLI flags

### Question 6: Modifier Pause in Shortcut Simulation
| Option | Description | Selected |
|--------|-------------|----------|
| Minimal modifier pause (-s 20ms) | Sequential execution with -s 20ms pause ensuring compositor registers Ctrl before V | ✓ |
| Direct execution without pause | Direct execution without -s pauses | |
| You decide | Benchmark and pick the cleanest shortcut sequence | |

**User's choice:** Sequential execution with minimal modifier pause (-s 20ms) to ensure Wayland compositor registers Ctrl before V

### Question 7: Subprocess Invocation Mode
| Option | Description | Selected |
|--------|-------------|----------|
| Synchronous with timeout (15s) | Synchronous subprocess.run with timeout protection so failures trigger clipboard fallback | ✓ |
| Detached spawn | Detached spawn without blocking (fire-and-forget) | |
| You decide | Structure subprocess invocation for maximum reliability | |

**User's choice:** Synchronous subprocess.run with timeout protection (15s) so failures can trigger clipboard fallback

### Question 8: Type Delay Sanitization
| Option | Description | Selected |
|--------|-------------|----------|
| Clamp to max(0, delay) | Allow explicit 0ms but prevent negative values | ✓ |
| Clamp to min 1ms | Clamp type_delay to minimum 1ms | |
| You decide | Let the agent handle input sanitization | |

**User's choice:** Clamp type_delay to max(0, delay) allowing explicit 0ms but preventing negative values

---

## Special characters & newline handling

### Question 1: Text Input Stream
| Option | Description | Selected |
|--------|-------------|----------|
| Pipe text via stdin | wtype -d <ms> - for robust handling of long strings, special characters, and leading hyphens | ✓ |
| CLI argument | Pass text as trailing CLI argument (wtype -d <ms> -- "<text>") | |
| You decide | Let the agent pick the most secure and robust input stream | |

**User's choice:** Pipe text via stdin (wtype -d <ms> -) for robust handling of long strings, special characters, and leading hyphens

### Question 2: Newline Replacement in Dictation
| Option | Description | Selected |
|--------|-------------|----------|
| Replace newlines with spaces | Replace newlines with spaces by default to prevent accidental message dispatch | ✓ |
| Preserve newlines literally | Preserve newlines literally as Enter/Return keystrokes | |
| You decide | Determine safest default handling for transcript line breaks | |

**User's choice:** Replace newlines with spaces by default to prevent accidental message dispatch or shell command execution

### Question 3: Opt-in for Newlines
| Option | Description | Selected |
|--------|-------------|----------|
| --keep-newlines flag | Support --keep-newlines CLI flag and VOICE_KEEP_NEWLINES env var | ✓ |
| No extra flag | Always normalize to spaces during typing | |
| You decide | Let the agent provide an opt-in mechanism if needed | |

**User's choice:** Support --keep-newlines CLI flag and VOICE_KEEP_NEWLINES env var to allow opting into literal Return keystrokes

### Question 4: Boundary Whitespace
| Option | Description | Selected |
|--------|-------------|----------|
| Strictly trimmed | Keep strictly trimmed (strip()) with no automatic trailing space | ✓ |
| Automatic trailing space | Automatically append single trailing space | |
| You decide | Follow standard text insertion conventions | |

**User's choice:** Keep strictly trimmed (strip()) with no automatic trailing space, keeping typing predictable

---

## Output method preferences & clipboard fallback

### Question 1: Default Output Method
| Option | Description | Selected |
|--------|-------------|----------|
| Keep "type" | Natural typing, preserves user's clipboard history | ✓ |
| Change to "paste" | Instant insertion, overwriting clipboard | |
| You decide | Keep existing default if appropriate | |

**User's choice:** Keep "type" as default output method (natural typing, preserves user's clipboard history)

### Question 2: Clipboard Fallback on Typing Failure
| Option | Description | Selected |
|--------|-------------|----------|
| Copy to clipboard on failure | Always copy transcript to clipboard upon typing failure so user speech is never lost | ✓ |
| Leave clipboard untouched | Do not modify clipboard on typing failure | |
| You decide | Structure failure handling to prevent data loss | |

**User's choice:** Always copy transcript to clipboard upon typing failure so user speech is never lost and can be manually pasted

### Question 3: Clipboard Retention in Paste Mode
| Option | Description | Selected |
|--------|-------------|----------|
| Leave transcript in clipboard | Simple, reliable, avoids race conditions with apps and clipboard managers | ✓ |
| Restore prior clipboard content | Attempt to restore prior clipboard content 500ms after paste completes | |
| You decide | Structure clipboard behavior for maximum reliability | |

**User's choice:** Leave transcript in clipboard (simple, reliable, avoids race conditions with apps and clipboard managers)

### Question 4: User Clarification on Clipboard Behavior
**User input:** "i think always keep it in the clipboard, then i will manually paste it where i want to. if you need to change previous decisions do so"
**Resolved preference:** Dual behavior: Always copy transcript to clipboard AND type into active window (best of both worlds: auto-types, plus clipboard always has it ready for manual paste).

### Final Review & Simplification Analysis
**Simplifications accepted:**
1. Unified Clipboard Flow: Transcript is copied to clipboard unconditionally upfront right after transcription. This fulfills Dual Behavior and eliminates separate reactive failover clipboard copying.
2. Direct wtype stdin stream: Rootless Wayland typing and shortcuts without requiring root ydotoold daemon.

---

## The Agent's Discretion

- Internal timeout duration calibration for wtype processes (15s default).
- Precise CLI argument assembly and process error logging details.

## Deferred Ideas

None — discussion stayed within phase scope.
