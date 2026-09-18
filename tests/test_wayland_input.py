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


if __name__ == "__main__":
    unittest.main()
