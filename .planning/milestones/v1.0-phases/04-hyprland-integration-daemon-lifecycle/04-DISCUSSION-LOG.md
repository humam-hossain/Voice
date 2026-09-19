# Phase 4: Hyprland Integration & Daemon Lifecycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-19
**Phase:** 4-Hyprland Integration & Daemon Lifecycle
**Areas discussed:** Hyprland Keybinding Chords & Upstream Conflict Resolution, Configuration Target & Installation Tooling, Daemon Invocation, Binary Paths & Signal Handling, Desktop UX & Feedback Behavior

---

## Hyprland Keybinding Chords & Upstream Conflict Resolution

### Question 1: STT Push-to-Talk Toggle Chord
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Super+B unbinding upstream | Unbind upstream quickshell sidebar in custom/keybinds.lua | |
| Modified chord (Super+Alt+B) | Avoids modifying Super+B sidebar bind | |
| Alternative chord | Ctrl+Super+Space or Super+Grave | |
| Free-text choice | User specified `SUPER + SHIFT + M` | ✓ |

**User's choice:** `use SUPER + SHIFT + M`
**Notes:** `SUPER + SHIFT + M` was previously bound to volume mute upstream and already unbound in `custom/keybinds.lua`, making it completely free and cleanly aligned with microphone/audio modifiers.

### Question 2: TTS Speak Selection Chord
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) SUPER + SHIFT + T | Leaves SUPER + T intact for opening terminal | |
| SUPER + CTRL + M | Pairs with STT chord under microphone/audio family | |
| SUPER + T unbinding upstream terminal | Unbind upstream terminal bind in custom/keybinds.lua | ✓ |

**User's choice:** `SUPER + T by unbinding the upstream terminal bind in custom/keybinds.lua (hl.unbind("SUPER + T")).`
**Notes:** Retains standard voicemode `Super+T` mnemonic for speech output.

### Question 3: Locked Screen Behavior
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Unlocked only | Standard bind / locked = false: Prevents accidental mic activation or typing while locked | ✓ |
| Allow locked for TTS stop only | Standard bind for STT, allow TTS stop while locked | |
| Allow locked for both | bindl / locked = true | |

**User's choice:** `(Recommended) Unlocked only (standard bind / locked = false): Prevents accidental microphone activation or transcription keystroke injection while the screen is locked.`
**Notes:** Prevents accidental keypresses from activating the microphone or attempting Wayland virtual keyboard injection while `hyprlock` is active.

### Question 4: Upstream Terminal Reassignment
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Simply unbind SUPER + T | No rebind needed, SUPER + Return and CTRL + ALT + T already launch terminal | ✓ |
| Rebind terminal to an alternative chord | Bind terminal to another key in custom/keybinds.lua | |

**User's choice:** `(Recommended) Simply unbind SUPER + T (No rebind needed, since SUPER + Return and CTRL + ALT + T already launch your terminal).`
**Notes:** System inspection verified `SUPER + Return` and `CTRL + ALT + T` are already configured upstream in `hyprland/keybinds.lua`.

---

## Configuration Target & Installation Tooling

### Question 1: Installation Command Behavior
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Auto-detect desktop in --install-hotkey | Check for Hyprland, locate custom/keybinds.lua, safely append block | ✓ |
| Print-only helper | Output snippets to console without modifying files | |
| Dedicated --install-hyprland flag | Only modify when explicitly requested | |

**User's choice:** `(Recommended) Auto-detect desktop in --install-hotkey with safe append: Detect Hyprland session, check for custom/keybinds.lua, and safely append the unbind/bind block if not already present (with --print-hyprland fallback).`

### Question 2: Block Formatting Structure
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Delimited block | `-- voicemode start` ... `-- voicemode end` markers for idempotence | ✓ |
| Append-only without markers | Append raw lines to the end of file | |

**User's choice:** `(Recommended) Delimited block (-- voicemode start ... -- voicemode end): Makes installation idempotent, prevents duplicate blocks if run repeatedly, and enables clean uninstallation or updates.`

### Question 3: Non-dots-hyprland Fallback
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Dual support | Support both custom/keybinds.lua and standard hyprland.conf | |
| Lua custom/keybinds.lua only | Tailor strictly to user's dots-hyprland Lua structure | ✓ |
| Print snippet fallback | Print hyprland.conf snippet to terminal | |

**User's choice:** `Lua custom/keybinds.lua only: Tailor the installer strictly to the dots-hyprland Lua structure present on your system.`

### Question 4: Dynamic Configuration Reload
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Auto-reload | Run `hyprctl reload` immediately after writing block | ✓ |
| Manual reload | Print instruction advising user to reload manually | |

**User's choice:** `(Recommended) Auto-reload: Run hyprctl reload immediately after writing the delimited block so shortcuts become active instantly.`

---

## Daemon Invocation, Binary Paths & Signal Handling

### Question 1: Command Path in Dispatcher
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Full expanded path | `$HOME/.local/bin/voice` in `hl.dsp.exec_cmd` | ✓ |
| Bare command `voice` | Relies on PATH in Hyprland session | |
| Direct launcher | `~/.local/bin/voicemode` | |

**User's choice:** `(Recommended) Full expanded path: ~/.local/bin/voice (or $HOME/.local/bin/voice) in hl.dsp.exec_cmd: Ensures reliability even if Hyprland's systemd/PAM session environment has a restricted PATH.`

### Question 2: PID Race Mitigation
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Parent writes PID immediately upon Popen | Eliminates startup race window | ✓ |
| File-based lock during toggle | Advisory flock around toggle | |
| Keep current child write_pid | Child writes PID when ready | |

**User's choice:** `(Recommended) Parent writes PID immediately upon Popen: The parent writes the spawned child's PID into recorder.pid right after Popen, eliminating the startup race window.`

### Question 3: Hotkey Behavior during Transcription
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Ignore keypresses while transcribing | Retain PID until typing finishes, emit busy cue if pressed | ✓ |
| Abort active transcription | Kill worker and start fresh recording | |
| Queue new recording | Wait for transcription, then record | |

**User's choice:** `(Recommended) Ignore keypresses while transcribing: The recorder process retains its PID until typing completes; pressing the toggle while transcribing emits a subtle notification/cue or is safely ignored so typing isn't corrupted.`

### Question 4: PID Verification Hardening
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Enhanced process verification | Check `/proc/<pid>/cmdline` before signaling | ✓ |
| Standard os.kill(pid, 0) | POSIX check only | |

**User's choice:** `(Recommended) Enhanced process verification: Check /proc/<pid>/cmdline to ensure the PID actually belongs to voicemode/python before signaling, preventing misdirected signals if a PID was recycled.`

### Question 5: Safety Ceiling Duration
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Keep 300s default with env override | 5 min ceiling, overrideable via VOICE_MAX_RECORDING_SECONDS | ✓ |
| Shorter 120s default | 2 min ceiling | |
| Short 60s default | 1 min ceiling | |

**User's choice:** `(Recommended) Keep 300s (5 min) default with env var override (VOICE_MAX_RECORDING_SECONDS): Generous ceiling allowing both short sentences and extended thoughts without cutting off, configurable if needed.`

### Question 6: Transcription Watchdog Timeout
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) 60-second watchdog timeout | Log error, clean PID, and exit safely if transcribing/typing hangs | ✓ |
| No watchdog timeout | Let transcription run indefinitely | |

**User's choice:** `(Recommended) 60-second watchdog timeout: If transcription or typing takes longer than 60s, log an error, clean up the PID file, and exit safely to prevent permanent lockouts.`

### Question 7: TTS Auto-Stop on STT Start
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Auto-stop TTS on STT start | Silence TTS playback immediately when recording starts | ✓ |
| Keep independent | Allow concurrent playback and recording | |

**User's choice:** `(Recommended) Auto-stop TTS on STT start: Immediately silence active TTS playback when starting a voice recording to prevent speaker audio bleeding into the microphone.`

### Question 8: Signal Differentiation (SIGTERM vs SIGUSR1)
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Abort without transcribing on SIGTERM/SIGINT | Clean up audio and PID; reserve transcription for SIGUSR1 | ✓ |
| Transcribe on all signals | Transcribe regardless of signal type | |

**User's choice:** `(Recommended) Abort without transcribing on SIGTERM/SIGINT: Clean up audio file and PID without typing into focused window; reserve transcription strictly for intentional SIGUSR1 toggles.`

---

## Desktop UX & Feedback Behavior

### Question 1: STT Notification Feedback
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Audio cues primary, notifications for errors only | Rely on start/stop chimes, suppress routine toasts | ✓ |
| Full desktop notifications | Show toasts on every state transition | |
| Completion toast only | Audio cues for start/stop, toast on completion | |

**User's choice:** `(Recommended) Audio cues primary, notifications for errors only: Rely on instant start/stop audio chimes during normal push-to-talk to keep the screen distraction-free, showing desktop toasts only for errors, no-speech, or timeout warnings.`

### Question 2: TTS Notification Feedback
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Keep TTS preview and stop toasts | Show preview toast and stopped toast | ✓ |
| Errors-only for TTS | Silent playback, notify on error only | |

**User's choice:** `(Recommended) Keep TTS preview and stop toasts: Keep the snippet toast ('Speaking selection: "..."') and 'Speech stopped' toast so you know exactly what text was captured and spoken.`

### Question 3: Periodic Reminder Cue
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Silent recording | Silent between start chime and stop chime | |
| Periodic reminder cue | Quiet audio tick every 5s while recording | ✓ |

**User's choice:** `Periodic reminder cue: Quiet audio tick every 5s while recording to ensure you know the microphone is active.`

### Question 4: Notification Urgent & Timeout Flags
| Option | Description | Selected |
|--------|-------------|----------|
| (Recommended) Fast-expiring low-urgency toasts | `-u low -t 2000` for informational toasts | ✓ |
| System default notification timing | Use system daemon defaults | |

**User's choice:** `(Recommended) Fast-expiring low-urgency toasts (-u low -t 2000): Automatically dismiss toasts after 2 seconds with low urgency so they never accumulate or block screen space.`

---

## the Agent's Discretion

- 300ms polling timeout for startup readiness in `toggle_background_recording()`.
- Explicit state progression in `recorder.pid` (`starting`, `recording`, `transcribing`, `idle`).
- Regex pattern matching for idempotent replacement of delimited `-- voicemode start` blocks.

## Deferred Ideas

None — discussion stayed strictly within Phase 4 scope.
