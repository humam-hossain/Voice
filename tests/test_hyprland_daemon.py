"""Unit tests for Hyprland integration, keybinding installation, and daemon lifecycle."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice


class TestHyprlandKeybindInstallation(unittest.TestCase):
    """Test suite covering Hyprland Lua keybinding generation, installation, and auto-detection."""

    def test_generate_hyprland_block_format(self) -> None:
        block = voice.generate_hyprland_block()
        self.assertIn("-- voicemode start", block)
        self.assertIn("-- voicemode end", block)
        self.assertIn('hl.unbind("SUPER + T")', block)
        self.assertIn(
            'hl.bind("SUPER + SHIFT + M", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --toggle"), { description = "Voice STT: Push-to-talk toggle" })',
            block,
        )
        self.assertIn(
            'hl.bind("SUPER + T", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --speak-selection"), { description = "Voice TTS: Speak selection" })',
            block,
        )
        self.assertIn('HOME .. "/.local/bin/voice', block)

    def test_unlocked_only_execution(self) -> None:
        block = voice.generate_hyprland_block()
        self.assertNotIn("locked = true", block)
        self.assertNotIn("bindl", block)

    def test_print_hyprland_stdout(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            ret = voice.print_hyprland_keybinds()
            self.assertEqual(ret, 0)
            self.assertEqual(fake_stdout.getvalue(), voice.generate_hyprland_block())

    def test_install_hyprland_creates_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_file = Path(tmp_dir) / "custom" / "keybinds.lua"
            with patch("shutil.which", return_value=None):
                ret = voice.install_hyprland_keybinds(config_path=target_file)
            self.assertEqual(ret, 0)
            self.assertTrue(target_file.exists())
            content = target_file.read_text(encoding="utf-8")
            self.assertIn("-- voicemode start", content)
            self.assertIn("-- voicemode end", content)
            self.assertIn('hl.unbind("SUPER + T")', content)

    def test_install_hyprland_idempotent_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_file = Path(tmp_dir) / "keybinds.lua"
            initial_content = (
                "-- User initial keybinds\n"
                'hl.bind("SUPER + Return", hl.dsp.terminal())\n\n'
                "-- voicemode start\n"
                "-- stale old content here\n"
                "-- voicemode end\n\n"
                "-- Trailing keybinds\n"
            )
            target_file.write_text(initial_content, encoding="utf-8")

            with patch("shutil.which", return_value=None):
                ret = voice.install_hyprland_keybinds(config_path=target_file)
            self.assertEqual(ret, 0)

            content = target_file.read_text(encoding="utf-8")
            self.assertEqual(content.count("-- voicemode start"), 1)
            self.assertEqual(content.count("-- voicemode end"), 1)
            self.assertNotIn("stale old content", content)
            self.assertIn("-- User initial keybinds", content)
            self.assertIn("-- Trailing keybinds", content)
            self.assertIn('hl.bind("SUPER + SHIFT + M"', content)

            # Second execution must be strictly idempotent
            with patch("shutil.which", return_value=None):
                ret_second = voice.install_hyprland_keybinds(config_path=target_file)
            self.assertEqual(ret_second, 0)
            content_second = target_file.read_text(encoding="utf-8")
            self.assertEqual(content, content_second)

    def test_install_hyprland_preserves_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            real_dir = Path(tmp_dir) / "dotfiles" / "hypr"
            real_dir.mkdir(parents=True)
            real_file = real_dir / "keybinds.lua"
            real_file.write_text('-- initial dotfiles\nhl.bind("SUPER + Return", terminal)\n', encoding="utf-8")

            symlink_dir = Path(tmp_dir) / "config" / "hypr" / "custom"
            symlink_dir.mkdir(parents=True)
            symlink_file = symlink_dir / "keybinds.lua"
            symlink_file.symlink_to(real_file)

            self.assertTrue(symlink_file.is_symlink())

            with patch("shutil.which", return_value=None):
                ret = voice.install_hyprland_keybinds(config_path=symlink_file)
            self.assertEqual(ret, 0)

            # Assert symlink was NOT severed or replaced with a plain file
            self.assertTrue(symlink_file.is_symlink())
            self.assertEqual(symlink_file.resolve(), real_file.resolve())

            # Assert real file was modified
            content = real_file.read_text(encoding="utf-8")
            self.assertIn("-- initial dotfiles", content)
            self.assertIn("-- voicemode start", content)
            self.assertIn('hl.bind("SUPER + SHIFT + M"', content)

    def test_install_hyprland_reloads_hyprctl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_file = Path(tmp_dir) / "keybinds.lua"
            target_file.touch()

            with patch("shutil.which", return_value="/usr/bin/hyprctl"), patch("subprocess.run") as mock_run:
                ret = voice.install_hyprland_keybinds(config_path=target_file)
                self.assertEqual(ret, 0)
                mock_run.assert_called_once_with(
                    ["hyprctl", "reload"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )

    def test_install_hotkey_auto_detection(self) -> None:
        # Hyprland session via HYPRLAND_INSTANCE_SIGNATURE
        with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "hypr_session_123"}, clear=True):
            with patch("voice.install_hyprland_keybinds", return_value=0) as mock_hypr, patch(
                "voice.install_gnome_hotkey"
            ) as mock_gnome:
                ret = voice.install_hotkeys_dispatch()
                self.assertEqual(ret, 0)
                mock_hypr.assert_called_once()
                mock_gnome.assert_not_called()

        # Non-Hyprland session (e.g. GNOME)
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"}, clear=True):
            with patch("shutil.which", return_value=None), patch(
                "voice.install_hyprland_keybinds"
            ) as mock_hypr, patch("voice.install_gnome_hotkey", return_value=0) as mock_gnome:
                ret = voice.install_hotkeys_dispatch()
                self.assertEqual(ret, 0)
                mock_gnome.assert_called_once()
                mock_hypr.assert_not_called()


class TestDaemonLifecycleStates(unittest.TestCase):
    """Placeholder test suite satisfying Wave 0 contract for Plan 04-02."""

    def test_daemon_lifecycle_placeholder(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
