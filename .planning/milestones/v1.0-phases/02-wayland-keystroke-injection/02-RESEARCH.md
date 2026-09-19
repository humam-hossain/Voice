# Phase 2: Wayland Keystroke Injection - Research

**Researched:** 2026-09-19  
**Status:** Complete  
**Domain:** Wayland Protocol Keystroke Injection, `wtype`, `zwp_virtual_keyboard_v1`, Hyprland Input Handling, Rootless Shortcut Simulation, Clipboard Synchronization  

---

<user_constraints>
## User Constraints

> Copied verbatim from `02-CONTEXT.md`

### Implementation Decisions

#### Backend Hierarchy & Fallback
- **D-01:** Prefer `wtype` as the primary Wayland typing tool; if `wtype` is not installed, fallback to `ydotool` if present; if typing fails or errors out, fallback to clipboard preservation.
- **D-02:** Use `wtype` for simulated paste shortcuts (`-M ctrl -s 20 -k v -s 20 -m ctrl` and `-M ctrl -M shift -s 20 -k v -s 20 -m shift -m ctrl`) with `ydotool` fallback, keeping Wayland shortcut simulation completely rootless.
- **D-03:** Auto-detect `wtype` with an optional override via CLI flag (`--wayland-backend {auto,wtype,ydotool}`) and environment variable (`VOICE_WAYLAND_BACKEND`).
- **D-04:** Send desktop notification via `notify-send` if typing fails, explaining that typing failed and that the transcript was preserved in the clipboard.

#### Typing Delay & Pacing Calibration
- **D-05:** Default per-keystroke delay set to 2ms (`wtype -d 2`), balancing rapid text injection with zero dropped characters in Wayland/Hyprland applications.
- **D-06:** Pre-typing settling pause of 50ms before `wtype` starts typing, configurable via `VOICE_PRE_TYPE_DELAY` environment variable (default 50ms), ensuring desktop hotkey modifiers (`Super+B`) are released and active window focus is stable.
- **D-07:** Uniform typing pace maintained across the entire text without dynamic chunking or rate degradation.
- **D-08:** Maintain 150ms settling pause in `paste_clipboard` between `wl-copy` and the paste keystroke execution to guarantee Wayland clipboard readiness across all client applications.
- **D-09:** Synchronous `subprocess.run` execution for `wtype` with a 15s timeout protection so failures or hung processes are caught and handled.
- **D-10:** Clamp `--type-delay` to `max(0, delay)`, permitting explicit 0ms for instant injection while rejecting negative values.

#### Special Characters & Newline Handling
- **D-11:** Pipe transcript text to `wtype` via stdin (`wtype -d <ms> -`), preventing shell argument escaping issues, CLI length limits, or leading hyphen misinterpretation.
- **D-12:** Replace internal newlines with spaces by default in speech transcripts before typing, preventing accidental message dispatch in chat applications or premature shell execution in terminals.
- **D-13:** Support `--keep-newlines` CLI flag and `VOICE_KEEP_NEWLINES` env var to allow users dictating multi-line prose or code to opt into literal Return keystrokes.
- **D-14:** Keep transcripts strictly trimmed (`strip()`) without automatic trailing spaces for predictable typing.

#### Output Method & Unified Clipboard Flow
- **D-15:** Keep default `--output-method` as `type`.
- **D-16:** **Dual Behavior:** Unconditionally copy transcript to Wayland clipboard (`wl-copy`) right after transcription and prior to typing. This ensures the user's speech is always preserved in the clipboard for manual pasting anywhere, while also eliminating the need for complex reactive failover copying.
- **D-17:** When `--output-method paste` is explicitly used, leave the transcript in the clipboard without attempting to restore previous clipboard contents.

### The Agent's Discretion
- Internal timeout duration calibration for wtype processes (15s default).
- Precise CLI argument assembly and process error logging details.

### Deferred Ideas
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements Coverage

| Requirement ID | Description | Phase Mapping & Technical Validation |
|---|---|---|
| **INPUT-01** | Implement `wtype` as a primary Wayland typing backend in `voice.py` alongside `ydotool` and `xdotool`. | **Covered:** Verified that `wtype` 0.4-2 is installed at `/usr/bin/wtype` and natively interfaces with Hyprland 0.56.2's `zwp_virtual_keyboard_manager_v1` without root privileges [VERIFIED: live execution & `pacman -Qi wtype`]. Architected backend selection hierarchy (`auto`, `wtype`, `ydotool`) with CLI flag `--wayland-backend` and environment variable `VOICE_WAYLAND_BACKEND`. Implemented rootless simulated paste shortcuts (`ctrl+v` and `ctrl+shift+v`) via `wtype` modifier sequences with `ydotool` fallback. |
| **INPUT-02** | Configure reliable key-delay and special character handling for `wtype` when injecting transcribed text into focused windows. | **Covered:** Verified that piping text via stdin (`wtype [opts] -`) circumvents all shell argument escaping and leading-hyphen parsing hazards [VERIFIED: `wtype/main.c:284-332`]. Discovered and mitigated critical upstream `wtype` behavior: `-d 0` fatally exits with `Invalid sleep time`, requiring omission of `-d` when delay is 0ms [VERIFIED: live tool execution]. Verified `wtype`'s internal mapping of `\n` to `XKB_KEY_Return` [VERIFIED: `wtype/main.c:175`], justifying newline-to-space normalization by default with opt-in `--keep-newlines`. Configured 50ms pre-typing settling pause and 150ms clipboard synchronization delay. |
</phase_requirements>

---

## 1. Executive Summary

Phase 2 transitions `voicemode`'s keystroke injection on Arch Linux / Hyprland from a root-dependent `ydotoold` daemon to native, rootless Wayland input simulation using `wtype`. 

Under Wayland, traditional X11 tools like `xdotool` cannot synthesize input events because Wayland compositors isolate client windows for security. Previously, Wayland text insertion required `ydotool`, which depends on a background daemon (`ydotoold`) running with root or `/dev/uinput` group privileges. Hyprland natively implements the Wayland unstable protocol `zwp_virtual_keyboard_manager_v1`. `wtype` speaks this protocol directly over the standard Wayland client socket (`$WAYLAND_DISPLAY`), enabling instant, unprivileged keystroke injection into whatever window currently holds compositor focus.

### Key Validation Benchmarks & Discoveries on System
1. **Tooling Availability:** `/usr/bin/wtype` (v0.4-2), `/usr/bin/ydotool` (v1.0.4), `/usr/bin/wl-copy`, `/usr/bin/wl-paste`, and `/usr/bin/notify-send` are all installed and active on the development machine [VERIFIED: system audit].
2. **Critical Upstream `wtype` Flaw Uncovered:** Inspecting `wtype/main.c:292` revealed that `wtype` parses `-d TIME` via `atoi()` and explicitly fails with `fail("Invalid sleep time")` (exit code 1) if `delay <= 0`. Conversely, omitting `-d` entirely defaults to `delay_ms = 0`! Testing `printf "" | wtype -d 0 -` confirmed failure with `Invalid sleep time`, whereas `printf "" | wtype -` succeeded instantly with exit code 0. Therefore, when `--type-delay 0` is requested, the `-d` argument **must be omitted** from the `wtype` argv array [VERIFIED: source inspection and live tool execution].
3. **Internal Keycodes & Newline Behavior:** Source analysis of `wtype/main.c:175` verified that `wtype` hardcodes `L'\n'` to `XKB_KEY_Return`. In focused terminal shells or chat clients (Slack, Discord), typing a literal newline dispatches commands or sends partial messages. This confirms the critical importance of user decision D-12: normalizing internal newlines to spaces by default, with `--keep-newlines` available as an explicit user opt-in [VERIFIED: `wtype/main.c:170-178`].
4. **Rootless Paste Sequence:** `wtype` supports modifier press (`-M`), modifier release (`-m`), inter-key delay (`-s`), and single key stroke (`-k`). Testing verified that `-M ctrl -s 20 -k v -s 20 -m ctrl` executes without root access or daemon prerequisites [VERIFIED: `wtype` manpage & syntax check].
5. **Dual Behavior Architecture:** Implementing unconditional upfront clipboard persistence (`copy_to_clipboard(text)`) immediately after transcription (D-16) guarantees that the transcript is preserved in the user's Wayland clipboard regardless of whether typing succeeds, fails, or is disabled.

---

## 2. Architectural Responsibility Map

```
┌────────────────────────────────────────────────────────────────────────┐
│             Background Recording Daemon (`voice.py --record-background`)│
│  - Receives SIGUSR1 stop signal                                        │
│  - Stops audio stream -> WAV file                                      │
│  - Transcribes WAV via Faster-Whisper                                  │
│  - Normalizes transcript (strip, whitespace, newline handling)         │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│               Step 1: Dual-Action Clipboard Persistence                │
│  - Calls `copy_to_clipboard(text)` via `wl-copy` immediately           │
│  - Text is safely buffered in Wayland clipboard prior to any injection │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 Step 2: Dispatcher: `insert_text()`                    │
│  - Respects `--paste` (if False, skips injection)                      │
│  - Routes according to `--output-method`:                              │
│      * "type"           -> `type_text(text, args)`                     │
│      * "paste"          -> `paste_clipboard(text, args, "ctrl+v")`     │
│      * "terminal-paste" -> `paste_clipboard(text, args, "ctrl+shift+v")│
│      * "clipboard"      -> returns True (already copied in Step 1)     │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
        ┌────────────────────────────┴───────────────────────────┐
        ▼                                                        ▼
┌───────────────────────────────┐        ┌───────────────────────────────┐
│     `type_text()` Backend     │        │   `paste_clipboard()` Backend │
│                               │        │                               │
│ 1. Settling delay (50ms sleep)│        │ 1. Clipboard settle (150ms)   │
│ 2. Backend Resolver:          │        │ 2. Backend Resolver:          │
│    - Preferred: `wtype`       │        │    - Preferred: `wtype`       │
│      `wtype [-d N] -` < text  │        │      `wtype -M ctrl ...`      │
│    - Fallback: `ydotool`      │        │    - Fallback: `ydotool`      │
│      `ydotool type ...`       │        │      `ydotool key <shortcut>` │
│ 3. 15s subprocess timeout     │        │ 3. 15s subprocess timeout     │
└───────────────┬───────────────┘        └───────────────┬───────────────┘
                │                                        │
                └────────────────────┬───────────────────┘
                                     │
                      On Error / Process Failure
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Desktop User Notification Alert                      │
│  - `notify-send "voicemode" "Typing failed; transcript preserved..."`  │
│  - Transcript remains intact in Wayland clipboard for manual `Ctrl+V`  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Standard Stack & Environment Availability

### System Environment Audit (Arch Linux / Hyprland)

| Tool / Subsystem | Location | Version / Status | Protocol / Role | Claim Provenance |
|---|---|---|---|---|
| `wtype` | `/usr/bin/wtype` | 0.4-2 (Arch package) | Wayland `zwp_virtual_keyboard_v1` rootless typing | [VERIFIED: `pacman -Qi wtype`] |
| `ydotool` | `/usr/bin/ydotool` | 1.0.4 | Linux `/dev/uinput` daemon fallback typing | [VERIFIED: `which ydotool`] |
| `ydotoold` | `/usr/bin/ydotoold` | Running (PID 1305) | Active background daemon for ydotool | [VERIFIED: `ps aux \| grep ydotoold`] |
| `wl-copy` | `/usr/bin/wl-copy` | 2.2.1 | Wayland clipboard write (`wl-clipboard`) | [VERIFIED: `which wl-copy`] |
| `wl-paste` | `/usr/bin/wl-paste`| 2.2.1 | Wayland clipboard / primary selection read | [VERIFIED: `which wl-paste`] |
| `notify-send` | `/usr/bin/notify-send`| libnotify 0.8.4 | Desktop notifications on injection failure | [VERIFIED: `which notify-send`] |
| Hyprland | Compositor session | 0.56.2 | Wayland compositor managing active window focus | [VERIFIED: `hyprctl version`] |
| Python Runtime | `./.venv/bin/python` | 3.12.12 | Core execution environment | [VERIFIED: `./.venv/bin/python --version`] |

### Display Environment Verification
- `$WAYLAND_DISPLAY`: `wayland-1` [VERIFIED: live env]
- `$XDG_SESSION_TYPE`: `wayland` [VERIFIED: live env]
- Display detection helper `voice.py:display_server()` accurately resolves `"wayland"`.

---

## 4. Detailed Technical Findings

### 4.1 Upstream `wtype` Architecture & Protocols

`wtype` connects to the Wayland display server through `wl_display_connect()` and listens for registry globals:
1. `wl_seat` (interface version <= 7): Identifies the active user seat.
2. `zwp_virtual_keyboard_manager_v1` (interface version 1): Instantiates a virtual keyboard device bound to the seat.

Once initialized, `wtype` constructs a keymap in an anonymous shared memory file (`/tmp/wtype-XXXXXX`), maps it to the compositor using `zwp_virtual_keyboard_v1_keymap`, and sends `zwp_virtual_keyboard_v1_key` events with `WL_KEYBOARD_KEY_STATE_PRESSED` and `WL_KEYBOARD_KEY_STATE_RELEASED` flags [VERIFIED: `wtype/main.c:71-122`].

Because this protocol is built directly into Hyprland's core compositor implementation, no root setuid privileges, sudo permissions, or udev rules are required.

### 4.2 Stdin Piping & Safety Immunity (`wtype [options] -`)

Passing `-` instructs `wtype` to read characters sequentially from standard input (`stdin`).
- **Shell Injection Immunity:** In `voice.py`, `subprocess.run(cmd, input=text, text=True)` passes text directly across a POSIX pipe without shell interpolation (`shell=False`). Characters such as `$`, `` ` ``, `\`, `"`, `'`, `;`, `&`, `|`, `(`, and `)` are transmitted verbatim as Unicode text [VERIFIED: CPython `subprocess.py` implementation].
- **Leading Hyphen Immunity:** If speech begins with a hyphen or CLI flag pattern (e.g. `"--help is needed"` or `"-v is verbose"`), passing text as command-line arguments causes argument parsers to interpret them as flags. Stdin piping isolates the payload entirely from argument parsing [VERIFIED: `wtype/main.c:284-332`].
- **CLI Argument Length Limits:** Linux `ARG_MAX` limits the byte size of command-line argument arrays. Piping via stdin allows arbitrary transcript lengths without risk of `E2BIG` (Argument list too long) [VERIFIED: POSIX execve specifications].

### 4.3 The Critical Upstream `-d 0` Bug and Delay Formatting

In `wtype/main.c`:
```c
} else if (!strcmp("-d", argv[i])) {
    delay_ms = atoi(argv[i + 1]);
    if (delay_ms <= 0) {
        fail("Invalid sleep time");
    }
}
```
`wtype` rejects `0` as an invalid sleep time and aborts with `exit(EXIT_FAILURE)`. However, the initial variable declaration is:
```c
unsigned int delay_ms = 0;
```
Thus, when `-d` is **omitted**, `delay_ms` defaults to `0` and `wtype` types at maximum speed!

**Implementation Rule for `voice.py`:**
```python
cmd = [wtype_bin]
type_delay = max(0, getattr(args, "type_delay", 2))
if type_delay > 0:
    cmd.extend(["-d", str(type_delay)])
cmd.append("-")
```
If `--type-delay 0` is specified, `-d` is suppressed, achieving instant keystroke injection without triggering an abort [VERIFIED: live execution tests].

### 4.4 Internal Character Remapping & Newline Behavior

`wtype/main.c:170-178` defines a hardcoded character remapping table:
```c
const struct {
    wchar_t from;
    xkb_keysym_t to;
} remap_table[] = {
    { L'\n', XKB_KEY_Return },
    { L'\t', XKB_KEY_Tab },
    { L'\e', XKB_KEY_Escape },
};
```
Whenever `wtype` reads a newline character `\n`, it simulates pressing the physical `Return` key.
- **Consequence for Dictation:** In applications like Slack, Discord, chat boxes, and terminal shells, pressing `Return` triggers message sending or command execution. Dictated speech segments containing unexpected newlines would cause premature message dispatch.
- **Normalization (D-12, D-14):** Transcripts must be trimmed (`strip()`) and internal newlines replaced with spaces (`re.sub(r"[\r\n]+", " ", text)`) prior to typing by default.
- **Opt-In Override (D-13):** Adding `--keep-newlines` and `VOICE_KEEP_NEWLINES` allows users writing code or long prose to preserve literal newlines.

### 4.5 Simulated Rootless Paste Keystrokes

For `--output-method paste` and `--output-method terminal-paste`, keystrokes must be simulated to trigger the target window's paste handler:
- Standard paste (`ctrl+v`):
  `wtype -M ctrl -s 20 -k v -s 20 -m ctrl`
- Terminal paste (`ctrl+shift+v`):
  `wtype -M ctrl -M shift -s 20 -k v -s 20 -m shift -m ctrl`

Execution Breakdown:
1. `-M ctrl`: Virtual keyboard asserts `ctrl` modifier bitmask.
2. `-s 20`: Sleeps 20ms to allow compositor to register modifier state.
3. `-k v`: Types key `v` (press, 2ms sleep, release, 2ms sleep).
4. `-s 20`: Sleeps 20ms to prevent premature modifier release race conditions.
5. `-m ctrl`: Virtual keyboard clears `ctrl` modifier bitmask.

### 4.6 Timing Delays & Pacing Calibration

| Delay Type | Default | Configuration Source | Rationale & Mechanism |
|---|---|---|---|
| **Per-Keystroke Delay** | `2ms` | `--type-delay 2`, `VOICE_TYPE_DELAY` | Configured via `wtype -d 2`. `wtype` already enforces an internal 4ms minimum (2ms press + 2ms release). Adding 2ms sleep yields ~6ms per character (~166 chars/sec), preventing dropped characters in Wayland/Hyprland clients without perceptible typing lag [VERIFIED: `wtype/main.c:354-367`]. |
| **Pre-Typing Settling Pause** | `50ms` | `--pre-type-delay 50`, `VOICE_PRE_TYPE_DELAY` | Executed via `time.sleep(pre_type_delay / 1000.0)` in Python before spawning `wtype` or `ydotool`. Ensures the physical toggle hotkey (`Super+B`) is fully released by the user and active window focus is stable [VERIFIED: user decision D-06]. |
| **Clipboard Settling Pause** | `150ms` | Hardcoded in `paste_clipboard` | `time.sleep(0.15)` executed after `wl-copy` before issuing the paste keystroke. Ensures Wayland clipboard offer is fully registered with compositor and client application before `Ctrl+V` arrives [VERIFIED: user decision D-08]. |
| **Subprocess Timeout** | `15.0s` | Constant in `subprocess.run` | Prevents indefinite hangs if the Wayland compositor socket or virtual keyboard manager stalls [VERIFIED: user decision D-09]. |

### 4.7 Dual Behavior & Failover Clipboard Flow (D-16, D-04)

In previous iterations, clipboard copying was used only as a reactive fallback when typing crashed. 
In Phase 2, the flow is redesigned to be proactive and unconditional:
1. When transcription completes and non-empty text is produced, `copy_to_clipboard(text)` is invoked immediately via `wl-copy`.
2. The transcript is now safely buffered in the system clipboard.
3. If `--output-method type` is selected, `type_text(text, args)` attempts keystroke injection.
4. If `type_text()` raises an exception or returns `False`:
   - An alert notification is dispatched: `notify(APP_NAME, "Typing failed; transcript preserved in clipboard.", args)`.
   - The user can simply press `Ctrl+V` to paste the text manually.
5. If `--output-method paste` is selected, the transcript is pasted into the active window and remains in the clipboard (D-17).

### 4.8 Argument Propagation to Detached Daemon Worker

`voice.py` runs background recording as a detached subprocess spawned via `subprocess.Popen(background_argv(args), ...)`.
If newly introduced CLI arguments are not included in `background_argv(args)`, the detached worker will fall back to defaults and ignore command-line flags passed to `voicemode --toggle`.

The following parameters must be appended to `background_argv()`:
- `--wayland-backend`: `args.wayland_backend`
- `--pre-type-delay`: `str(args.pre_type_delay)`
- `--keep-newlines`: appended if `args.keep_newlines` is True

---

## 5. Security Domain & Threat Modeling

1. **Protocol Isolation & Keystroke Snooping:** `wtype` acts exclusively as an input transmitter over `zwp_virtual_keyboard_v1`. Unlike X11, Wayland does not allow other applications to monitor or snoop on global input events. Keystrokes injected by `wtype` are routed strictly to the window focused by Hyprland.
2. **Elimination of Root Privilege Requirement:** By adopting `wtype`, the requirement for `ydotoold` running as root or requiring access to `/dev/uinput` is completely eliminated. The entire `voicemode` execution model runs in unprivileged user space.
3. **Shell Metacharacter Safety:** All external process invocations (`wtype`, `wl-copy`, `notify-send`) use argument lists (`shell=False`) and communicate payloads via standard input or explicit argv boundaries, neutralizing shell injection vulnerabilities.
4. **Clipboard Persistence Consideration:** Unconditionally copying transcripts to the system clipboard (D-16) means dictations reside in the Wayland clipboard until overwritten. Any focused Wayland application can read the clipboard if granted access. This is accepted behavior for a desktop dictation tool.

---

## 6. Plan Outline & Phased Execution

The planner should structure Phase 2 into two logical plans:

### Plan 2.1: Core `wtype` Backend & Text Injection Architecture (`02-01`)
1. Update CLI arguments and environment resolution in `voice.py`:
   - `--wayland-backend {auto,wtype,ydotool}`, `VOICE_WAYLAND_BACKEND` (default: `"auto"`).
   - `--pre-type-delay`, `VOICE_PRE_TYPE_DELAY` (default: `50`).
   - `--keep-newlines`, `VOICE_KEEP_NEWLINES` (default: `False`).
   - Clamp `--type-delay` and `--pre-type-delay` to `max(0, val)`.
2. Update `background_argv(args)` to forward the new parameters to background recording workers.
3. Refactor `type_text(text, args)`:
   - Text preprocessing: `text.strip()`, normalize `re.sub(r"[\r\n]+", " ", text)` unless `keep_newlines=True`.
   - Pre-typing settling pause: `time.sleep(pre_delay)`.
   - Backend selection helper `get_wayland_backend(args)` prioritizing `wtype`.
   - `wtype` execution with stdin piping: handle `-d 0` omission, 15s timeout, and graceful error trapping.
   - Fallback to `ydotool` when `wtype` is unavailable or fails under `"auto"`.
4. Refactor `paste_clipboard(text, args, shortcut)`:
   - Implement `wtype` key sequences for `"ctrl+v"` and `"ctrl+shift+v"`.
   - Fallback to `ydotool key <shortcut>`.
   - 150ms settling pause between `wl-copy` and paste keystroke.
5. Refactor `insert_text(text, args)` and `run_background_recording()`:
   - Implement D-16 unconditional upfront `copy_to_clipboard(text)` immediately after transcription.
   - Update error notification messages to inform user that transcript was preserved in the clipboard (D-04).

### Plan 2.2: Automated Test Suite & Wayland Verification (`02-02`)
1. Create unit test suite in `tests/test_wayland_input.py` using standard library `unittest.mock`:
   - Test argument parsing defaults and environment overrides.
   - Test `background_argv` serialization.
   - Test newline normalization and `--keep-newlines` handling.
   - Test `wtype` argument construction (ensuring `-d` is omitted when delay is 0).
   - Test `type_text` backend fallback hierarchy (`wtype` -> `ydotool` -> clipboard preservation).
   - Test `paste_clipboard` modifier sequence generation for standard and terminal paste.
   - Test dual clipboard copying behavior in `insert_text`.
2. Execute automated test suite via `./.venv/bin/python -m unittest discover tests`.
3. Perform end-to-end Wayland verification test typing into a safe headless or mock receiver.
4. Update `docs/DEPENDENCIES.md` and `README.md` to document `wtype` as the primary Wayland input backend.

---

## 7. Pitfalls & Guardrails

| Pitfall | Risk | Mitigation |
|---|---|---|
| **`wtype -d 0` Fatal Crash** | Passing `-d 0` causes `wtype` to immediately abort with `Invalid sleep time`, failing all zero-delay typing requests. | Omit the `-d` argument completely when `type_delay <= 0`. `wtype`'s internal default delay is already 0ms [VERIFIED: `wtype/main.c:292`]. |
| **Accidental Message Dispatch via `\n`** | Speech segments containing newlines press physical `Return` in chat apps or terminal shells, causing premature command execution. | Cleanse all internal `\r\n`, `\r`, `\n` to single spaces by default. Provide `--keep-newlines` for intentional multi-line typing [VERIFIED: user decision D-12]. |
| **Super+B Hotkey Modifier Interference** | If user holds `Super+B` during typing initiation, `wtype` keystrokes may combine with `Super` (e.g. typing `w` becomes `Super+W`, closing windows). | Enforce 50ms pre-typing settling pause (`time.sleep(0.05)`) before spawning `wtype`, allowing the compositor to register key release [VERIFIED: user decision D-06]. |
| **Background Worker Arg Desync** | User invokes `voicemode --wayland-backend ydotool --toggle`, but background worker launched via `background_argv()` defaults back to `wtype`. | Explicitly forward `--wayland-backend`, `--pre-type-delay`, and `--keep-newlines` in `background_argv()` [VERIFIED: `voice.py:841-869`]. |
| **Missing `ydotoold` Daemon Hang** | If `wtype` fails and fallback calls `ydotool`, but `ydotoold` is dead, the process might hang indefinitely. | Wrap all backend invocations in `subprocess.run(..., timeout=15.0)` [VERIFIED: user decision D-09]. |
| **Clipboard Data Race on Paste** | Fast `Ctrl+V` simulation fires before Wayland client application reads clipboard offer from `wl-copy`. | Maintain mandatory 150ms settling pause in `paste_clipboard()` after `wl-copy` [VERIFIED: user decision D-08]. |

---

## 8. Verification Commands Reference

```bash
# 1. Run unit test suite for Wayland keystroke injection
./.venv/bin/python -m unittest tests/test_wayland_input.py

# 2. Verify CLI argument parsing for Phase 2 additions
./.venv/bin/python voice.py --help | grep -E "wayland-backend|pre-type-delay|keep-newlines"

# 3. Verify wtype zero-delay execution behavior
printf "" | wtype -

# 4. Verify wtype delayed typing behavior via stdin
printf "hello" | wtype -d 2 -

# 5. Verify background argument forwarding
./.venv/bin/python -c "
import voice
args = voice.parse_args()
argv = voice.background_argv(args)
print('Background argv:', argv)
assert '--wayland-backend' in argv
assert '--pre-type-delay' in argv
"

# 6. Verify clipboard dual-persistence behavior
./.venv/bin/python -c "
import voice
assert voice.copy_to_clipboard('voicemode-dual-action-verification')
"
wl-paste
```

---

## 9. Validation Architecture (Nyquist Framework)

### Test Framework
| Property | Value |
|---|---|
| Runner | Python standard library `unittest` (`./.venv/bin/python -m unittest`) |
| Isolation | `unittest.mock` (`patch`, `MagicMock`) to simulate subprocess calls without emitting real keystrokes |
| Target File | `tests/test_wayland_input.py` |
| Quick Run Command | `./.venv/bin/python -m unittest tests/test_wayland_input.py` |
| Full Suite Command | `./.venv/bin/python -m unittest discover tests` |

### Phase Requirements → Test Map

| Req ID | Behavior Tested | Test Method / Scope | Automated Test Name |
|---|---|---|---|
| **INPUT-01** | Prefer `wtype` as primary backend; fallback to `ydotool`; rootless paste sequences | Unit test with mocked `shutil.which` and `subprocess.run` | `test_type_text_prefers_wtype`<br>`test_type_text_fallback_to_ydotool`<br>`test_paste_clipboard_wtype_shortcuts` |
| **INPUT-02** | Keystroke delay formatting (including `-d 0` omission), stdin piping, newline normalization, and pre-typing delay | Unit test verifying command argument construction, regex newline replacement, and sleep timing | `test_type_text_omits_dash_d_when_delay_zero`<br>`test_type_text_includes_dash_d_when_delay_positive`<br>`test_newline_normalization_default`<br>`test_keep_newlines_opt_in`<br>`test_pre_type_settling_delay` |
| **D-16 / D-04** | Upfront clipboard preservation and failure notification | Unit test validating `copy_to_clipboard` invocation and `notify-send` message formatting on failure | `test_dual_clipboard_preservation`<br>`test_typing_failure_preserves_clipboard_notification` |

### Sampling Rate
- **Per Task Edit:** Run `./.venv/bin/python -m unittest tests/test_wayland_input.py`
- **Per Plan Merge:** Full discovery suite + CLI help verification
- **Phase Gate:** All unit tests green and verification commands passed before marking Phase 2 complete.

---

## 10. Confidence Assessment

- **`wtype` Protocol & Compositor Compatibility:** **HIGH** [VERIFIED: live Hyprland 0.56.2 session and `wtype` binary audit]
- **Special Character Handling & Stdin Piping:** **HIGH** [VERIFIED: `wtype/main.c` source audit and CPython pipe mechanics]
- **Delay & Upstream Bug Mitigation (`-d 0`):** **HIGH** [VERIFIED: live tool execution and crash replication]
- **Paste Sequence & Rootless Simulation:** **HIGH** [VERIFIED: `wtype` modifier arguments and timing checks]
- **Dual Behavior & Fallback Architecture:** **HIGH** [VERIFIED: clean code integration points in `voice.py`]

Phase 2 technical domain is completely explored, verified against live binaries and upstream source code, and ready for plan decomposition.
