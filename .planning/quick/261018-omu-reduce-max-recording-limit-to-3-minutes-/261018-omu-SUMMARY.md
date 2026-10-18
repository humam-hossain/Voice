---
phase: quick-task
plan: 261018-omu
subsystem: stt-wayland-input
tags: [stt, timeout, wayland, ydotool, wtype, hyprland]
requires: []
provides:
  - 3-minute max recording limit (180.0s) with auto-stop and transcription
  - Dynamic typing timeout scaling based on transcript length to prevent premature process termination
  - Emergency virtual keyboard key release on typing error/timeout and --reset-keys CLI utility
affects: [voice.py, tests/test_wayland_input.py, tests/test_hyprland_daemon.py]
actuals:
  tasks: 3
  tests: 112 passed
key-files:
  modified: [voice.py, tests/test_wayland_input.py, tests/test_hyprland_daemon.py]
key-decisions:
  - "Reduce MAX_RECORDING_SECONDS default from 300.0s to 180.0s (3 minutes)."
  - "Dynamically scale typing_timeout above 15.0s for text longer than 50 characters based on transcript character length and type delay."
  - "Safely release virtual keys via ydotool key 1:0...127:0 on typing exceptions/timeouts, preventing stuck keys in ydotoold / Hyprland."
  - "Do not retry with ydotool if wtype times out mid-typing to avoid duplicate typed text."
status: complete
---

# Quick Task 261018-omu Summary

Reduced max recording duration to 3 minutes (180s), diagnosed and fixed the stuck 'T' key on typing timeout, and added adaptive typing timeouts and emergency key release protection.

## Root Cause & Explanation: Stuck Keyboard Keys

When dictating for several minutes, Faster-Whisper produces long transcripts (often 2,000 to 3,000+ characters). Previously, `type_text()` passed a fixed `timeout=15.0` to `subprocess.run(["wtype", ...])` and `subprocess.run(["ydotool", "type", ...])`.

Because Wayland IPC keystroke injection requires round-trip processing per character (taking ~16 to 25 seconds for 2,500 characters):
1. At 15 seconds, Python raised `subprocess.TimeoutExpired` and sent `SIGKILL` to `wtype`.
2. `type_text()` then immediately caught this and ran `ydotool type` to re-type the whole text from character 0, which also hit the 15-second timeout and was killed with `SIGKILL`.
3. When `ydotool` was killed abruptly mid-stroke, it left `ydotoold` (the persistent background daemon) with whatever key was currently down (frequently keycode 20, `KEY_T`, in English sentences) held down in `/dev/uinput` (`ydotoold-virtual-device`).
4. Hyprland maintained this virtual keyboard state, making physical presses of the 'T' key non-functional.

## Accomplishments

1. **Reduced Recording Limit to 3 Minutes:**
   - Changed `MAX_RECORDING_SECONDS = 180.0` in `voice.py`.
   - Recording now automatically halts and initiates transcription upon reaching 3 minutes (180s).
   - Preserved environment variable override `VOICE_MAX_RECORDING_SECONDS`.

2. **Adaptive Typing Timeout:**
   - Added `typing_timeout(text, type_delay)` which retains a 15.0s baseline for short inputs (<= 50 chars) and dynamically scales up for long transcripts, ensuring multi-minute recordings with thousands of characters never get killed mid-typing.

3. **Virtual Key Release & Stuck Key Protection:**
   - Added `release_virtual_keys()` to send key-up (`:0`) events across keycodes 1-127 via `ydotool` on typing failure, timeout, or daemon kill (`voice --kill`).
   - Added `--reset-keys` command (`voice --reset-keys`) to allow instant recovery of any stuck virtual keys at any time.
   - Prevented runaway retries: if `wtype` times out mid-stream, it releases keys and aborts without attempting duplicate typing with `ydotool`.

## Verification

- Ran full unittest suite: all 112 tests passed (`tests/test_wayland_input.py`, `tests/test_hyprland_daemon.py`, `tests/test_tts_pipeline.py`, `tests/test_verification_doctor.py`).
- Verified `voice.py --reset-keys` runs and cleanly releases all virtual keys.
