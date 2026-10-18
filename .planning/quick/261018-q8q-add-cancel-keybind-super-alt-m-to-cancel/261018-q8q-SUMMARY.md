---
phase: quick-task
plan: 261018-q8q
subsystem: hyprland-keybinds
tags: [hyprland, keybinds, stt, cancel]
requires: []
provides:
  - CLI flag `--cancel` to terminate active STT recording without transcribing or typing
  - Replaced mute shortcut `SUPER + ALT + M` with `voice --cancel` in Hyprland Lua config
  - Updated `install_hyprland_keybinds()` to unbind upstream `SUPER + ALT + M` and bind cancel action
  - Verified live reloading via `hyprctl reload`
affects: [voice.py, tests/test_hyprland_daemon.py, ~/.config/hypr/custom/keybinds.lua]
actuals:
  tasks: 4
  tests: 119 passed
key-files:
  modified: [voice.py, tests/test_hyprland_daemon.py, ~/.config/hypr/custom/keybinds.lua]
key-decisions:
  - "Add --cancel flag calling cancel_recording() to send SIGTERM to active STT PID, play cue, and notify."
  - "Add hl.unbind('SUPER + ALT + M') and hl.bind('SUPER + ALT + M', ...) in generate_hyprland_block() to replace default audio mute with voicemode cancel."
status: complete
---

# Quick Task 261018-q8q Summary

Added `--cancel` command and bound `SUPER + ALT + M` in Hyprland to cancel active speech-to-text recording mid-dictation without transcribing or typing.

## Accomplishments

1. **`--cancel` Command Implementation (`voice.py`):**
   - Added `--cancel` CLI argument.
   - Added `cancel_recording(args)` which detects any active recording process from `PID_FILE`, issues `SIGTERM` to cleanly terminate recording, removes PID locks, plays stop chime, shows notification toast ("Recording cancelled."), and outputs feedback.
   - If no recording is in progress, cleanly reports status without errors.

2. **Hyprland `Super + Alt + M` Keybinding Integration (`voice.py`, `~/.config/hypr/custom/keybinds.lua`):**
   - Updated `generate_hyprland_block()` to unbind `SUPER + ALT + M` and bind it to `~/.local/bin/voice --cancel` (replacing the default sink mute).
   - Applied updated keybinding block directly to `/home/pera/.config/hypr/custom/keybinds.lua` (via GNU Stow symlink target).
   - Reloaded active Hyprland configuration with `hyprctl reload`.

3. **Verification:**
   - Added unit tests in `tests/test_hyprland_daemon.py` verifying `--cancel` dispatch, active process signaling, idle process safety, and Hyprland Lua block formatting.
   - All 119 unit tests pass.
