#!/usr/bin/env python3
"""Unit tests for Wayland keystroke injection, backends, and shortcuts in voicemode."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import unittest
from unittest.mock import MagicMock, call, patch

import voice


class TestTextNormalization(unittest.TestCase):
    """Test newline and whitespace normalization for speech transcripts."""

    def test_strip_transcripts(self):
        self.assertEqual(voice.normalize_typed_text("  hello world  "), "hello world")

    def test_newlines_replaced_with_spaces_by_default(self):
        raw = "Line one\nLine two\r\nLine three\rLine four"
        expected = "Line one Line two Line three Line four"
        self.assertEqual(voice.normalize_typed_text(raw, keep_newlines=False), expected)

    def test_keep_newlines_opt_in(self):
        raw = "Line one\nLine two\r\nLine three"
        self.assertEqual(voice.normalize_typed_text(raw, keep_newlines=True), raw)

    def test_empty_and_single_char_input(self):
        self.assertEqual(voice.normalize_typed_text(""), "")
        self.assertEqual(voice.normalize_typed_text("   "), "")
        self.assertEqual(voice.normalize_typed_text("\n\r\n"), "")
        self.assertEqual(voice.normalize_typed_text("a"), "a")
        self.assertEqual(voice.normalize_typed_text(" a "), "a")

    def test_unicode_preservation(self):
        raw = "  café 🚀 日本語\nMünchen  "
        expected = "café 🚀 日本語 München"
        self.assertEqual(voice.normalize_typed_text(raw, keep_newlines=False), expected)
        self.assertEqual(
            voice.normalize_typed_text(raw, keep_newlines=True),
            "café 🚀 日本語\nMünchen",
        )


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
    def test_wtype_preferred_over_ydotool_in_auto_mode(self, mock_run, mock_which, mock_server):
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
    def test_wtype_omits_dash_d_when_delay_zero(self, mock_run, mock_which, mock_server):
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
    def test_wtype_failure_falls_back_to_ydotool(self, mock_run, mock_which, mock_server):
        mock_which.side_effect = lambda bin_name: f"/usr/bin/{bin_name}"
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, ["wtype"]),
            MagicMock(returncode=0),
        ]
        result = voice.type_text("hello", self.args)
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_called_with(
            ["ydotool", "type", "--key-delay", "2", "--", "hello"],
            check=True,
            timeout=15.0,
        )

    @patch("voice.display_server", return_value="wayland")
    @patch("time.sleep")
    @patch("shutil.which", return_value="/usr/bin/wtype")
    @patch("subprocess.run")
    def test_pre_type_delay_sleeps_before_typing(self, mock_run, mock_which, mock_sleep, mock_server):
        self.args.pre_type_delay = 50
        voice.type_text("hello", self.args)
        mock_sleep.assert_called_once_with(0.05)

    @patch("voice.display_server", return_value="wayland")
    @patch("shutil.which", return_value="/usr/bin/wtype")
    @patch("subprocess.run")
    def test_timeout_passed_to_subprocess(self, mock_run, mock_which, mock_server):
        voice.type_text("hello", self.args)
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("timeout"), 15.0)

    @patch("voice.display_server", return_value="wayland")
    @patch("subprocess.run")
    def test_empty_text_returns_false_without_subprocess(self, mock_run, mock_server):
        result = voice.type_text("   ", self.args)
        self.assertFalse(result)
        mock_run.assert_not_called()


class TestPasteClipboardWayland(unittest.TestCase):
    """Test paste_clipboard simulated shortcuts on Wayland."""

    def setUp(self):
        self.args = argparse.Namespace(wayland_backend="auto")

    @patch("voice.display_server", return_value="wayland")
    @patch("voice.copy_to_clipboard", return_value=True)
    @patch("shutil.which", return_value="/usr/bin/wtype")
    @patch("subprocess.run")
    @patch("time.sleep")
    def test_paste_ctrl_v_modifier_sequence(self, mock_sleep, mock_run, mock_which, mock_copy, mock_server):
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
    def test_terminal_paste_ctrl_shift_v_sequence(self, mock_sleep, mock_run, mock_which, mock_copy, mock_server):
        result = voice.paste_clipboard("payload", self.args, "ctrl+shift+v")
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["wtype", "-M", "ctrl", "-M", "shift", "-s", "20", "-k", "v", "-s", "20", "-m", "shift", "-m", "ctrl"],
            check=True,
            timeout=15.0,
        )

    @patch("voice.display_server", return_value="wayland")
    @patch("voice.copy_to_clipboard", return_value=True)
    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("time.sleep")
    def test_paste_wtype_failure_falls_back_to_ydotool(self, mock_sleep, mock_run, mock_which, mock_copy, mock_server):
        mock_which.side_effect = lambda bin_name: f"/usr/bin/{bin_name}"
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, ["wtype"]),
            MagicMock(returncode=0),
        ]
        result = voice.paste_clipboard("payload", self.args, "ctrl+v")
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_called_with(["ydotool", "key", "ctrl+v"], check=True, timeout=15.0)


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

    @patch("voice.paste_clipboard", return_value=True)
    @patch("voice.copy_to_clipboard", return_value=True)
    def test_paste_method_leaves_transcript_in_clipboard(self, mock_copy, mock_paste):
        self.args.output_method = "paste"
        result = voice.insert_text("speech text", self.args)
        self.assertTrue(result)
        mock_copy.assert_called_once_with("speech text")
        mock_paste.assert_called_once_with("speech text", self.args, "ctrl+v")

    @patch("voice.copy_to_clipboard")
    @patch("voice.type_text")
    def test_empty_input_bypasses_clipboard_and_typing(self, mock_type, mock_copy):
        result = voice.insert_text("   ", self.args)
        self.assertFalse(result)
        mock_copy.assert_not_called()
        mock_type.assert_not_called()


class TestWaylandCliParsing(unittest.TestCase):
    """Test CLI argument parsing and environment variable overrides."""

    def test_default_cli_values(self):
        with patch.object(voice.sys, "argv", ["voice"]):
            args = voice.parse_args()
            self.assertEqual(args.wayland_backend, "auto")
            self.assertEqual(args.pre_type_delay, 50)
            self.assertEqual(args.type_delay, 2)
            self.assertFalse(args.keep_newlines)
            self.assertEqual(args.output_method, "type")

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


class TestNotifyWayland(unittest.TestCase):
    """Test desktop notification detection in pure Wayland sessions."""

    @patch("shutil.which", return_value="/usr/bin/notify-send")
    @patch("subprocess.run")
    def test_notify_pure_wayland(self, mock_run, mock_which):
        args = argparse.Namespace(notify=True)
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1"}, clear=True):
            voice.notify("Title", "Message", args)
            mock_run.assert_called_once_with(
                ["/usr/bin/notify-send", "Title", "Message"],
                check=False,
                stdin=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    unittest.main()
