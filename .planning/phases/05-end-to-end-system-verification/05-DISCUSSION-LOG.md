# Phase 5: End-to-End System Verification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-19
**Phase:** 5-End-to-End System Verification
**Areas discussed:** Target Applications & Window Matrix, Verification Strategy & Tooling, Troubleshooting & System Doctor, Documentation & Arch/Hyprland Guide

---

## Target Applications & Window Matrix

### Terminal Emulators
| Option | Description | Selected |
|--------|-------------|----------|
| Kitty and Foot as primary, Alacritty secondary | Kitty is default on dots-hyprland; Foot is native pure-Wayland | ✓ |
| Verify Kitty only | Standard terminal for current dots-hyprland setup | |
| Verify all three equally | Kitty, Foot, and Alacritty treated with equal weight | |
| You decide | Based on installed packages in current system | |

**User's choice:** Focus on Kitty and Foot as primary targets with Alacritty secondary.

### Code Editors / IDEs
| Option | Description | Selected |
|--------|-------------|----------|
| Both Terminal Editors and GUI Wayland/Electron IDEs | Neovim/Helix running in Kitty/Foot, plus VS Code / Cursor / Zed | ✓ |
| Verify GUI Wayland/Electron editors only | VS Code / Cursor only | |
| Verify Terminal editors only | Neovim / Helix inside Kitty only | |
| You decide | Test whatever editors are currently installed and runnable | |

**User's choice:** Verify both Terminal Editors (Neovim/Helix running in Kitty/Foot) and GUI Wayland/Electron IDEs (VS Code / Cursor / Zed).

### Browsers & Document Readers
| Option | Description | Selected |
|--------|-------------|----------|
| Firefox and Chromium-based browsers, plus PDF/document viewer | Firefox (native Wayland primary selection), Brave/Chrome, Zathura/Evince | ✓ |
| Verify Firefox and Chromium browsers only | Web browsers only | |
| Whichever default browser is installed | Single active browser | |
| You decide | Auto-detect active browser on system | |

**User's choice:** Verify both Firefox (native Wayland primary selection) and Chromium-based browsers (Brave/Chrome), plus PDF/document viewer (e.g. Zathura or Evince).

### Test Text Payloads
| Option | Description | Selected |
|--------|-------------|----------|
| Standardized diverse matrix | Plain conversational sentences, punctuation/casing, programming code snippets with symbols (`{}[]()$"'\`), and multi-line text | ✓ |
| Normal prose dictation only | Sentences, punctuation, capitalization with basic symbols | |
| Minimal payloads | Short sentences and phrases only | |
| You decide | Standard benchmark test corpus | |

**User's choice:** Test a standardized matrix: plain conversational sentences, punctuation/casing, programming code snippets with symbols (`{}[]()$"'\`), and multi-line text.

---

## Verification Strategy & Tooling

### Test Runner Structure
| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated interactive test runner script / command | Validates automated subsystem checks (PipeWire, wtype, hotkeys, synthetic audio) and guides user through real interactive window typing/speaking tests | ✓ |
| Purely automated headless test script | Synthetic audio and headless Wayland/wtype virtual checks | |
| Manual checklist document only | No dedicated verification code | |
| You decide | Best combination of automated checks and interactive verification | |

**User's choice:** Implement a dedicated interactive test runner script (`scripts/verify-e2e.sh` or `voice --verify`) that validates both automated subsystem checks (PipeWire, wtype, hotkeys, synthetic audio) and guides the user through real interactive window typing/speaking tests.

### Runner Access Point
| Option | Description | Selected |
|--------|-------------|----------|
| Built-in `voice --verify` CLI command backed by `scripts/verify-e2e.sh` | Clean module accessible easily from anywhere | ✓ |
| Standalone script in `scripts/verify-e2e.sh` only | Keep `voice.py` lean | |
| Purely inside `voice.py` under `--verify` with no extra script files | Single-file implementation | |
| You decide | Based on repo architecture conventions | |

**User's choice:** Expose `voice --verify` as a built-in CLI command backed by a clean module/script in `scripts/verify-e2e.sh`, accessible easily from anywhere.

### Audio & STT Verification Method
| Option | Description | Selected |
|--------|-------------|----------|
| Bundled/generated synthetic audio sample + live mic test | Test STT pipeline + wtype injection deterministically, followed by live mic push-to-talk test | ✓ |
| Live microphone push-to-talk only | No synthetic/reference audio file | |
| Synthetic/reference audio file only | No required live speech | |
| You decide | Whichever gives highest verification confidence | |

**User's choice:** Include a bundled/generated synthetic reference audio sample to test the STT pipeline + wtype injection deterministically, followed by a live mic push-to-talk test.

### Verification Reporting
| Option | Description | Selected |
|--------|-------------|----------|
| Rich terminal summary table + structured verification artifact | Pass/fail per subsystem in terminal and export `05-VERIFICATION.md` / `verification-results.json` | ✓ |
| Terminal output only | Pass/fail checkmarks without extra report files | |
| Markdown report file in `docs/verification-report.md` | Separate documentation report | |
| You decide | Standard GSD phase verification artifacts | |

**User's choice:** Print a rich terminal summary table (pass/fail per subsystem) and export a structured verification artifact (`05-VERIFICATION.md` / `verification-results.json`) for the phase record.

---

## Troubleshooting & System Doctor

### System Diagnostic Command
| Option | Description | Selected |
|--------|-------------|----------|
| First-class `voice --doctor` diagnostic command | Verifies binaries, audio devices, model weights, Hyprland bind status, and virtualenv health with actionable fix suggestions | ✓ |
| Rely on existing `--check` | Model loading only; troubleshooting in docs | |
| Separate shell script (`scripts/doctor.sh`) | External script | |
| You decide | Balance between CLI utility and codebase size | |

**User's choice:** Implement a first-class `voice --doctor` diagnostic command that verifies binaries, audio devices, model weights, Hyprland bind status, and virtualenv health with actionable fix suggestions.

### Remediation Output Formatting
| Option | Description | Selected |
|--------|-------------|----------|
| Exact Arch Linux package commands in remediation hints | `sudo pacman -S wtype ffmpeg`, `scripts/download-kokoro-assets.sh`, `voice --install-hotkey` | ✓ |
| Generic error descriptions | Without distro-specific package manager commands | |
| Auto-fix option (`voice --doctor --fix`) | Automatically download assets or repair configuration | |
| You decide | Clear, pragmatic guidance for Arch/Hyprland users | |

**User's choice:** Provide exact Arch Linux package commands (`sudo pacman -S wtype ...`, `scripts/download-kokoro-assets.sh`, `voice --install-hotkey`) directly in doctor remediation hints.

### Audio & PipeWire Diagnostics
| Option | Description | Selected |
|--------|-------------|----------|
| Check mic default source, volume/mute state (`wpctl`), active service, PortAudio devices | Document common PipeWire fixes | ✓ |
| Check PortAudio device listing only | Leave system audio controls to external tools | |
| Software dependencies only | Assume PipeWire is preconfigured properly | |
| You decide | Essential audio checks without over-complicating PipeWire internals | |

**User's choice:** Check microphone default input source, volume/mute state (`wpctl`), active PipeWire service, and PortAudio device listing in doctor probe and document common PipeWire fixes.

### Daemon Status & Recovery
| Option | Description | Selected |
|--------|-------------|----------|
| Check PID file health, detect orphaned daemons, suggest recovery | Suggest `voice --log` / `voice --kill` for quick recovery | ✓ |
| Print log file locations only | Manual inspection | |
| Keep daemon status checks limited to existing `--status` | No changes to doctor | |
| You decide | Clean integration with existing `--status` and `--log` CLI options | |

**User's choice:** Doctor checks active PID file health (`recorder.pid`, `tts.pid`), validates if daemon is alive or orphaned, and suggests `voice --log` / `voice --kill` for quick recovery.

---

## Documentation & Arch/Hyprland Guide

### Documentation Architecture
| Option | Description | Selected |
|--------|-------------|----------|
| Update `README.md` as first-class Arch/Hyprland + `docs/ARCH_HYPRLAND.md` deep dive | Full coverage of dots-hyprland integration, PipeWire audio tuning, and troubleshooting | ✓ |
| Update `README.md` only | All Arch + Hyprland instructions in one place | |
| Minimal `README.md` + all details in `docs/ARCH_HYPRLAND.md` | Separate manual | |
| You decide | Maintain clean docs following repo conventions | |

**User's choice:** Update `README.md` with Arch Linux + Hyprland as the first-class setup and add a comprehensive `docs/ARCH_HYPRLAND.md` guide covering dots-hyprland integration, PipeWire audio tuning, and troubleshooting.

### Package & Dependency Documentation
| Option | Description | Selected |
|--------|-------------|----------|
| Frame dots-hyprland defaults first + `pacman -S wtype ffmpeg` | Explain `wl-clipboard`, `libnotify`, `pipewire` are preinstalled by dots-hyprland, provide full fallback for vanilla Arch | ✓ |
| Pure Arch Linux package commands only | Without specific dots-hyprland callouts | |
| Multi-distro side-by-side tabs | Arch, Fedora, and Debian/Ubuntu | |
| You decide | Optimize for dots-hyprland / Arch users while keeping instructions clear | |

**User's choice:** Frame dots-hyprland defaults first (explain that `wl-clipboard`, `libnotify`, and PipeWire are typically preinstalled by dots-hyprland), highlight `wtype` + `ffmpeg` installation via `pacman`, and provide a complete fallback `pacman` command for vanilla Arch.

### Keybinding Setup Guide
| Option | Description | Selected |
|--------|-------------|----------|
| Document `voice --install-hotkey` + Stow symlink preservation + manual config | Comprehensive installer and manual options | ✓ |
| Document automatic `voice --install-hotkey` command only | Automation only | |
| Manual copy-paste snippets only | Manual config only | |
| You decide | Provide both automated and manual instructions | |

**User's choice:** Document the one-command installer (`voice --install-hotkey`) with an explanation of how it safely updates `custom/keybinds.lua` preserving Stow symlinks, alongside manual config instructions for non-stow users.

### Operational Cheatsheet Reference
| Option | Description | Selected |
|--------|-------------|----------|
| "At a Glance" cheat-sheet table in README.md | Shortcuts, Chime Meanings, Status/Recovery Commands + workflow examples | ✓ |
| Workflow narrative paragraphs only | No dedicated table | |
| Separate reference file in `docs/CHEATSHEET.md` | Standalone file | |
| You decide | Clean formatting in README.md | |

**User's choice:** Include a concise "At a Glance" cheat-sheet table in README.md (Shortcuts, Chime Meanings, Status/Recovery Commands) followed by step-by-step workflow examples.

---

## Claude's Discretion

- Selection of exact synthetic audio test phrases ("The quick brown fox jumps over the lazy dog").
- Layout, styling, and status indicators in terminal tables and doctor output.
- Dynamic detection logic using `hyprctl activewindow -j` during interactive window verification.

## Deferred Ideas

None — discussion stayed strictly within Phase 5 scope.
