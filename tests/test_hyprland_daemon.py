"""Unit tests for Hyprland integration, keybinding installation, and daemon lifecycle."""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import time
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
            'hl.bind("SUPER + SHIFT + M", '
            'hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --toggle"), '
            '{ description = "Voice STT: Push-to-talk toggle" })',
            block,
        )
        self.assertIn(
            'hl.bind("SUPER + T", '
            'hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --speak-selection"), '
            '{ description = "Voice TTS: Speak selection" })',
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
    """Test suite covering PID state tracking, aliveness verification, signal handling, and mutual exclusion."""

    def test_write_and_read_pid_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pid_file = Path(tmp_dir) / "recorder.pid"
            voice.write_pid_state(1234, "starting", path=pid_file)
            self.assertEqual(voice.read_pid_state(pid_file), (1234, "starting"))
            self.assertEqual(voice.read_pid(pid_file), 1234)

            voice.write_pid_state(1234, "recording", path=pid_file)
            self.assertEqual(voice.read_pid_state(pid_file), (1234, "recording"))
            self.assertEqual(voice.read_pid(pid_file), 1234)

            voice.write_pid_state(1234, "transcribing", path=pid_file)
            self.assertEqual(voice.read_pid_state(pid_file), (1234, "transcribing"))
            self.assertEqual(voice.read_pid(pid_file), 1234)

            pid_file.unlink()
            self.assertEqual(voice.read_pid_state(pid_file), (None, "idle"))
            self.assertIsNone(voice.read_pid(pid_file))

    def test_read_pid_backward_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pid_file = Path(tmp_dir) / "legacy.pid"
            pid_file.write_text("9876\n", encoding="utf-8")
            self.assertEqual(voice.read_pid(pid_file), 9876)
            self.assertEqual(voice.read_pid_state(pid_file), (9876, "recording"))

    def test_hardened_process_alive_cmdline_verification(self) -> None:
        pid = 4321
        with patch("os.kill") as mock_kill:
            # Case 1: Matching cmdline -> True
            with patch.object(Path, "read_bytes", return_value=b"python3\x00voice.py\x00--record-background\x00"):
                self.assertTrue(voice.process_alive(pid))
                mock_kill.assert_called_with(pid, 0)

            # Case 2: Recycled PID (e.g. bash) -> False
            with patch.object(Path, "read_bytes", return_value=b"/bin/bash\x00-i\x00"):
                self.assertFalse(voice.process_alive(pid))

            # Case 3: Empty cmdline (zombie) -> False
            with patch.object(Path, "read_bytes", return_value=b""):
                self.assertFalse(voice.process_alive(pid))

            # Case 4: FileNotFoundError reading /proc/<pid>/cmdline -> False
            with patch.object(Path, "read_bytes", side_effect=FileNotFoundError):
                self.assertFalse(voice.process_alive(pid))

        # Case 5: ProcessLookupError on os.kill -> False
        with patch("os.kill", side_effect=ProcessLookupError):
            self.assertFalse(voice.process_alive(pid))

    def test_double_tap_startup_race_wait(self) -> None:
        args = voice.parse_args([])
        pid = 5555
        states = [(pid, "starting"), (pid, "recording")]

        def fake_read_pid_state(path=voice.PID_FILE):
            return states.pop(0) if states else (pid, "recording")

        with patch("voice.read_pid_state", side_effect=fake_read_pid_state), \
             patch("voice.process_alive", return_value=True), \
             patch("os.kill") as mock_kill, \
             patch("time.sleep") as mock_sleep:
            ret = voice.toggle_background_recording(args)
            self.assertEqual(ret, 0)
            mock_kill.assert_called_once_with(pid, voice.signal.SIGUSR1)
            mock_sleep.assert_called()

    def test_busy_state_protection_error_cue(self) -> None:
        args = voice.parse_args([])
        pid = 5555
        with patch("voice.read_pid_state", return_value=(pid, "transcribing")), \
             patch("voice.process_alive", return_value=True), \
             patch("voice.play_cue") as mock_cue, \
             patch("os.kill") as mock_kill, \
             patch("subprocess.Popen") as mock_popen:
            ret = voice.toggle_background_recording(args)
            self.assertEqual(ret, 0)
            mock_cue.assert_called_once_with(args, "error")
            mock_kill.assert_not_called()
            mock_popen.assert_not_called()

    def test_signal_differentiation_usr1_vs_term(self) -> None:
        args = voice.parse_args([])
        handlers = {}

        def fake_signal(sig, handler):
            handlers[sig] = handler

        mock_recorder = MagicMock()
        mock_recorder.recording = True
        mock_recorder.started_at = None
        mock_recorder.start.side_effect = lambda: setattr(mock_recorder, "started_at", time.monotonic())
        mock_recorder.stop_to_wav.return_value = (Path("/tmp/test.wav"), 1.0, False)

        # Test cancel on SIGTERM: stops recording without transcribing or typing
        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=mock_recorder), \
             patch("voice.play_cue"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model") as mock_load, \
             patch("voice.transcribe") as mock_transcribe:

            def trigger_term():
                if voice.signal.SIGTERM in handlers:
                    handlers[voice.signal.SIGTERM](voice.signal.SIGTERM, None)

            with patch("time.sleep", side_effect=lambda _: trigger_term()):
                ret = voice.run_background_recording(args)
                self.assertEqual(ret, 0)
                mock_load.assert_not_called()
                mock_transcribe.assert_not_called()

        # Test stop on SIGUSR1: proceeds to transcribe and insert text
        handlers.clear()
        mock_recorder.recording = True
        mock_recorder.started_at = None
        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=mock_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model", return_value=MagicMock()) as mock_load, \
             patch("voice.transcribe", return_value=("Hello world", MagicMock())) as mock_transcribe, \
             patch("voice.insert_text", return_value=True) as mock_insert:

            def trigger_usr1():
                if voice.signal.SIGUSR1 in handlers:
                    handlers[voice.signal.SIGUSR1](voice.signal.SIGUSR1, None)

            with patch("time.sleep", side_effect=lambda _: trigger_usr1()):
                ret = voice.run_background_recording(args)
                self.assertEqual(ret, 0)
                mock_load.assert_called_once()
                mock_transcribe.assert_called_once()
                mock_insert.assert_called_once()

    def test_symmetric_mutex_stt_stops_tts(self) -> None:
        args = voice.parse_args([])
        with patch("voice.read_pid_state", return_value=(None, "idle")), \
             patch("voice.stop_tts") as mock_stop_tts, \
             patch("subprocess.Popen") as mock_popen, \
             patch("voice.write_pid_state"):
            mock_popen.return_value.pid = 9999
            ret = voice.toggle_background_recording(args)
            self.assertEqual(ret, 0)
            mock_stop_tts.assert_called_once_with(args, quiet=True)

    def test_symmetric_mutex_tts_stops_stt(self) -> None:
        stt_pid = 7777
        with patch("voice.read_pid_state", return_value=(stt_pid, "recording")), \
             patch("voice.process_alive", return_value=True), \
             patch("os.kill") as mock_kill, \
             patch("voice.remove_pid") as mock_remove_pid:
            voice.cancel_active_stt()
            mock_kill.assert_called_once_with(stt_pid, voice.signal.SIGTERM)
            mock_remove_pid.assert_called_once_with(stt_pid)

    def test_safety_recording_duration_ceiling_override(self) -> None:
        with patch.dict(os.environ, {"VOICE_MAX_RECORDING_SECONDS": "15.5"}):
            ceiling = voice.max_recording_seconds()
            self.assertEqual(ceiling, 15.5)

    def test_transcription_watchdog_timeout(self) -> None:
        # Verifies watchdog handler cleans up PID on timeout
        with patch("voice.remove_pid") as mock_remove, patch("os._exit") as mock_exit:
            voice.transcription_watchdog_handler(9999)
            mock_remove.assert_called_once_with(9999)
            mock_exit.assert_called_once_with(1)


class TestDesktopNotificationBehavior(unittest.TestCase):
    """Test suite covering focus-safe notification rules, urgency flags, and cue intervals."""

    def test_routine_stt_notifications_suppressed(self) -> None:
        args = voice.parse_args([])
        handlers = {}

        def fake_signal(sig, handler):
            handlers[sig] = handler

        mock_recorder = MagicMock()
        mock_recorder.recording = True
        mock_recorder.started_at = None
        mock_recorder.start.side_effect = lambda: setattr(mock_recorder, "started_at", time.monotonic())
        mock_recorder.stop_to_wav.return_value = (Path("/tmp/test.wav"), 1.0, False)

        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=mock_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model"), \
             patch("voice.transcribe", return_value=("Normal dictation text", MagicMock())), \
             patch("voice.insert_text", return_value=True), \
             patch("voice.notify") as mock_notify:

            def trigger_usr1():
                if voice.signal.SIGUSR1 in handlers:
                    handlers[voice.signal.SIGUSR1](voice.signal.SIGUSR1, None)

            with patch("time.sleep", side_effect=lambda _: trigger_usr1()):
                ret = voice.run_background_recording(args)
                self.assertEqual(ret, 0)
                # Verify routine toasts were suppressed
                mock_notify.assert_not_called()

    def test_exceptional_stt_notifications_allowed(self) -> None:
        args = voice.parse_args([])
        handlers = {}

        def fake_signal(sig, handler):
            handlers[sig] = handler

        mock_recorder = MagicMock()
        mock_recorder.recording = True
        mock_recorder.started_at = 1000.0
        mock_recorder.stop_to_wav.return_value = (Path("/tmp/test.wav"), 1.0, False)

        # 1. No speech detected -> exceptional toast
        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=mock_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model"), \
             patch("voice.transcribe", return_value=("", MagicMock())), \
             patch("voice.notify") as mock_notify:

            def trigger_usr1():
                if voice.signal.SIGUSR1 in handlers:
                    handlers[voice.signal.SIGUSR1](voice.signal.SIGUSR1, None)

            with patch("time.sleep", side_effect=lambda _: trigger_usr1()):
                voice.run_background_recording(args)
                mock_notify.assert_called_with(voice.APP_NAME, "No speech detected.", args)

        # 2. Max duration ceiling reached -> exceptional toast
        handlers.clear()
        mock_recorder.recording = True
        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=mock_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model"), \
             patch("voice.transcribe", return_value=("", MagicMock())), \
             patch("voice.max_recording_seconds", return_value=0.01), \
             patch("voice.notify") as mock_notify:
            with patch("time.monotonic", side_effect=[1000.0, 1000.0, 1000.02, 1000.02, 1000.02]):
                voice.run_background_recording(args)
                notified_messages = [call[0][1] for call in mock_notify.call_args_list]
                self.assertTrue(any("Max recording duration" in m for m in notified_messages))

    def test_tts_notification_urgency_and_timeout(self) -> None:
        args = voice.parse_args([])
        with patch("shutil.which", return_value="/usr/bin/notify-send"), \
             patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1"}), \
             patch("subprocess.run") as mock_run:
            voice.notify("Voice TTS", "Speaking selection", args, urgency="low", expire_time_ms=2000)
            mock_run.assert_called_once_with(
                ["/usr/bin/notify-send", "Voice TTS", "Speaking selection", "-u", "low", "-t", "2000"],
                check=False,
                stdin=subprocess.DEVNULL,
            )

    def test_periodic_reminder_cue_interval(self) -> None:
        args = voice.parse_args([])
        self.assertEqual(voice.recording_beep_interval(args), 5.0)
        with patch.dict(os.environ, {"VOICE_RECORDING_BEEP_INTERVAL": "2.5"}):
            self.assertEqual(voice.recording_beep_interval(args), 2.5)


if __name__ == "__main__":
    unittest.main()
