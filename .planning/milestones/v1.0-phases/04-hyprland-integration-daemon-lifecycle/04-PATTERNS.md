# Phase 4: Hyprland Integration & Daemon Lifecycle - Pattern Mapping

**Target Directory:** `/home/pera/github_repo/Voice/.planning/phases/04-hyprland-integration-daemon-lifecycle`  
**Generated:** 2026-09-19  
**Phase Requirements:** `HYPR-01`, `HYPR-02`  
**Target Output File:** `04-PATTERNS.md`

---

## 1. Executive Summary & File Classification

Phase 4 integrates `voicemode` with the user's native Hyprland desktop environment (`dots-hyprland`) and hardens the background daemon process lifecycle against concurrency races, PID recycling, and focus-stealing desktop notifications.

### Target Files to Create / Modify

| File Path | Action | Role | Data Flow Summary |
|---|---|---|---|
| [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) | **Modify** | Core CLI, Keybind Installer & Daemon Manager | Handles `--print-hyprland`, `--install-hyprland`, and `--install-hotkey` desktop auto-detection; generates idempotent Lua config blocks; updates `custom/keybinds.lua` preserving symlinks; manages daemon state transitions (`starting` -> `recording` -> `transcribing` -> `idle`) in `recorder.pid`; handles `SIGUSR1` (graceful stop & type) vs `SIGTERM`/`SIGINT` (immediate abort & cleanup); coordinates symmetric STT/TTS mutex; enforces focus-safe notifications and periodic cue ticks. |
| [`tests/test_hyprland_daemon.py`](file:///home/pera/github_repo/Voice/tests/test_hyprland_daemon.py) | **Create** | Unit Test Harness | Validates Hyprland Lua block generation, upstream unbinding, symlink preservation, `hyprctl reload`, desktop auto-detection, PID lifecycle transitions, 300ms double-tap race mitigation, busy state protection, hardened `/proc/<pid>/cmdline` checking, symmetric STT/TTS mutex, safety watchdogs, and focus-safe notification suppression. |
| [`~/.config/hypr/custom/keybinds.lua`](file:///home/pera/.config/hypr/custom/keybinds.lua) *(resolves to `~/.dotfiles/stow/hypr/.config/hypr/custom/keybinds.lua`)* | **Modify** *(via installer)* | Declarative User Keybinds Config | User dotfiles Lua script loaded by Hyprland. Receives delimited `-- voicemode start` / `-- voicemode end` block unbinding `SUPER + T` and binding `SUPER + SHIFT + M` (`voice --toggle`) and `SUPER + T` (`voice --speak-selection`). |

---

## 2. Pattern Assignments & Codebase Analogs

Each target file and capability maps directly to existing codebase patterns:

```
┌───────────────────────────────────────────────┐
│              EXISTING ANALOG                  │
├───────────────────────────────────────────────┤
│ voice.py:install_gnome_hotkey (1377-1405)    │ ──► Pattern 1: Desktop Config & Keybind Installation
│ voice.py:read_pid / write_pid (567-598)       │ ──► Pattern 2: Atomic PID & Lifecycle State Management
│ voice.py:process_alive (575-583)              │ ──► Pattern 3: Hardened Process Aliveness & Identity Check
│ voice.py:toggle_background_recording (1251)   │ ──► Pattern 4: Double-Tap Race Mitigation & Busy Cue Guard
│ voice.py:run_background_recording (1277-1358) │ ──► Pattern 5: Signal Differentiation & Worker Lifecycle
│ voice.py:stop_tts / speak_selection (932,1034)│ ──► Pattern 6: Symmetric STT/TTS Mutual Exclusion
│ voice.py:notify (558-565)                     │ ──► Pattern 7: Focus-Safe Desktop Notifications
│ tests/test_wayland_input.py & test_tts_...py  │ ──► Pattern 8: Test Harness & Subprocess Mocking Patterns
└───────────────────────────────────────────────┘
```

---

### Pattern 1: Desktop Configuration & Idempotent Keybind Installation

#### Target File:
- [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) (Add `generate_hyprland_block`, `install_hyprland_keybinds`, update `install_gnome_hotkey` / `parse_args` dispatch)

#### Closest Existing Analog:
- [`voice.py:1377-1405`](file:///home/pera/github_repo/Voice/voice.py#L1377-L1405) (`install_gnome_hotkey`)

#### Existing Code Excerpt:
```python
def install_gnome_hotkey() -> int:
    voice_cmd = str(Path.home() / ".local" / "bin" / "voice")
    stt_command = voice_cmd + " --toggle"
    tts_command = voice_cmd + " --speak-selection"
    media_schema = "org.gnome.settings-daemon.plugins.media-keys"

    result = subprocess.run(
        ["gsettings", "get", media_schema, "custom-keybindings"],
        capture_output=True,
        text=True,
        check=True,
    )
    bindings = parse_gsettings_list(result.stdout)
    changed = False
    for path in (GNOME_BINDING_PATH, GNOME_TTS_BINDING_PATH):
        if path not in bindings:
            bindings.append(path)
            changed = True
    if changed:
        subprocess.run(
            ["gsettings", "set", media_schema, "custom-keybindings", repr(bindings)],
            check=True,
        )

    set_gnome_custom_binding(GNOME_BINDING_SCHEMA, APP_NAME, stt_command, "<Super>b")
    set_gnome_custom_binding(GNOME_TTS_BINDING_SCHEMA, "Voice TTS", tts_command, "<Super>t")
    print(f"Installed GNOME shortcut Super+B -> {stt_command}")
    print(f"Installed GNOME shortcut Super+T -> {tts_command}")
    return 0
```

#### Adaptation Pattern to Implement:
1. **Delimited Idempotent Block Generator:**
   Generate the verbatim Lua block adhering to D-01, D-02, D-04, D-06, D-10:
   ```python
   HYPRLAND_CUSTOM_KEYBINDS_PATH = Path.home() / ".config" / "hypr" / "custom" / "keybinds.lua"

   def generate_hyprland_block() -> str:
       voice_bin = Path.home() / ".local" / "bin" / "voice"
       # Enforce unlocked-only execution (locked = false / standard bind) per D-04
       return (
           "-- voicemode start\n"
           'hl.unbind("SUPER + T")\n'
           f'hl.bind("SUPER + SHIFT + M", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --toggle"), {{ description = "Voice STT: Push-to-talk toggle" }})\n'
           f'hl.bind("SUPER + T", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --speak-selection"), {{ description = "Voice TTS: Speak selection" }})\n'
           "-- voicemode end\n"
       )
   ```
2. **Symlink-Preserving Update (D-07):**
   Resolve real path (`target.resolve()`) before writing so stow symlinks (`~/.config/hypr/custom/keybinds.lua -> ~/.dotfiles/...`) are never severed. Use regex replacement `r"-- voicemode start\n.*?-- voicemode end\n"` or append:
   ```python
   def install_hyprland_keybinds(config_path: Optional[Path] = None) -> int:
       raw_path = config_path or HYPRLAND_CUSTOM_KEYBINDS_PATH
       resolved_path = raw_path.resolve()
       resolved_path.parent.mkdir(parents=True, exist_ok=True)
       
       existing = resolved_path.read_text(encoding="utf-8") if resolved_path.is_file() else ""
       block = generate_hyprland_block()
       pattern = re.compile(r"-- voicemode start\n.*?-- voicemode end\n?", re.DOTALL)
       
       if pattern.search(existing):
           new_content = pattern.sub(block, existing)
       else:
           prefix = "" if not existing or existing.endswith("\n") else "\n"
           new_content = existing + prefix + block
           
       resolved_path.write_text(new_content, encoding="utf-8")
       print(f"Updated Hyprland keybinds in {resolved_path} (target of {raw_path})")
       
       # Reload Hyprland dynamically (D-09)
       if shutil.which("hyprctl"):
           try:
               subprocess.run(["hyprctl", "reload"], check=True, stdout=subprocess.DEVNULL)
               print("Hyprland reloaded successfully (`hyprctl reload`).")
           except (subprocess.CalledProcessError, OSError) as exc:
               print(f"Warning: failed to reload Hyprland via hyprctl: {exc}", file=sys.stderr)
       return 0
   ```
3. **Session Auto-Detection (D-05):**
   ```python
   def is_hyprland_session() -> bool:
       return (
           bool(os.getenv("HYPRLAND_INSTANCE_SIGNATURE"))
           or os.getenv("XDG_CURRENT_DESKTOP") == "Hyprland"
           or (shutil.which("hyprctl") is not None and bool(os.getenv("WAYLAND_DISPLAY")))
       )

   def install_hotkeys_dispatch() -> int:
       if is_hyprland_session():
           return install_hyprland_keybinds()
       return install_gnome_hotkey()
   ```

---

### Pattern 2: Atomic PID & Lifecycle State Management

#### Target File:
- [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) (Update `read_pid`, `write_pid`, add `read_pid_state`, `write_pid_state`)

#### Closest Existing Analog:
- [`voice.py:567-598`](file:///home/pera/github_repo/Voice/voice.py#L567-L598)

#### Existing Code Excerpt:
```python
def read_pid(path: Path = PID_FILE) -> Optional[int]:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return int(value) if value else None
    except (FileNotFoundError, ValueError, OSError):
        return None


def write_pid(path: Path = PID_FILE) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")
```

#### Adaptation Pattern to Implement:
1. **Backward-Compatible State String File Format (`<pid> <state>\n`):**
   Keep `read_pid()` returning `Optional[int]` by parsing the first whitespace-delimited token as an integer.
2. **State Reader `read_pid_state`:**
   ```python
   def read_pid_state(path: Path = PID_FILE) -> tuple[Optional[int], str]:
       try:
           content = path.read_text(encoding="utf-8").strip()
           if not content:
               return None, "idle"
           parts = content.split()
           pid = int(parts[0])
           state = parts[1] if len(parts) > 1 else "recording"
           return pid, state
       except (FileNotFoundError, ValueError, OSError):
           return None, "idle"

   def write_pid_state(pid: int, state: str, path: Path = PID_FILE) -> None:
       STATE_DIR.mkdir(parents=True, exist_ok=True)
       path.write_text(f"{pid} {state}\n", encoding="utf-8")

   def write_pid(path: Path = PID_FILE) -> None:
       write_pid_state(os.getpid(), "recording", path)
   ```

---

### Pattern 3: Hardened Process Aliveness & Identity Check

#### Target File:
- [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) (Harden `process_alive`)

#### Closest Existing Analog:
- [`voice.py:575-583`](file:///home/pera/github_repo/Voice/voice.py#L575-L583)

#### Existing Code Excerpt:
```python
def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
```

#### Adaptation Pattern to Implement (D-15):
Inspect `/proc/<pid>/cmdline` to prevent sending signals to unrelated recycled PIDs:
```python
def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    # Hardened identity verification: inspect /proc/<pid>/cmdline (D-15)
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        cmdline = cmdline_path.read_bytes().decode("utf-8", errors="ignore")
        # Ensure the process belongs to python/voice/voicemode
        return any(token in cmdline for token in ("voice", "python", "voicemode"))
    except (FileNotFoundError, ProcessLookupError):
        return False
    except (PermissionError, OSError):
        # In case /proc is restricted or owned by another user (not our child)
        return False
```

---

### Pattern 4: Concurrency Race Elimination & Busy Cue Protection

#### Target File:
- [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) (`toggle_background_recording`)

#### Closest Existing Analogs:
- [`voice.py:1251-1274`](file:///home/pera/github_repo/Voice/voice.py#L1251-L1274) (`toggle_background_recording`)
- [`voice.py:487-497`](file:///home/pera/github_repo/Voice/voice.py#L487-L497) (`play_cue` error tone)

#### Existing Code Excerpt:
```python
def toggle_background_recording(args: argparse.Namespace) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    pid = read_pid()
    if pid and process_alive(pid):
        os.kill(pid, signal.SIGUSR1)
        print("Stopping voice recording...")
        return 0
    if pid:
        remove_pid(pid)

    log = LOG_FILE.open("a", encoding="utf-8")
...
```

#### Adaptation Pattern to Implement (D-11, D-12, D-14):
```python
def toggle_background_recording(args: argparse.Namespace) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    pid, state = read_pid_state()
    
    if pid and process_alive(pid):
        # D-11: Double-tap startup race wait (up to 300ms)
        if state == "starting":
            deadline = time.monotonic() + 0.300
            while time.monotonic() < deadline:
                time.sleep(0.02)
                pid, state = read_pid_state()
                if not (pid and process_alive(pid)) or state != "starting":
                    break
        
        # D-12: Transcribing / Busy state protection
        if state == "transcribing":
            play_cue(args, "error")
            return 0
            
        # Normal recording stop trigger
        if state == "recording":
            os.kill(pid, signal.SIGUSR1)
            print("Stopping voice recording...")
            return 0

    if pid:
        remove_pid(pid)

    # D-14: Symmetric Mutex: silence active TTS before recording
    stop_tts(args, quiet=True)

    log = LOG_FILE.open("a", encoding="utf-8")
    log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} start ---\n")
    log.flush()
    proc = subprocess.Popen(
        background_argv(args),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    log.close()
    
    # Write initial 'starting' state immediately after spawn (D-11)
    write_pid_state(proc.pid, "starting")
    print("Started voice recording. Run `voice --toggle` again to stop.")
    return 0
```

---

### Pattern 5: Signal Differentiation, Watchdogs & Worker Event Loop

#### Target File:
- [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) (`run_background_recording`)

#### Closest Existing Analog:
- [`voice.py:1277-1358`](file:///home/pera/github_repo/Voice/voice.py#L1277-L1358) (`run_background_recording`)

#### Existing Code Excerpt:
```python
def run_background_recording(args: argparse.Namespace) -> int:
    input_device = parse_device(args.input_device)
    sample_rate = resolve_sample_rate(input_device, args.sample_rate)
    recorder = Recorder(sample_rate=sample_rate, input_device=input_device)
    stop_requested = False
    pid = os.getpid()

    def request_stop(signum, frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGUSR1, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    write_pid()
...
```

#### Adaptation Pattern to Implement (D-13, D-16, D-17, D-18, D-19):
```python
def run_background_recording(args: argparse.Namespace) -> int:
    pid = os.getpid()
    stop_requested = False
    cancel_requested = False

    # D-13: Differentiate SIGUSR1 (graceful stop & transcribe) vs SIGTERM/SIGINT (clean abort)
    def handle_usr1(signum, frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    def handle_cancel(signum, frame) -> None:
        nonlocal cancel_requested
        cancel_requested = True

    signal.signal(signal.SIGUSR1, handle_usr1)
    signal.signal(signal.SIGTERM, handle_cancel)
    signal.signal(signal.SIGINT, handle_cancel)

    input_device = parse_device(args.input_device)
    sample_rate = resolve_sample_rate(input_device, args.sample_rate)
    recorder = Recorder(sample_rate=sample_rate, input_device=input_device)

    # Transition state to 'recording' once handlers and audio are ready (D-11)
    write_pid_state(pid, "recording")

    max_duration = float(os.getenv("VOICE_MAX_RECORDING_SECONDS", str(MAX_RECORDING_SECONDS)))
    beep_interval = float(os.getenv("VOICE_RECORDING_BEEP_INTERVAL", str(getattr(args, "recording_beep_interval", 5.0))))

    wav_path: Optional[Path] = None
    should_delete = False
    try:
        play_cue(args, "start")
        recorder.start()
        # D-17: Routine toast "Recording..." SUPPRESSED for focus safety
        print(f"Recording in background at {sample_rate} Hz. PID {pid}.", flush=True)

        next_recording_cue = (time.monotonic() + beep_interval) if (args.beep and beep_interval > 0) else None

        while not stop_requested and not cancel_requested:
            # D-16: Maximum duration ceiling
            if recorder.started_at and (time.monotonic() - recorder.started_at) >= max_duration:
                print(f"Safety ceiling: reached max duration ({int(max_duration)}s).", flush=True)
                # D-18: Exceptional notification allowed
                notify(APP_NAME, f"Max recording duration ({int(max_duration)}s) reached. Transcribing...", args)
                break
            # D-19: Periodic reminder cue
            if next_recording_cue is not None and time.monotonic() >= next_recording_cue:
                play_cue(args, "recording")
                next_recording_cue = time.monotonic() + beep_interval
            time.sleep(0.05)

        # Handle clean abort (SIGTERM / SIGINT) without transcribing or typing (D-13)
        if cancel_requested:
            print("Recording cancelled by signal.", flush=True)
            return 0

        # Transition to transcribing state (D-12)
        write_pid_state(pid, "transcribing")
        wav_path, duration, should_delete = recorder.stop_to_wav(args.save_dir)
        play_cue_async(args, "stop")
        # D-17: Routine toast "Transcribing..." SUPPRESSED
        print(f"Stopped ({duration:.1f}s). Transcribing {wav_path}...", flush=True)

        # D-16: Arm 60s transcription watchdog
        def watchdog_fired():
            print("Transcription watchdog expired (60s). Terminating daemon.", file=sys.stderr, flush=True)
            remove_pid(pid)
            os._exit(1)

        watchdog = threading.Timer(60.0, watchdog_fired)
        watchdog.daemon = True
        watchdog.start()

        try:
            model_state = load_model(args)
            text, _ = transcribe(model_state, wav_path, args)
        finally:
            watchdog.cancel()

        print(text or "[no speech detected]", flush=True)

        if text and args.paste:
            if insert_text(text, args):
                print("Transcript inserted.", flush=True)
                # D-17: Routine toast "Transcript inserted." SUPPRESSED
            else:
                print("Transcript insert failed.", flush=True)
                # D-18: Exceptional error toast allowed
                notify(APP_NAME, "Transcript insert failed; see log.", args)
        elif text:
            notify(APP_NAME, "Transcript ready; see log.", args)
        else:
            # D-18: Exceptional no-speech toast allowed
            notify(APP_NAME, "No speech detected.", args)
        return 0
    except Exception as exc:
        play_cue(args, "error")
        notify(APP_NAME, str(exc), args)
        print(f"voice background error: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        if recorder.recording:
            try:
                recorder.stop_to_wav(None)
            except Exception:
                pass
        if should_delete and wav_path:
            try:
                wav_path.unlink()
            except OSError:
                pass
        remove_pid(pid)
```

---

### Pattern 6: Symmetric STT/TTS Mutual Exclusion

#### Target File:
- [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) (`toggle_background_recording`, `speak_selection`)

#### Closest Existing Analogs:
- [`voice.py:932-956`](file:///home/pera/github_repo/Voice/voice.py#L932-L956) (`stop_tts`)
- [`voice.py:1034-1080`](file:///home/pera/github_repo/Voice/voice.py#L1034-L1080) (`speak_selection`)

#### Existing Code Excerpt in `speak_selection`:
```python
def speak_selection(args: argparse.Namespace) -> int:
    cleanup_stale_tts_files()
    pid = read_pid(TTS_PID_FILE)
    if pid and process_alive(pid):
        stop_tts(args)
        return 0
    if pid:
        remove_pid(pid, TTS_PID_FILE)

    raw_text, source = selected_or_clipboard_text()
...
```

#### Adaptation Pattern to Implement (D-14):
Before TTS processes selection or launches synthesis, stop active STT recording cleanly via `SIGTERM`:
```python
def cancel_active_stt() -> None:
    stt_pid = read_pid(PID_FILE)
    if stt_pid and process_alive(stt_pid):
        try:
            os.kill(stt_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        remove_pid(stt_pid, PID_FILE)

def speak_selection(args: argparse.Namespace) -> int:
    cleanup_stale_tts_files()
    # D-14: Cancel active STT recording to prevent concurrent audio
    cancel_active_stt()

    pid = read_pid(TTS_PID_FILE)
    if pid and process_alive(pid):
        stop_tts(args)
        return 0
...
```

---

### Pattern 7: Focus-Safe Desktop Notifications & Low Urgency Settings

#### Target File:
- [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) (`notify`, `stop_tts`, `speak_selection`)

#### Closest Existing Analog:
- [`voice.py:558-565`](file:///home/pera/github_repo/Voice/voice.py#L558-L565) (`notify`)

#### Existing Code Excerpt:
```python
def notify(title: str, message: str, args: argparse.Namespace) -> None:
    if not getattr(args, "notify", True):
        return
    notify_send = shutil.which("notify-send")
    if not notify_send or (not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY")):
        return
    subprocess.run([notify_send, title, message], check=False, stdin=subprocess.DEVNULL)
```

#### Adaptation Pattern to Implement (D-17, D-18, D-20):
Add urgency and timeout controls to `notify()`:
```python
def notify(
    title: str,
    message: str,
    args: argparse.Namespace,
    *,
    urgency: str = "normal",
    expire_time_ms: Optional[int] = None,
) -> None:
    if not getattr(args, "notify", True):
        return
    notify_send = shutil.which("notify-send")
    if not notify_send or (not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY")):
        return
    cmd = [notify_send, title, message]
    if urgency:
        cmd.extend(["-u", urgency])
    if expire_time_ms is not None:
        cmd.extend(["-t", str(expire_time_ms)])
    subprocess.run(cmd, check=False, stdin=subprocess.DEVNULL)
```

Usage in TTS informational toasts (D-20):
```python
# In speak_selection:
notify("Voice TTS", toast_msg, args, urgency="low", expire_time_ms=2000)

# In stop_tts:
notify("Voice TTS", "Speech stopped.", args, urgency="low", expire_time_ms=2000)
```

---

### Pattern 8: Test Harness & Mocking Conventions

#### Target File:
- [`tests/test_hyprland_daemon.py`](file:///home/pera/github_repo/Voice/tests/test_hyprland_daemon.py)

#### Closest Existing Analogs:
- [`tests/test_wayland_input.py`](file:///home/pera/github_repo/Voice/tests/test_wayland_input.py)
- [`tests/test_tts_pipeline.py`](file:///home/pera/github_repo/Voice/tests/test_tts_pipeline.py)

#### Existing Patterns to Copy:
1. **Module Header & Standard Imports:**
   ```python
   #!/usr/bin/env python3
   """Unit tests for Hyprland keybinding integration and hardened daemon lifecycle."""

   from __future__ import annotations

   import argparse
   import os
   import signal
   import subprocess
   import tempfile
   import time
   import unittest
   from pathlib import Path
   from unittest.mock import MagicMock, call, patch

   import voice
   ```
2. **Temporary File & Symlink Fixtures:**
   ```python
   with tempfile.TemporaryDirectory() as tmp_dir:
       real_file = Path(tmp_dir) / "dotfiles" / "keybinds.lua"
       real_file.parent.mkdir(parents=True)
       real_file.write_text("-- initial config\n", encoding="utf-8")
       
       symlink_file = Path(tmp_dir) / "config" / "keybinds.lua"
       symlink_file.parent.mkdir(parents=True)
       symlink_file.symlink_to(real_file)
       
       voice.install_hyprland_keybinds(config_path=symlink_file)
       self.assertTrue(symlink_file.is_symlink())
       self.assertIn("-- voicemode start", real_file.read_text())
   ```
3. **Mocking `/proc/<pid>/cmdline` in `test_hardened_process_alive`:**
   ```python
   with patch("os.kill") as mock_kill, \
        patch("pathlib.Path.read_bytes", return_value=b"python3\x00voice.py\x00--record-background"):
       mock_kill.return_value = None
       self.assertTrue(voice.process_alive(12345))

   # Non-matching cmdline
   with patch("os.kill") as mock_kill, \
        patch("pathlib.Path.read_bytes", return_value=b"/usr/bin/bash\x00"):
       mock_kill.return_value = None
       self.assertFalse(voice.process_alive(12345))
   ```
4. **Mocking Subprocess & Hyprctl Reload:**
   ```python
   @patch("shutil.which", return_value="/usr/bin/hyprctl")
   @patch("subprocess.run")
   def test_install_hyprland_reloads_hyprctl(self, mock_run, mock_which):
       mock_run.return_value = MagicMock(returncode=0)
       voice.install_hyprland_keybinds(config_path=self.test_path)
       mock_run.assert_called_with(["hyprctl", "reload"], check=True, stdout=subprocess.DEVNULL)
   ```

---

## 3. Concrete Implementation Anti-Patterns & Traps to Avoid

| Anti-Pattern / Trap | Risk | Mitigation Rule |
|---|---|---|
| **Using `os.replace` on Symlink** | Destroys dotfiles stow symlink, replacing it with an untracked regular file (breaks git versioning). | Always call `target.resolve()` and write directly to the resolved real file path (D-07). |
| **Sending `SIGUSR1` to `starting` Child** | Child Python runtime has not yet set custom signal handler; Linux triggers default signal action `SIG_DFL` (immediate silent process kill). | Poll `read_pid_state()` up to 300ms waiting for state to reach `recording` before sending `SIGUSR1` (D-11). |
| **Triggering Transcription on `SIGTERM`** | Spurious keystroke injection when session is stopping or TTS interrupts STT. | Strictly separate signal actions: only `SIGUSR1` transcribes and types; `SIGTERM`/`SIGINT` aborts and unlinks immediately (D-13). |
| **Routine Toasts Before `wtype`** | SwayNC / Mako / Quickshell notification overlays capture compositor focus, swallowing subsequent `wtype` keystrokes. | Suppress routine toasts ("Recording...", "Transcribing...", "Transcript inserted."). Rely on audio sine chimes (880 Hz, stop chime) for normal feedback (D-17). |
| **Blind PID Aliveness via `os.kill(pid, 0)`** | PID recycling on long-running systems causes signals to hit unrelated processes. | Inspect `/proc/<pid>/cmdline` for `voice` / `python` / `voicemode` tokens (D-15). |
| **Locked Keybindings in Lua** | Using `locked = true` allows hotkeys to activate while desktop is locked (`hyprlock`), risking secret leakage or unexpected typing into locked sessions. | Never add `locked = true` to voice keybindings (D-04). |
| **Breaking `read_pid()` Callers** | Breaking existing code that expects `read_pid()` to return `Optional[int]`. | Make `read_pid()` parse the first whitespace-delimited token as integer; introduce `read_pid_state()` for tuples. |

---

## 4. Pattern Matrix Summary

| Requirement | Implementation Artifact | Pattern Copied From | Key Technical Elements |
|---|---|---|---|
| `HYPR-01` | `voice.py:generate_hyprland_block` | Existing Lua unbind syntax in `custom/keybinds.lua` | Idempotent block, unbind `SUPER + T`, bind `SUPER + SHIFT + M` & `SUPER + T`, full `$HOME/.local/bin/voice` path, unlocked-only |
| `HYPR-01` | `voice.py:install_hyprland_keybinds` | `voice.py:install_gnome_hotkey` | Resolves symlink via `path.resolve()`, regex block replacement, `hyprctl reload` execution |
| `HYPR-01` | `voice.py:parse_args` & dispatch | `voice.py:parse_args` | Adds `--print-hyprland`, `--install-hyprland`, desktop auto-detection via `HYPRLAND_INSTANCE_SIGNATURE` in `--install-hotkey` |
| `HYPR-02` | `voice.py:read_pid_state` / `write_pid_state` | `voice.py:read_pid` / `write_pid` | Atomic format `<pid> <state>\n`, transitions: `starting` -> `recording` -> `transcribing` -> `idle` |
| `HYPR-02` | `voice.py:toggle_background_recording` | `voice.py:toggle_background_recording` | 300ms poll for `starting`, error chime for `transcribing`, `stop_tts(quiet=True)` mutex |
| `HYPR-02` | `voice.py:run_background_recording` | `voice.py:run_background_recording` | Early signal registration, `SIGUSR1` vs `SIGTERM`, 5s periodic cue, 60s transcription watchdog, focus-safe toast suppression |
| `HYPR-02` | `voice.py:process_alive` | `voice.py:process_alive` | `/proc/<pid>/cmdline` validation against PID recycling |
| `HYPR-02` | `voice.py:notify` & `speak_selection` | `voice.py:notify` & `speak_selection` | `-u low -t 2000` for TTS toasts; STT cancellation mutex |
| Test Coverage | `tests/test_hyprland_daemon.py` | `tests/test_wayland_input.py` & `test_tts_pipeline.py` | Unit test cases for all keybinding and daemon lifecycle guarantees |
