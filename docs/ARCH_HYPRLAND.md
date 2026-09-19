# Arch Linux & Hyprland Operational Guide

A comprehensive architectural and operational guide for running **voicemode** on Arch Linux with the Hyprland Wayland compositor.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [dots-hyprland Integration (`custom/keybinds.lua`)](#dots-hyprland-integration-customkeybindslua)
3. [GNU Stow Symlink Preservation](#gnu-stow-symlink-preservation)
4. [Audio Routing & WirePlumber Tuning (`wpctl`)](#audio-routing--wireplumber-tuning-wpctl)
5. [Offline Model Asset Pipeline (Whisper & Kokoro)](#offline-model-asset-pipeline-whisper--kokoro)
6. [Troubleshooting & Diagnostic Playbook](#troubleshooting--diagnostic-playbook)

---

## Architecture Overview

voicemode is engineered as a lightweight, unprivileged desktop daemon and CLI utility optimized for modern Linux Wayland desktop environments. On Arch Linux running Hyprland, it eliminates heavy background daemons and root permissions by interfacing directly with native Wayland protocols and system utilities:

```
[ Hyprland Keybind ]
       |
       v
  SUPER + SHIFT + M  ──> voice --toggle ────────> Faster-Whisper (int8 CPU) ──> wtype (Wayland virtual keyboard)
  SUPER + T          ──> voice --speak-selection ─> Kokoro ONNX TTS ───────────> ffplay (PipeWire audio sink)
```

### Key Subsystem Principles

- **Rootless Keystroke Injection:** Injects text via `wtype` over the Wayland `zwp_virtual_keyboard_v1` protocol. Unlike tools that require `/dev/uinput` root daemon privileges (like `ydotool`), `wtype` runs entirely unprivileged in the user session.
- **Dynamic Focus & Selection:** Primary text selection capture (`SUPER + T`) uses `wl-paste --primary` to immediately access mouse-highlighted text in pure Wayland browsers (Firefox), document viewers (Zathura), and terminals (Kitty, Foot) without requiring clipboard modification.
- **Local AI Inference:** STT transcription is powered locally by Faster-Whisper using CTranslate2 int8 quantization on CPU (~1.8-2.2s for dictations). Speech synthesis uses Kokoro-v1.0 via ONNX Runtime (~1.2-1.7s per paragraph) with zero network transmissions.
- **Detached Worker Lifecycle:** Background processes detach via `subprocess.Popen(start_new_session=True)` and coordinate using POSIX signals (`SIGUSR1` for stop & transcribe; `SIGTERM` for immediate abort) and atomic PID files in `$XDG_RUNTIME_DIR/voice-stt/`.

---

## dots-hyprland Integration (`custom/keybinds.lua`)

In modern Hyprland setups based on `dots-hyprland`, keybindings are defined in Lua using `hyprland-qtutils` or `hyprctl`. The canonical integration target is:

```text
~/.config/hypr/custom/keybinds.lua
```

### Generated Keybinding Block

When installed via `voice --install-hotkey` (or manual configuration), voicemode appends an isolated block delimited by comments:

```lua
-- voicemode start
hl.unbind("SUPER + T")
hl.bind("SUPER + SHIFT + M", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --toggle"), { description = "Voice STT: Push-to-talk toggle" })
hl.bind("SUPER + T", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --speak-selection"), { description = "Voice TTS: Speak selection" })
-- voicemode end
```

### Why These Key Chords?

1. **`SUPER + SHIFT + M` (STT Toggle):**
   - Preserves `SUPER + Return` and `CTRL + ALT + T` for terminal spawning.
   - Avoids collision with `SUPER + M` (`wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle` for physical microphone mute).
   - Unbinds upstream conflicting `SUPER + SHIFT + M` to prevent duplicate actuation.
2. **`SUPER + T` (TTS Speak Selection & Stop):**
   - Dots-hyprland binds `SUPER + T` by default to an upstream action. The installer explicitly inserts `hl.unbind("SUPER + T")` first.
   - When speech is idle, `SUPER + T` reads the active selection.
   - When speech is currently playing, `SUPER + T` acts as an interrupt, terminating `ffplay` immediately.
3. **Unlocked-Only Execution:**
   - Both bindings omit `locked = true` and do not use `bindl`. Dictation and selection reading are explicitly inhibited on the lock screen (`hyprlock`) to prevent accidental unauthorized text leakage.

---

## GNU Stow Symlink Preservation

A critical feature of voicemode's configuration management is **symlink preservation**.

In many developer setups, `~/.config/hypr/custom/keybinds.lua` is not a regular file, but a symbolic link created by GNU Stow pointing into a version-controlled dotfiles repository (e.g. `~/.dotfiles/stow/hypr/.config/hypr/custom/keybinds.lua`).

### The Safe-Update Contract

A naive file write (e.g. `open("...", "w")` or atomic write via temporary file replacement `os.replace`) unlinks the symlink, writing the new file to `~/.config/` while leaving the git repository disconnected.

Voicemode enforces safe in-place updates:
1. It calls `Path(config_path).resolve()` to locate the real canonical file inside the dotfiles repository.
2. It inspects `Path.is_symlink()` and logs the target destination.
3. It rewrites only the content inside the `-- voicemode start` and `-- voicemode end` block in the canonical destination file, preserving all surrounding user keybinds.
4. The symlink structure remains completely intact, ensuring your dotfiles git repository tracks the change.

---

## Audio Routing & WirePlumber Tuning (`wpctl`)

Voicemode interacts directly with PipeWire through WirePlumber.

### Audio Stream Identification

When voicemode records audio or plays cues, it labels its streams via environment variables set in `voice.py`:
```bash
PULSE_PROP_application.name="voicemode"
PIPEWIRE_PROPS='{ application.name = voicemode }'
```
This ensures voicemode appears as an independent application in `pavucontrol`, `helvum`, or `qpwgraph`, allowing per-app volume and device routing.

### Useful `wpctl` Commands

- **Check microphone status and volume:**
  ```bash
  wpctl get-volume @DEFAULT_AUDIO_SOURCE@
  ```
  *(Example output: `Volume: 0.85` or `Volume: 1.00 [MUTED]`)*

- **Unmute the default microphone:**
  ```bash
  wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0
  ```
  *(Or press `SUPER + M` if using dots-hyprland defaults)*

- **List all audio devices and endpoints:**
  ```bash
  wpctl status
  ```

- **Set a specific input device as default:**
  ```bash
  wpctl set-default <device-id>
  ```

---

## Offline Model Asset Pipeline (Whisper & Kokoro)

All AI inference in voicemode runs 100% locally on your machine without external cloud dependencies.

### Faster-Whisper (STT)

- **Model:** `Systran/faster-whisper-small.en` (default)
- **Engine:** CTranslate2 using `int8` quantization on CPU.
- **Cache Location:** `~/.cache/huggingface/hub/models--Systran--faster-whisper-small.en`
- **Initial Download:**
  ```bash
  voice --check --allow-download
  ```

### Kokoro ONNX (TTS)

- **Model Weights:** `kokoro-v1.0.onnx` (~311 MB)
- **Voice Vectors:** `voices-v1.0.bin` (~27 MB)
- **Directory:** `models/kokoro/` within the repository or system directory.
- **Asset Downloader:**
  ```bash
  scripts/download-kokoro-assets.sh
  ```
- **Voices Available:**
  - `af_heart` (American English female, warm default)
  - `bm_george` (British English male)
  - Full catalog viewable via `voice --list-tts-voices`

---

## Troubleshooting & Diagnostic Playbook

### 1. Pre-Flight Check with `voice --doctor`

Whenever something isn't behaving as expected, run:
```bash
voice --doctor
```
This inspects:
- **Binaries:** `wtype`, `wl-copy`, `wl-paste`, `ffplay`, `wpctl`, `hyprctl`.
- **Audio:** WirePlumber default input source volume and mute status.
- **Models:** Whisper HuggingFace cache and Kokoro ONNX assets.
- **Keybindings:** `custom/keybinds.lua` block and Stow symlink health.
- **PID Health:** Identifies stale or orphaned recorder/player daemon locks.

### 2. Daemon Recovery with `voice --kill`

If a recording process was interrupted or an unexpected crash left a stale lock file (`recorder.pid` or `tts.pid`):
```bash
voice --kill
```
This safely signals any active worker processes with `SIGTERM` and purges stale PID lock files in `$XDG_RUNTIME_DIR/voice-stt/`, resetting system state to idle.

### 3. Verification Suite with `voice --verify`

To run automated and interactive validation of all subsystems:
```bash
voice --verify
# Or run specific tiers:
voice --verify --tier 1   # Static pre-flight diagnostics
voice --verify --tier 2   # Automated synthetic loopback self-test (~3-4s)
voice --verify --tier 3   # Interactive desktop application testing
```

### 4. Text Typing Settling Delay (`--pre-type-delay`)

If text fails to type into certain Electron or XWayland applications (like VS Code or Discord) because modifier keys (`SUPER`, `SHIFT`) take a fraction of a second to release:
```bash
# Increase focus settling delay to 100ms:
voice --pre-type-delay 100 --toggle
```
You can export this globally in your shell profile:
```bash
export VOICE_PRE_TYPE_DELAY=75
```
