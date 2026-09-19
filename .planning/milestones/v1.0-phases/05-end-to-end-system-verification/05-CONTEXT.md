# Phase 5: End-to-End System Verification - Context

**Gathered:** 2026-09-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 delivers comprehensive desktop-global end-to-end validation of voicemode under Hyprland on Arch Linux. It verifies push-to-talk speech-to-text dictation across terminals (Kitty, Foot) and text/code editors (Neovim, VS Code), text-to-speech reading and stop-playback of highlighted screen text across browsers (Firefox, Chromium) and document viewers, implements a static system diagnostic probe (`voice --doctor`), builds an interactive/automated verification test suite (`voice --verify`), and produces complete, polished Arch Linux + Hyprland documentation (`README.md`, `docs/ARCH_HYPRLAND.md`, `docs/DEPENDENCIES.md`).

</domain>

<decisions>
## Implementation Decisions

### Target Applications & Window Matrix
- **D-01:** Focus on **Kitty** and **Foot** as primary terminal targets (Kitty is default on dots-hyprland; Foot is native pure-Wayland) with Alacritty secondary.
- **D-02:** Verify both **Terminal Editors** (Neovim / Helix running inside Kitty/Foot) and **GUI Wayland/Electron IDEs** (VS Code / Cursor / Zed).
- **D-03:** Verify **Firefox** (native Wayland primary selection) and **Chromium-based browsers** (Brave/Chrome), plus document readers (Zathura / Evince) for `SUPER + T` selection capture (`wl-paste --primary`).
- **D-04:** Test a standardized payload matrix: conversational prose, punctuation & capitalization, programming code snippets with special symbols (`{}[]()$"'\`), and multi-line text with newlines.

### Verification Strategy & Tooling Architecture
- **D-05:** Implement a 3-tier verification architecture:
  - **Tier 1 (Static Pre-Flight Diagnostics):** Instant, non-destructive check of binaries, permissions, audio devices, and models via `voice --doctor`.
  - **Tier 2 (Automated Pipeline Self-Test):** Zero human effort test running in 3-5 seconds (audio cue tone synthesis, synthetic audio transcription, Kokoro TTS synthesis, Wayland primary selection round-trip).
  - **Tier 3 (Interactive Application Matrix):** Live desktop testing across user-focused windows with dynamic compositor inspection.
- **D-06:** Expose `voice --verify` as a built-in CLI command backed by `scripts/verify-e2e.sh`, accessible easily from anywhere in the user's PATH via `~/.local/bin/voice`.
- **D-07:** **Dynamic Window Inspection via `hyprctl activewindow -j`:** Instead of hardcoding application locks, the interactive verifier prompts the user to focus their target window, dynamically detects the active window class (e.g. `kitty`, `code-url-handler`, `firefox`), and injects test text using `wtype`.
- **D-08:** Print a rich terminal summary table (pass/fail per subsystem) and export a structured verification artifact (`05-VERIFICATION.md` / `verification-results.json`) for the phase record.

### Troubleshooting & System Diagnostics (`voice --doctor`)
- **D-09:** Implement a first-class `voice --doctor` diagnostic command that verifies binaries (`wtype`, `wl-copy`, `wl-paste`, `ffplay`), audio devices (PipeWire / WirePlumber input source and mute state via `wpctl`, PortAudio listing), model weights (Whisper cache, Kokoro weights in `models/kokoro/`), Hyprland keybind status in `custom/keybinds.lua`, and active daemon PID health.
- **D-10:** Provide exact Arch Linux package commands (`sudo pacman -S wtype ffmpeg`, `scripts/download-kokoro-assets.sh`, `voice --install-hotkey`) directly in doctor remediation hints.
- **D-11:** Doctor checks active PID file health (`recorder.pid`, `tts.pid`), identifies orphaned or stale daemon processes, and suggests recovery commands (`voice --log`, `voice --kill`).

### Documentation & Arch/Hyprland Guide
- **D-12:** Update `README.md` to establish Arch Linux + Hyprland as the first-class setup, featuring an "At a Glance" cheat-sheet table (Shortcuts, Chime Meanings, Status/Recovery Commands) and step-by-step workflow examples.
- **D-13:** Create a comprehensive `docs/ARCH_HYPRLAND.md` guide detailing dots-hyprland integration, Lua keybindings in `custom/keybinds.lua` with GNU Stow preservation, PipeWire / WirePlumber audio tuning (`wpctl`), Kokoro offline TTS model pipeline, and troubleshooting.
- **D-14:** In `docs/DEPENDENCIES.md` and `README.md`, frame `dots-hyprland` defaults first (clarify that `wl-clipboard`, `libnotify`, and `PipeWire` are typically preinstalled by dots-hyprland), highlight `wtype` and `ffmpeg` as the two essential `pacman -S` packages, and provide a complete fallback `pacman` command for vanilla Arch.
- **D-15:** Document the one-command installer (`voice --install-hotkey`) explaining safe in-place updates of `custom/keybinds.lua` preserving Stow symlinks, alongside manual configuration snippets.

### Claude's Discretion
- Selection of synthetic test phrases ("The quick brown fox jumps over the lazy dog", symbol test strings).
- Layout and visual styling of terminal pass/fail tables and doctor checkmark icons.
- Calibration of countdown delays (e.g. 3-5 seconds) for interactive window focus transitions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core Implementation & Daemon Architecture
- `voice.py` — Complete application containing CLI dispatch, audio recording, Whisper STT, Kokoro TTS, Wayland injection, and daemon management.
- `/home/pera/.local/bin/voice` — System launcher wrapper pointing to the Python 3.12 virtualenv.

### Hyprland Configuration & Compositor Tooling
- `/home/pera/.config/hypr/custom/keybinds.lua` (resolves to `/home/pera/github_repo/.dotfiles/stow/hypr/.config/hypr/custom/keybinds.lua`) — User keybinding definitions.
- `hyprctl` — Compositor query tool (`hyprctl activewindow -j`, `hyprctl reload`).

### Prior Phase Context
- `.planning/phases/01-environment-audio-subsystem/01-CONTEXT.md` — Audio subsystem, virtualenv setup, PipeWire conventions, and sine tone synthesis.
- `.planning/phases/02-wayland-keystroke-injection/02-CONTEXT.md` — `wtype` typing backend, settling delays, dual clipboard mirroring.
- `.planning/phases/03-text-to-speech-model-asset-pipeline/03-CONTEXT.md` — Kokoro ONNX offline TTS, primary selection capture, TTS background player lifecycle.
- `.planning/phases/04-hyprland-integration-daemon-lifecycle/04-CONTEXT.md` — Hyprland native Lua keybinds, Stow symlink preservation, multi-token PID state tracking, and focus-safe notifications.

### Documentation Targets
- `README.md` — Root user guide and quickstart.
- `docs/DEPENDENCIES.md` — System package requirements and distro mapping.
- `docs/ARCH_HYPRLAND.md` — Dedicated Arch Linux + Hyprland operational guide.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `check_environment()` / `args.check` (`voice.py:1664`, `voice.py:1933`): Baseline check logic to be expanded into `voice --doctor`.
- `insert_text()`, `type_text()` (`voice.py:440-485`): Wayland input injection via `wtype`.
- `selected_or_clipboard_text()` (`voice.py:734-777`): Primary selection read via `wl-paste --primary`.
- `play_cue()`, `play_tone()` (`voice.py:487-547`): Audio cue synthesizer.
- `read_pid()`, `process_alive()`, `kill_background()` (`voice.py:567-630`): Process state and PID helpers.

### Established Patterns
- **Detached Worker Pattern:** Background workers run detached with PID files in `$XDG_RUNTIME_DIR/voice-stt/`.
- **Dynamic Compositor Interrogation:** Querying `hyprctl` for active windows, reload triggers, and signatures.
- **Symlink-Safe File Writes:** Resolving `Path.resolve()` to avoid overwriting GNU Stow dotfile symlinks.

### Integration Points
- `voice --doctor`: New top-level CLI flag and diagnostic engine in `voice.py`.
- `voice --verify`: New top-level CLI flag running 3-tier verification suite.
- `scripts/verify-e2e.sh`: Convenience wrapper calling `voice --verify`.

</code_context>

<specifics>
## Specific Ideas

- **3-Tier Verification:** Static Pre-Flight (`--doctor`), Automated Pipeline Self-Test (synthetic wav, cues, selection round-trip), Interactive Application Matrix (`hyprctl activewindow` target testing).
- **At-a-Glance Cheatsheet:** Clean Markdown table in `README.md` with shortcuts (`SUPER + SHIFT + M`, `SUPER + T`), audio chime frequencies/rhythms, and CLI recovery commands.
- **Arch-First Dependency Hierarchy:** Highlight `dots-hyprland` pre-packaged tools vs `pacman -S wtype ffmpeg` prerequisites.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed strictly within Phase 5 scope.

</deferred>

---

*Phase: 05-End-to-End System Verification*
*Context gathered: 2026-09-19*
