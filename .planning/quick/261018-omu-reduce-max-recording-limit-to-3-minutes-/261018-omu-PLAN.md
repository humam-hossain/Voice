# Quick Plan: Reduce max recording limit to 3 minutes and fix stuck keyboard keys on typing timeout

**Goal:** Reduce `MAX_RECORDING_SECONDS` from 300.0s to 180.0s (3 minutes), dynamically scale typing timeout in `type_text` to prevent premature process termination on long transcripts, and ensure virtual keyboard keys are safely released if typing ever fails or is interrupted.

**Files in scope:** `voice.py`, `tests/test_wayland_input.py`, `tests/test_hyprland_daemon.py`

## Context & Root Cause Analysis

1. **Why the 'T' key gets stuck:**
   - In Wayland, `voice.py` uses `wtype` or `ydotool` to inject typed text into the active window.
   - For long dictations (>3 minutes, >2000 chars), `type_text()` previously enforced a rigid static `timeout=15.0` seconds.
   - Typing 2,500+ characters with Wayland round-trip latency takes 16-25 seconds, triggering `subprocess.TimeoutExpired`.
   - When Python kills `wtype` or `ydotool` with `SIGKILL` mid-stroke, whatever key was currently down (in English dictation, frequently 't' or 'y') never receives a corresponding `key-up` release event.
   - For `ydotool`, the persistent background daemon `ydotoold` maintains the virtual keyboard state in the Linux kernel `/dev/uinput` device (`ydotoold-virtual-device`), leaving `KEY_T` (keycode 20) permanently held down. Hyprland sees the key as down, blocking physical keyboard input for that key.

2. **Why 3 minutes recording limit:**
   - The user requested capping recording duration to 3 minutes max (`MAX_RECORDING_SECONDS = 180.0`) so the recorder automatically stops and transitions to transcription after 3 minutes instead of running for 5 minutes.

## Tasks

### Task 1: Update recording ceiling constant to 180.0s (3 minutes)
- In `voice.py`, set `MAX_RECORDING_SECONDS = 180.0`.
- Preserve environment variable override `VOICE_MAX_RECORDING_SECONDS`.
- Update any docstrings/help strings referencing the 300-second maximum.

### Task 2: Dynamically scale typing timeout and add key release cleanup
- Add a helper `typing_timeout(text: str, type_delay: int) -> float`:
  - Returns `15.0` for text <= 50 characters (preserving existing test expectations and fast timeouts for small inputs).
  - For longer text, computes `max(15.0, (len(text) * (max(0, type_delay) + 25) / 1000.0) * 2.0 + 15.0)` to provide ample headroom based on transcript length and typing delay.
- In `type_text()`:
  - Use `timeout = typing_timeout(text, type_delay)`.
  - Add a safety cleanup helper `release_stuck_keys()` that sends key-up events (via `ydotool key` if available) whenever typing raises an exception or times out, ensuring no virtual keys remain stuck in `ydotoold`.
- Do not blindly attempt to re-type the entire text with `ydotool` if `wtype` timed out (retyping after timeout doubles already-typed text). Fall back only if `wtype` fails to start or exits immediately with an error code before typing.

### Task 3: Unit tests & verification
- Update `tests/test_wayland_input.py` to test:
  - Dynamic `typing_timeout` scaling for short and long text.
  - Verification that short text still uses `15.0` timeout.
  - Error/timeout handling does not leave unhandled exceptions.
- Update `tests/test_hyprland_daemon.py` to verify `max_recording_seconds()` defaults to `180.0`.
- Run full test suite using `.venv/bin/python -m unittest discover tests`.

**Verify:** All unit tests pass, compilation passes with `py_compile`, and `MAX_RECORDING_SECONDS` is 180.0.
