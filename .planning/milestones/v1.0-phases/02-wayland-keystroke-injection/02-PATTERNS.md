# Phase 2: Wayland Keystroke Injection - Pattern Map

**Generated:** 2026-09-19  
**Status:** Ready for planning  
**Domain:** Wayland Input Protocol Injection, `wtype`, `zwp_virtual_keyboard_v1`, Hyprland Keystroke Emulation, Rootless Shortcuts, Stdin Piping, Dual-Action Clipboard Synchronization  

---

## 1. Overview & File Catalog

This document defines the architectural patterns, concrete analogs, and code patterns to copy when implementing Phase 2. Downstream planners and executors must adhere strictly to these established patterns to maintain codebase consistency.

### Target Files to Create / Modify

| File Path | Action | Role | Closest Analog |
|---|---|---|---|
| [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) | Modify | Core CLI, Wayland typing/pasting backends, clipboard flow, background worker dispatch | [`voice.py`](file:///home/pera/github_repo/Voice/voice.py) (Self) |
| [`tests/test_wayland_input.py`](file:///home/pera/github_repo/Voice/tests/test_wayland_input.py) | Create | Unit test suite for Wayland input injection, CLI parsing, backend hierarchy, shortcuts, and failure alerts | Standard library `unittest.TestCase` / `unittest.mock` |
| [`docs/DEPENDENCIES.md`](file:///home/pera/github_repo/Voice/docs/DEPENDENCIES.md) | Modify | Document `wtype` dependency, Wayland protocols, and system requirements | [`docs/DEPENDENCIES.md`](file:///home/pera/github_repo/Voice/docs/DEPENDENCIES.md) (Self) |
| [`README.md`](file:///home/pera/github_repo/Voice/README.md) | Modify | Update Wayland status, dependencies, and CLI options documentation | [`README.md`](file:///home/pera/github_repo/Voice/README.md) (Self) |

---

## 2. File Pattern Mappings

### 2.1. Core Wayland Typing & Shortcut Simulation (`voice.py`)

#### Role & Data Flow
Receives transcribed speech text, cleanses special characters/newlines, buffers the text into the Wayland clipboard via `wl-copy` (dual-action persistence), and synthesizes keystrokes into the focused Hyprland window via `wtype` (or fallback `ydotool`) without requiring root permissions.
- **Inflow:** Raw transcript string from Faster-Whisper, CLI options in `args: argparse.Namespace`.
- **Processing:** 
  1. Unconditional upfront clipboard copy (`copy_to_clipboard(text)` via `wl-copy`).
  2. Text normalization (trim whitespace via `strip()`, replace internal newlines with spaces unless `keep_newlines` is enabled).
  3. Pre-typing settling pause (`time.sleep(pre_delay / 1000.0)`).
  4. Backend resolution (`wtype` preferred over `ydotool`).
  5. Stdin piping execution (`wtype [-d <ms>] -`) with 15s timeout protection and `-d 0` omission handling.
- **Outflow:** Keystrokes delivered to active Wayland window; on failure, user alert notification via `notify-send` confirming clipboard preservation.

#### Closest Analog & Existing Code
[`voice.py:431-518`](file:///home/pera/github_repo/Voice/voice.py#L431-L518)
Currently, `voice.py` relies exclusively on `ydotool` under Wayland (which fails if `ydotoold` daemon is not running as root) and does not pipe text via stdin or handle newline normalization:

```python
# Existing code in voice.py:451-460
def type_text(text: str, args: argparse.Namespace) -> bool:
    if display_server() == "wayland":
        ydotool = shutil.which("ydotool")
        if not ydotool:
            return False
        subprocess.run(
            [ydotool, "type", "--key-delay", str(args.type_delay), "--", text],
            check=True,
        )
        return True
    ...
```

#### Patterns to Implement in `voice.py`

##### A. Text Normalization Helper
Normalizes speech transcripts according to User Decisions D-12, D-13, and D-14:
```python
def normalize_typed_text(text: str, keep_newlines: bool = False) -> str:
    """Trim transcript and collapse internal newlines to spaces unless keep_newlines is True."""
    cleaned = text.strip()
    if not keep_newlines:
        cleaned = re.sub(r"[\r\n]+", " ", cleaned)
    return cleaned
```

##### B. Backend Resolution Helper
Resolves the active Wayland input backend based on user preference and tool availability (D-01, D-03):
```python
def resolve_wayland_backend(args: argparse.Namespace) -> Optional[str]:
    """Resolve Wayland typing backend: 'wtype', 'ydotool', or None."""
    pref = getattr(args, "wayland_backend", "auto")
    if pref == "wtype":
        return "wtype" if shutil.which("wtype") else None
    if pref == "ydotool":
        return "ydotool" if shutil.which("ydotool") else None
    # auto: prefer wtype, fallback to ydotool
    if shutil.which("wtype"):
        return "wtype"
    if shutil.which("ydotool"):
        return "ydotool"
    return None
```

##### C. Wayland Typing with `wtype` and Stdin Piping (`type_text`)
Implements rootless keystroke injection via `wtype` with critical upstream bug mitigation for `-d 0` (D-05, D-06, D-09, D-10, D-11):
```python
def type_text(text: str, args: argparse.Namespace) -> bool:
    text = normalize_typed_text(text, keep_newlines=getattr(args, "keep_newlines", False))
    if not text:
        return False

    pre_delay = max(0, getattr(args, "pre_type_delay", 50))
    if pre_delay > 0:
        time.sleep(pre_delay / 1000.0)

    server = display_server()
    if server == "wayland":
        backend = resolve_wayland_backend(args)
        if backend == "wtype":
            type_delay = max(0, getattr(args, "type_delay", 2))
            cmd = ["wtype"]
            # Upstream wtype aborts with "Invalid sleep time" if -d <= 0.
            # Omitting -d defaults delay_ms to 0.
            if type_delay > 0:
                cmd.extend(["-d", str(type_delay)])
            cmd.append("-")
            try:
                subprocess.run(cmd, input=text, text=True, check=True, timeout=15.0)
                return True
            except Exception as exc:
                # If 'auto' was requested, attempt fallback to ydotool before giving up
                if getattr(args, "wayland_backend", "auto") == "auto" and shutil.which("ydotool"):
                    try:
                        subprocess.run(
                            ["ydotool", "type", "--key-delay", str(type_delay), "--", text],
                            check=True,
                            timeout=15.0,
                        )
                        return True
                    except Exception:
                        pass
                return False

        if backend == "ydotool":
            type_delay = max(0, getattr(args, "type_delay", 2))
            try:
                subprocess.run(
                    ["ydotool", "type", "--key-delay", str(type_delay), "--", text],
                    check=True,
                    timeout=15.0,
                )
                return True
            except Exception:
                return False

        return False

    # X11 fallback
    xdotool = shutil.which("xdotool")
    if not os.getenv("DISPLAY") or not xdotool:
        return False
    try:
        subprocess.run(
            [
                xdotool,
                "type",
                "--clearmodifiers",
                "--delay",
                str(max(0, getattr(args, "type_delay", 2))),
                "--",
                text,
            ],
            check=True,
            timeout=15.0,
        )
        return True
    except Exception:
        return False
```

##### D. Simulated Rootless Paste Keystrokes (`paste_clipboard`)
Implements simulated paste shortcuts using `wtype` key modifiers with `ydotool` fallback (D-02, D-08, D-09):
```python
def paste_clipboard(text: str, args: argparse.Namespace, shortcut: str = "ctrl+v") -> bool:
    if not copy_to_clipboard(text):
        return False

    # Wayland clipboard readiness settling pause (D-08)
    time.sleep(0.15)

    server = display_server()
    if server == "wayland":
        backend = resolve_wayland_backend(args)
        if backend == "wtype":
            if shortcut == "ctrl+shift+v":
                cmd = ["wtype", "-M", "ctrl", "-M", "shift", "-s", "20", "-k", "v", "-s", "20", "-m", "shift", "-m", "ctrl"]
            else:
                cmd = ["wtype", "-M", "ctrl", "-s", "20", "-k", "v", "-s", "20", "-m", "ctrl"]
            try:
                subprocess.run(cmd, check=True, timeout=15.0)
                return True
            except Exception:
                if getattr(args, "wayland_backend", "auto") == "auto" and shutil.which("ydotool"):
                    try:
                        subprocess.run(["ydotool", "key", shortcut], check=True, timeout=15.0)
                        return True
                    except Exception:
                        pass
                return False

        if backend == "ydotool":
            try:
                subprocess.run(["ydotool", "key", shortcut], check=True, timeout=15.0)
                return True
            except Exception:
                return False

        return False

    # X11 fallback
    xdotool = shutil.which("xdotool")
    if not os.getenv("DISPLAY") or not xdotool:
        return False
    try:
        subprocess.run([xdotool, "key", "--clearmodifiers", shortcut], check=True, timeout=15.0)
        return True
    except Exception:
        return False
```

##### E. Dual-Action Clipboard Flow & Failure Alerting (`insert_text`)
Unconditionally preserves transcript in Wayland clipboard prior to typing, leaving it intact for user paste (D-04, D-15, D-16, D-17):
```python
def insert_text(text: str, args: argparse.Namespace) -> bool:
    if not text:
        return False

    # Dual behavior (D-16): Unconditionally buffer transcript in clipboard first
    copy_to_clipboard(text)

    if not args.paste:
        return False

    try:
        if args.output_method == "type":
            success = type_text(text, args)
            if not success:
                notify(APP_NAME, "Typing failed; transcript preserved in clipboard.", args)
            return success
        if args.output_method == "paste":
            return paste_clipboard(text, args, "ctrl+v")
        if args.output_method == "terminal-paste":
            return paste_clipboard(text, args, "ctrl+shift+v")
        if args.output_method == "clipboard":
            return True
        raise ValueError(f"unknown output method: {args.output_method}")
    except Exception as exc:
        notify(APP_NAME, f"Could not insert transcript: {exc}", args)
        return False
```

##### F. Wayland Notification Environment Check in `notify()`
Allows desktop notifications on pure Wayland sessions where `$WAYLAND_DISPLAY` is present but `$DISPLAY` (Xwayland) may not be:
```python
# Existing code in voice.py:378-385
def notify(title: str, message: str, args: argparse.Namespace) -> None:
    if not getattr(args, "notify", True):
        return
    notify_send = shutil.which("notify-send")
    # Support pure Wayland sessions by checking WAYLAND_DISPLAY as well as DISPLAY
    if not notify_send or (not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY")):
        return
    subprocess.run([notify_send, title, message], check=False, stdin=subprocess.DEVNULL)
```

##### G. CLI Argument Parsing & Value Clamping in `parse_args()`
Adds `--wayland-backend`, `--pre-type-delay`, and `--keep-newlines`, while clamping delay arguments to non-negative values (D-03, D-06, D-10, D-13):
```python
    parser.add_argument(
        "--wayland-backend",
        choices=("auto", "wtype", "ydotool"),
        default=os.getenv("VOICE_WAYLAND_BACKEND", "auto"),
        help="Wayland typing backend: auto, wtype, or ydotool. Default: auto.",
    )
    parser.add_argument(
        "--pre-type-delay",
        type=int,
        default=int(os.getenv("VOICE_PRE_TYPE_DELAY", "50")),
        help="Milliseconds to wait before keystroke injection starts. Default: 50.",
    )
    parser.add_argument(
        "--keep-newlines",
        dest="keep_newlines",
        action="store_true",
        default=env_bool("VOICE_KEEP_NEWLINES", False),
        help="Preserve literal newlines in typed transcripts.",
    )
    parser.add_argument(
        "--no-keep-newlines",
        dest="keep_newlines",
        action="store_false",
        help="Replace internal newlines with spaces before typing. Default.",
    )

    # Clamping in parse_args() after parser.parse_args():
    args.type_delay = max(0, args.type_delay)
    args.pre_type_delay = max(0, args.pre_type_delay)
```

##### H. Background Worker Argument Propagation in `background_argv()`
Ensures that new CLI arguments are serialized and forwarded to detached background recording processes ([`voice.py:841-869`](file:///home/pera/github_repo/Voice/voice.py#L841-L869)):
```python
    argv += ["--wayland-backend", args.wayland_backend]
    argv += ["--pre-type-delay", str(args.pre_type_delay)]
    if getattr(args, "keep_newlines", False):
        argv.append("--keep-newlines")
    else:
        argv.append("--no-keep-newlines")
```

---

### 2.2. Wayland Input Test Suite (`tests/test_wayland_input.py`)

#### Role & Data Flow
Provides comprehensive, zero-dependency unit tests running via Python's standard library `unittest` and `unittest.mock`. Tests mock system binaries (`wtype`, `ydotool`, `wl-copy`, `notify-send`) and verify exact argument formatting, timeout protection, stdin payloads, delay clamping, and fallback hierarchy without emitting actual desktop keystrokes.

#### Closest Analog
[`tests/`](file:///home/pera/github_repo/Voice/tests) is being established in Phase 2. The pattern follows Python standard library `unittest.TestCase` as documented in [`.planning/codebase/TESTING.md`](file:///home/pera/github_repo/Voice/.planning/codebase/TESTING.md) and [`.planning/phases/02-wayland-keystroke-injection/02-RESEARCH.md`](file:///home/pera/github_repo/Voice/.planning/phases/02-wayland-keystroke-injection/02-RESEARCH.md).

#### Pattern to Implement (`tests/test_wayland_input.py`)

```python
#!/usr/bin/env python3
"""Unit tests for Wayland keystroke injection, backends, and shortcuts in voicemode."""

from __future__ import annotations

import argparse
import os
import subprocess
import unittest
from unittest.mock import MagicMock, call, patch

import voice


class TestWaylandCliParsing(unittest.TestCase):
    """Test CLI argument parsing and environment variable overrides."""

    def test_default_cli_values(self):
        with patch.object(voice.sys, "argv", ["voice"]):
            args = voice.parse_args()
            self.assertEqual(args.wayland_backend, "auto")
            self.assertEqual(args.pre_type_delay, 50)
            self.assertEqual(args.type_delay, 2)
            self.assertFalse(args.keep_newlines)

    def test_cli_flags_override_defaults(self):
        test_argv = [
            "voice",
            "--wayland-backend", "wtype",
            "--pre-type-delay", "100",
            "--type-delay", "10",
            "--keep-newlines",
        ]
        with patch.object(voice.sys, "argv", test_argv):
            args = voice.parse_args()
            self.assertEqual(args.wayland_backend, "wtype")
            self.assertEqual(args.pre_type_delay, 100)
            self.assertEqual(args.type_delay, 10)
            self.assertTrue(args.keep_newlines)

    def test_environment_variables_override_defaults(self):
        env = {
            "VOICE_WAYLAND_BACKEND": "ydotool",
            "VOICE_PRE_TYPE_DELAY": "80",
            "VOICE_TYPE_DELAY": "5",
            "VOICE_KEEP_NEWLINES": "1",
        }
        with patch.dict(os.environ, env), patch.object(voice.sys, "argv", ["voice"]):
            args = voice.parse_args()
            self.assertEqual(args.wayland_backend, "ydotool")
            self.assertEqual(args.pre_type_delay, 80)
            self.assertEqual(args.type_delay, 5)
            self.assertTrue(args.keep_newlines)

    def test_negative_delays_clamped_to_zero(self):
        test_argv = ["voice", "--type-delay", "-10", "--pre-type-delay", "-50"]
        with patch.object(voice.sys, "argv", test_argv):
            args = voice.parse_args()
            self.assertEqual(args.type_delay, 0)
            self.assertEqual(args.pre_type_delay, 0)


class TestBackgroundArgvSerialization(unittest.TestCase):
    """Test propagation of Phase 2 arguments to background worker."""

    def test_background_argv_serialization(self):
        args = argparse.Namespace(
            model="small.en",
            device="cpu",
            compute_type="int8",
            beam_size=1,
            language="en",
            input_device=None,
            sample_rate=16000,
            save_dir=None,
            allow_download=False,
            output_method="type",
            type_delay=5,
            recording_beep_interval=5.0,
            beep_volume=0.08,
            beep_output_device=None,
            beep=True,
            paste=True,
            notify=True,
            wayland_backend="wtype",
            pre_type_delay=50,
            keep_newlines=True,
        )
        argv = voice.background_argv(args)
        self.assertIn("--wayland-backend", argv)
        self.assertIn("wtype", argv)
        self.assertIn("--pre-type-delay", argv)
        self.assertIn("50", argv)
        self.assertIn("--keep-newlines", argv)


class TestTextNormalization(unittest.TestCase):
    """Test newline and whitespace normalization for speech transcripts."""

    def test_strip_transcripts(self):
        self.assertEqual(voice.normalize_typed_text("  hello world  "), "hello world")

    def test_newlines_replaced_with_spaces_by_default(self):
        raw = "Line one\nLine two\r\nLine three\rLine four"
        expected = "Line one Line two Line three Line four"
        self.assertEqual(voice.normalize_typed_text(raw, keep_newlines=False), expected)

    def test_keep_newlines_preserves_linebreaks(self):
        raw = "Line one\nLine two\r\nLine three"
        self.assertEqual(voice.normalize_typed_text(raw, keep_newlines=True), raw)


class TestTypeTextWayland(unittest.TestCase):
    """Test type_text behavior on Wayland with wtype and ydotool."""

    def setUp(self):
        self.args = argparse.Namespace(
            type_delay=2,
            pre_type_delay=0,
            keep_newlines=False,
            wayland_backend="auto",
        )

    @patch("voice.display_server", return_value="wayland")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_wtype_preferred_over_ydotool_in_auto_mode(self, mock_run, mock_which):
        mock_which.side_effect = lambda bin_name: f"/usr/bin/{bin_name}"
        result = voice.type_text("hello", self.args)
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["wtype", "-d", "2", "-"],
            input="hello",
            text=True,
            check=True,
            timeout=15.0,
        )

    @patch("voice.display_server", return_value="wayland")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_wtype_omits_dash_d_when_delay_zero(self, mock_run, mock_which):
        """Verify upstream wtype bug mitigation: omit -d when delay is 0."""
        mock_which.side_effect = lambda bin_name: f"/usr/bin/{bin_name}"
        self.args.type_delay = 0
        result = voice.type_text("hello", self.args)
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["wtype", "-"],
            input="hello",
            text=True,
            check=True,
            timeout=15.0,
        )

    @patch("voice.display_server", return_value="wayland")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_wtype_failure_falls_back_to_ydotool(self, mock_run, mock_which):
        mock_which.side_effect = lambda bin_name: f"/usr/bin/{bin_name}"
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, ["wtype"]),
            MagicMock(returncode=0),
        ]
        result = voice.type_text("hello", self.args)
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)
        # Verify fallback call to ydotool
        mock_run.assert_called_with(
            ["ydotool", "type", "--key-delay", "2", "--", "hello"],
            check=True,
            timeout=15.0,
        )

    @patch("voice.display_server", return_value="wayland")
    @patch("time.sleep")
    @patch("shutil.which", return_value="/usr/bin/wtype")
    @patch("subprocess.run")
    def test_pre_type_delay_sleeps_before_typing(self, mock_run, mock_which, mock_sleep):
        self.args.pre_type_delay = 50
        voice.type_text("hello", self.args)
        mock_sleep.assert_called_once_with(0.05)


class TestPasteClipboardWayland(unittest.TestCase):
    """Test paste_clipboard simulated shortcuts on Wayland."""

    def setUp(self):
        self.args = argparse.Namespace(wayland_backend="auto")

    @patch("voice.display_server", return_value="wayland")
    @patch("voice.copy_to_clipboard", return_value=True)
    @patch("shutil.which", return_value="/usr/bin/wtype")
    @patch("subprocess.run")
    @patch("time.sleep")
    def test_paste_ctrl_v_modifier_sequence(self, mock_sleep, mock_run, mock_which, mock_copy):
        result = voice.paste_clipboard("payload", self.args, "ctrl+v")
        self.assertTrue(result)
        mock_sleep.assert_called_once_with(0.15)
        mock_run.assert_called_once_with(
            ["wtype", "-M", "ctrl", "-s", "20", "-k", "v", "-s", "20", "-m", "ctrl"],
            check=True,
            timeout=15.0,
        )

    @patch("voice.display_server", return_value="wayland")
    @patch("voice.copy_to_clipboard", return_value=True)
    @patch("shutil.which", return_value="/usr/bin/wtype")
    @patch("subprocess.run")
    @patch("time.sleep")
    def test_terminal_paste_ctrl_shift_v_sequence(self, mock_sleep, mock_run, mock_which, mock_copy):
        result = voice.paste_clipboard("payload", self.args, "ctrl+shift+v")
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["wtype", "-M", "ctrl", "-M", "shift", "-s", "20", "-k", "v", "-s", "20", "-m", "shift", "-m", "ctrl"],
            check=True,
            timeout=15.0,
        )


class TestInsertTextDualBehavior(unittest.TestCase):
    """Test dual clipboard persistence and error notifications in insert_text."""

    def setUp(self):
        self.args = argparse.Namespace(
            paste=True,
            output_method="type",
            notify=True,
            type_delay=2,
            pre_type_delay=0,
            keep_newlines=False,
            wayland_backend="auto",
        )

    @patch("voice.copy_to_clipboard")
    @patch("voice.type_text", return_value=True)
    def test_unconditional_clipboard_persistence(self, mock_type, mock_copy):
        result = voice.insert_text("speech text", self.args)
        self.assertTrue(result)
        mock_copy.assert_called_once_with("speech text")
        mock_type.assert_called_once_with("speech text", self.args)

    @patch("voice.notify")
    @patch("voice.copy_to_clipboard")
    @patch("voice.type_text", return_value=False)
    def test_typing_failure_alerts_user_with_clipboard_preservation(self, mock_type, mock_copy, mock_notify):
        result = voice.insert_text("speech text", self.args)
        self.assertFalse(result)
        mock_copy.assert_called_once_with("speech text")
        mock_notify.assert_called_once_with(
            voice.APP_NAME,
            "Typing failed; transcript preserved in clipboard.",
            self.args,
        )


if __name__ == "__main__":
    unittest.main()
```

---

### 2.3. Documentation Updates (`docs/DEPENDENCIES.md`, `README.md`)

#### Role & Data Flow
Informs users and packagers about system dependencies, distinguishing between Wayland tools (`wtype`, `wl-clipboard`) and legacy X11 tools (`xdotool`, `xclip`).

#### Pattern to Implement in `docs/DEPENDENCIES.md`
Add a section detailing the Wayland input injection stack:
```markdown
## Wayland Input & Clipboard Stack

| Component | Package (Arch) | Role | Permissions |
|---|---|---|---|
| `wtype` | `wtype` | Rootless keystroke injection & simulated shortcuts | Unprivileged (interfaces with `zwp_virtual_keyboard_v1`) |
| `wl-clipboard` | `wl-clipboard` | Clipboard management (`wl-copy`, `wl-paste`) | Unprivileged |
| `ydotool` | `ydotool` | Secondary fallback typing backend | Optional (requires root/uinput daemon `ydotoold`) |
```

#### Pattern to Implement in `README.md`
Update the Status and Installation sections to highlight native Arch/Wayland support:
```markdown
Tested target:
```text
OS: Arch Linux
Compositor: Hyprland (Wayland)
Python: 3.12
STT: faster-whisper (CPU int8)
Text insertion: wtype (primary, rootless) with ydotool fallback
Selection reading / Clipboard: wl-clipboard (wl-copy, wl-paste)
```
```

---

## 3. Cross-Cutting Patterns & Conventions

### 3.1. Subprocess Execution & Safety Boundaries
All subprocess invocations for input simulation and clipboard manipulation must follow strict safety rules:
1. **Never use `shell=True`:** Pass argv as a list (`['wtype', ...]`) to eliminate shell expansion risks.
2. **Stdin Piping (`input=text`):** Never pass text transcripts as command-line arguments to `wtype`. Use `input=text, text=True` with `-` as the final CLI token.
3. **Mandatory Subprocess Timeout:** All external tool calls (`wtype`, `ydotool`, `xdotool`) must specify `timeout=15.0` to guarantee that compositor socket freezes do not deadlock the daemon.
4. **Binary Availability Check:** Check `shutil.which(binary)` prior to invocation and handle missing binaries cleanly without throwing `FileNotFoundError`.

### 3.2. Timing Calibration & Delays
Maintain consistent timing constants across the codebase:
- **Per-keystroke Delay:** Default 2ms (`--type-delay 2`).
- **Pre-typing Settling Pause:** Default 50ms (`--pre-type-delay 50`, `VOICE_PRE_TYPE_DELAY`).
- **Clipboard Settling Pause:** Mandatory 150ms sleep (`time.sleep(0.15)`) between `copy_to_clipboard` and paste keystroke dispatch.
- **Modifier Inter-key Delay:** 20ms pause (`-s 20`) between modifier press/release in `wtype` paste sequences.

### 3.3. Dual-Action Clipboard Architecture
Rather than handling failures with complex reactive rollback or fallback routines:
1. Every successful transcription immediately invokes `copy_to_clipboard(text)` via `wl-copy`.
2. Typing proceeds knowing the text is already safe in the clipboard.
3. If typing fails, an alert is sent informing the user: `"Typing failed; transcript preserved in clipboard."`. The user can instantly paste with `Ctrl+V`.

---

## 4. Anti-Patterns & Guardrails

| Anti-Pattern | Hazard | Established Safe Pattern |
|---|---|---|
| `wtype -d 0 -` | `wtype` explicitly aborts with `Invalid sleep time` if `-d <= 0`. | Omit `-d` entirely when `type_delay <= 0`. Defaults to 0ms internally. |
| Passing transcript via CLI args (`wtype "$text"`) | Transcripts starting with `-` are parsed as flags; long texts exceed `ARG_MAX`; special characters break. | Pipe text via stdin (`wtype -`) with `subprocess.run(cmd, input=text, text=True)`. |
| Unbounded `subprocess.run()` | If compositor stalls or virtual keyboard seat deadlocks, worker hangs indefinitely. | Always specify `timeout=15.0`. |
| Typing raw newlines (`\n`) | `wtype` maps `\n` to `Return`, prematurely dispatching chat messages or executing terminal commands. | Replace newlines with spaces by default (`normalize_typed_text`), with opt-in `--keep-newlines`. |
| Zero pre-typing delay | Typing starts while user is still physically holding `Super+B`, causing modifier key chord collisions. | Enforce 50ms settling pause (`pre_type_delay`) before injection. |
| Forgetting daemon arg serialization | User configures `--wayland-backend ydotool` on CLI, but detached daemon runs with default `wtype`. | Explicitly forward `--wayland-backend`, `--pre-type-delay`, and `--keep-newlines` in `background_argv()`. |
| Checking only `$DISPLAY` in `notify()` | Desktop notifications fail silently on pure Wayland sessions where Xwayland is not loaded. | Check both `os.getenv("DISPLAY")` and `os.getenv("WAYLAND_DISPLAY")`. |

---

## 5. Verification Pattern Reference

Downstream planners and executors should use these exact command sequences for test verification:

```bash
# 1. Run unit test suite
./.venv/bin/python -m unittest tests/test_wayland_input.py

# 2. Run full discovery test suite
./.venv/bin/python -m unittest discover tests

# 3. Verify CLI help options
./.venv/bin/python voice.py --help | grep -E "wayland-backend|pre-type-delay|keep-newlines"

# 4. Verify background argument serialization
./.venv/bin/python -c "
import voice
args = voice.parse_args()
argv = voice.background_argv(args)
assert '--wayland-backend' in argv
assert '--pre-type-delay' in argv
print('Background argv verification: PASS')
"

# 5. Verify wtype zero-delay injection behavior
printf "" | wtype -

# 6. Verify wtype delayed injection behavior
printf "test" | wtype -d 2 -

# 7. Verify dual clipboard copy
./.venv/bin/python -c "
import voice
assert voice.copy_to_clipboard('pattern-map-test')
" && wl-paste
```

---

*Phase 2 Pattern Map complete. Ready for task decomposition in Plan 02-01 and Plan 02-02.*
