---
phase: 04-hyprland-integration-daemon-lifecycle
plan: "01"
subsystem: desktop-integration
tags: [hyprland, wayland, keybinds, lua, dots-hyprland, stow, symlink-preservation, hyprctl]

requires:
  - phase: 02-wayland-keystroke-injection
    plan: "01"
    provides: Wayland rootless typing backend and input injection
  - phase: 03-text-to-speech-model-asset-pipeline
    plan: "02"
    provides: Wayland primary selection TTS capture and playback
provides:
  - Idempotent Hyprland Lua keybinding generator (`generate_hyprland_block()`)
  - CLI commands `--print-hyprland` and `--install-hyprland`
  - Desktop auto-detection dispatcher for `--install-hotkey` / `--install-hotkeys` detecting Hyprland vs GNOME
  - Dotfiles GNU Stow symlink preservation using `raw_path.resolve()` modifying target in-place
  - Upstream terminal shortcut unbinding (`hl.unbind("SUPER + T")`) before TTS assignment
  - STT push-to-talk toggle assigned to `SUPER + SHIFT + M` (`voice --toggle`)
  - TTS speak-selection assigned to `SUPER + T` (`voice --speak-selection`)
  - Unlocked-only binding execution (`locked = false` / standard `hl.bind`) mitigating lockscreen activation
  - Live Hyprland session dynamic reloading via `hyprctl reload`
  - Comprehensive unit test suite in `tests/test_hyprland_daemon.py`
affects: [04-02-PLAN.md]

actuals:
  tasks: 3
  commits: 1

tech-stack:
  added: [hyprctl, dots-hyprland]
  patterns: [delimited-block-replacement, symlink-preserving-in-place-write, desktop-session-detection]

key-files:
  created: [tests/test_hyprland_daemon.py]
  modified: [voice.py]

key-decisions:
  - "Configured SUPER + SHIFT + M for STT toggle and SUPER + T for TTS speak-selection (per D-01, D-02)"
  - "Generated hl.unbind('SUPER + T') to cleanly release upstream dots-hyprland terminal binding (per D-02)"
  - "Preserved primary terminal access on existing chords SUPER + Return and CTRL + ALT + T without secondary rebinds (per D-03)"
  - "Enforced standard hl.bind without locked = true or bindl to prevent lockscreen keystroke execution (per D-04, T-04-01 mitigation)"
  - "Implemented desktop auto-detection in install_hotkeys_dispatch checking HYPRLAND_INSTANCE_SIGNATURE, XDG_CURRENT_DESKTOP, and hyprctl (per D-05)"
  - "Used delimited comment markers (-- voicemode start ... -- voicemode end) for idempotent replacement (per D-06)"
  - "Preserved GNU Stow symlinks by resolving real target path via raw_path.resolve() and updating in-place (per D-07, T-04-03 mitigation)"
  - "Targeted ~/.config/hypr/custom/keybinds.lua per dots-hyprland custom architecture (per D-08)"
  - "Dispatched hyprctl reload after keybinding installation for immediate hot-reload (per D-09)"
  - "Used HOME .. '/.local/bin/voice' full path in hl.dsp.exec_cmd to ensure binary discovery in non-interactive sessions (per D-10)"

patterns-established:
  - "generate_hyprland_block: delimited Lua configuration block generation"
  - "install_hyprland_keybinds: symlink-preserving idempotent configuration file updater with dynamic compositor reload"
  - "install_hotkeys_dispatch: transparent desktop environment auto-detection"

requirements-completed: [HYPR-01]

coverage:
  - id: D-01
    description: "Assign SUPER + SHIFT + M for STT push-to-talk toggle"
    requirement: "HYPR-01"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestHyprlandKeybindInstallation.test_generate_hyprland_block_format"
        status: pass
    human_judgment: false
  - id: D-02
    description: "Unbind upstream SUPER + T and assign to TTS speak-selection"
    requirement: "HYPR-01"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestHyprlandKeybindInstallation.test_generate_hyprland_block_format"
        status: pass
    human_judgment: false
  - id: D-04
    description: "Enforce unlocked-only execution (locked = false) to mitigate lockscreen keystroke injection"
    requirement: "HYPR-01"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestHyprlandKeybindInstallation.test_unlocked_only_execution"
        status: pass
    human_judgment: false
  - id: D-05
    description: "Desktop environment auto-detection for --install-hotkey and dedicated --print-hyprland / --install-hyprland"
    requirement: "HYPR-01"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestHyprlandKeybindInstallation.test_print_hyprland_stdout"
        status: pass
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestHyprlandKeybindInstallation.test_install_hotkey_auto_detection"
        status: pass
    human_judgment: false
  - id: D-06
    description: "Delimited comment block (-- voicemode start ... -- voicemode end) for idempotent replacement"
    requirement: "HYPR-01"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestHyprlandKeybindInstallation.test_install_hyprland_creates_block"
        status: pass
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestHyprlandKeybindInstallation.test_install_hyprland_idempotent_replace"
        status: pass
    human_judgment: false
  - id: D-07
    description: "Preserve GNU Stow dotfiles symlinks using raw_path.resolve() in-place modification"
    requirement: "HYPR-01"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestHyprlandKeybindInstallation.test_install_hyprland_preserves_symlink"
        status: pass
    human_judgment: false
  - id: D-09
    description: "Dynamically reload Hyprland via hyprctl reload after installation"
    requirement: "HYPR-01"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestHyprlandKeybindInstallation.test_install_hyprland_reloads_hyprctl"
        status: pass
    human_judgment: false
---

## Self-Check: PASSED
- `tests/test_hyprland_daemon.py` exists on disk and executes cleanly.
- `git log` returns commit `2999563` for `04-01`.
- Live symlink `/home/pera/.config/hypr/custom/keybinds.lua` verified intact pointing to GNU Stow dotfiles.
- Live `hyprctl reload` verified returning `ok`.
- Full test suite `python -m unittest discover tests` passing (60 tests).
