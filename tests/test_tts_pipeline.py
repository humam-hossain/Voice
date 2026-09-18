"""Unit tests for voicemode Text-to-Speech (TTS) asset management and verification pipeline."""

from __future__ import annotations

import argparse
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice


class TestKokoroAssetManagement(unittest.TestCase):
    """Test suite for Kokoro model asset download, verification, speed clamping, and offline privacy."""

    def test_speed_clamping(self) -> None:
        """Verify speed clamping to [0.5, 2.0] per D-14."""
        self.assertEqual(voice.clamp_tts_speed(0.1), 0.5)
        self.assertEqual(voice.clamp_tts_speed(0.49), 0.5)
        self.assertEqual(voice.clamp_tts_speed(0.5), 0.5)
        self.assertEqual(voice.clamp_tts_speed(1.2), 1.2)
        self.assertEqual(voice.clamp_tts_speed(2.0), 2.0)
        self.assertEqual(voice.clamp_tts_speed(2.5), 2.0)
        self.assertEqual(voice.clamp_tts_speed(5.0), 2.0)

    def test_default_voice_and_speed(self) -> None:
        """Verify default voice is af_heart, secondary is bm_george, speed is 1.2, and trim is False."""
        self.assertEqual(voice.DEFAULT_KOKORO_VOICE, "af_heart")
        self.assertEqual(voice.SECONDARY_KOKORO_VOICE, "bm_george")
        self.assertEqual(voice.DEFAULT_TTS_SPEED, 1.2)

        # Verify parser defaults
        with patch.dict("os.environ", {}, clear=True), patch("sys.argv", ["voice"]):
            args = voice.parse_args()
            self.assertEqual(args.tts_voice, "af_heart")
            self.assertEqual(args.tts_speed, 1.2)
            self.assertFalse(args.kokoro_trim)

    def test_download_asset_streaming_and_atomic_replace(self) -> None:
        """Verify streaming download to .tmp file, size guard passing, and atomic replacement."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = Path(tmp_dir) / "test-model.onnx"
            min_size = 1000

            fake_data = b"X" * 1500
            fake_response = MagicMock()
            fake_response.headers.get.return_value = str(len(fake_data))
            # Return chunks of 500 bytes
            fake_response.read.side_effect = [fake_data[:500], fake_data[500:1000], fake_data[1000:], b""]
            fake_response.__enter__.return_value = fake_response

            with patch("urllib.request.urlopen", return_value=fake_response) as mock_urlopen:
                voice.download_file_with_progress(
                    url="https://example.com/model.onnx",
                    dest_path=dest,
                    min_size=min_size,
                    label="Test Model",
                )

                mock_urlopen.assert_called_once()
                self.assertTrue(dest.is_file())
                self.assertEqual(dest.stat().st_size, len(fake_data))
                # .tmp file must not remain
                self.assertFalse(dest.with_suffix(".tmp").exists())

    def test_download_asset_size_guard_failure(self) -> None:
        """Verify download undersized bytes raises RuntimeError and cleans up .tmp file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = Path(tmp_dir) / "test-model.onnx"
            min_size = 300_000_000

            # Only provide 100 bytes
            fake_data = b"small_payload"
            fake_response = MagicMock()
            fake_response.headers.get.return_value = str(len(fake_data))
            fake_response.read.side_effect = [fake_data, b""]
            fake_response.__enter__.return_value = fake_response

            with patch("urllib.request.urlopen", return_value=fake_response):
                with self.assertRaises(RuntimeError) as ctx:
                    voice.download_file_with_progress(
                        url="https://example.com/model.onnx",
                        dest_path=dest,
                        min_size=min_size,
                        label="Kokoro Model",
                    )
                self.assertIn("undersized", str(ctx.exception).lower())
                self.assertFalse(dest.exists())
                self.assertFalse(dest.with_suffix(".tmp").exists())

    def test_offline_first_guard_no_cloud_fallback(self) -> None:
        """Verify synthesize_tts strictly rejects missing Kokoro assets without falling back to cloud."""
        args = argparse.Namespace(
            tts_backend="kokoro",
            tts_voice="af_heart",
            tts_speed=1.2,
            kokoro_lang="en-us",
            kokoro_trim=False,
            kokoro_model=Path("/nonexistent/model.onnx"),
            kokoro_voices=Path("/nonexistent/voices.bin"),
            beep=True,
            notify=True,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "output.wav"
            with patch("voice.synthesize_edge_tts") as mock_edge, \
                 patch("voice.notify") as mock_notify, \
                 patch("voice.play_cue") as mock_cue:
                with self.assertRaises(RuntimeError) as ctx:
                    voice.synthesize_tts("Hello world", out_path, args)

                mock_edge.assert_not_called()
                mock_cue.assert_called_with(args, "error")
                mock_notify.assert_called()
                self.assertIn("download-tts-assets", str(ctx.exception).lower())

    def test_print_tts_check_exit_code_contract(self) -> None:
        """Verify print_tts_check exit code 1 when assets are missing/invalid, and 0 on success."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            missing_model = tmp_path / "missing.onnx"
            missing_voices = tmp_path / "missing.bin"

            args = argparse.Namespace(
                tts_backend="kokoro",
                tts_voice="af_heart",
                tts_speed=1.2,
                kokoro_lang="en-us",
                kokoro_trim=False,
                kokoro_model=missing_model,
                kokoro_voices=missing_voices,
            )

            # Missing assets must return exit code 1
            code = voice.print_tts_check(args)
            self.assertEqual(code, 1)

            # Undersized files must return exit code 1
            undersized_model = tmp_path / "model.onnx"
            undersized_voices = tmp_path / "voices.bin"
            undersized_model.write_bytes(b"small")
            undersized_voices.write_bytes(b"small")

            args.kokoro_model = undersized_model
            args.kokoro_voices = undersized_voices
            code = voice.print_tts_check(args)
            self.assertEqual(code, 1)

            # Valid files with Kokoro instantiation returning voices
            valid_model = tmp_path / "valid_model.onnx"
            valid_voices = tmp_path / "valid_voices.bin"
            # Create dummy files passing size guards
            with open(valid_model, "wb") as f:
                f.seek(300_000_001)
                f.write(b"\0")
            with open(valid_voices, "wb") as f:
                f.seek(20_000_001)
                f.write(b"\0")

            args.kokoro_model = valid_model
            args.kokoro_voices = valid_voices

            mock_kokoro = MagicMock()
            mock_kokoro.get_voices.return_value = ["af_heart", "bm_george"]
            with patch("kokoro_onnx.Kokoro", return_value=mock_kokoro):
                code = voice.print_tts_check(args)
                self.assertEqual(code, 0)


class TestTtsTextNormalization(unittest.TestCase):
    """Test suite for conservative text normalization, length bounding, and stdin piping."""

    def test_ansi_escape_stripping(self) -> None:
        raw = "\x1B[31mRed Alert\x1B[0m: status \x1B[1mCRITICAL\x1B[22m"
        self.assertEqual(voice.normalize_tts_text(raw), "Red Alert: status CRITICAL")

    def test_markdown_links(self) -> None:
        raw = "Read the [official docs](https://github.com/thewh1teagle/kokoro-onnx) for details."
        self.assertEqual(voice.normalize_tts_text(raw), "Read the official docs for details.")

    def test_raw_urls_to_domains(self) -> None:
        raw = "Check https://github.com/thewh1teagle/kokoro-onnx/releases and http://example.org/test."
        self.assertEqual(voice.normalize_tts_text(raw), "Check github.com and example.org.")

    def test_code_snake_case_conversion(self) -> None:
        raw = "Run `download_file_with_progress` and check `tts_speed`."
        self.assertEqual(
            voice.normalize_tts_text(raw),
            "Run download file with progress and check tts speed.",
        )

    def test_markdown_formatting_removal(self) -> None:
        raw = (
            "# Main Heading\n\n"
            "```python\nprint('hello')\n```\n\n"
            "> A blockquote\n\n"
            "- First item\n"
            "* Second item\n\n"
            "Here is **bold** text and *italic* text."
        )
        normalized = voice.normalize_tts_text(raw)
        self.assertNotIn("#", normalized)
        self.assertNotIn("```", normalized)
        self.assertNotIn(">", normalized)
        self.assertNotIn("*", normalized)
        self.assertIn("Main Heading. print('hello') A blockquote. First item. Second item. Here is bold text and italic text.", normalized)

    def test_path_slashes_to_pauses(self) -> None:
        raw = "Inspect /home/user/Voice/models/kokoro/voices.bin today."
        normalized = voice.normalize_tts_text(raw)
        self.assertEqual(
            normalized,
            "Inspect home, user, Voice, models, kokoro, voices.bin today.",
        )

    def test_smart_line_pauses(self) -> None:
        raw = "First line without punctuation\nSecond line\nThird line."
        normalized = voice.normalize_tts_text(raw)
        self.assertEqual(normalized, "First line without punctuation. Second line. Third line.")

    def test_unicode_punctuation(self) -> None:
        raw = "Speech—offline–fast with ‘smart’ quotes and “double” quotes."
        normalized = voice.normalize_tts_text(raw)
        self.assertEqual(
            normalized,
            'Speech, offline, fast with \'smart\' quotes and "double" quotes.',
        )

    def test_length_bounding_and_warning_toast(self) -> None:
        args = argparse.Namespace(notify=True)
        short_text = "A" * 100
        bounded, truncated = voice.bound_tts_text(short_text, args)
        self.assertFalse(truncated)
        self.assertEqual(len(bounded), 100)

        long_text = "B" * 6000
        with patch("voice.notify") as mock_notify:
            bounded, truncated = voice.bound_tts_text(long_text, args)
            self.assertTrue(truncated)
            self.assertEqual(len(bounded), 5000)
            mock_notify.assert_called_once()
            self.assertIn("truncated", mock_notify.call_args[0][1].lower())

    def test_empty_text_upfront_abort(self) -> None:
        args = argparse.Namespace(
            notify=True,
            beep=True,
            tts_backend="kokoro",
            tts_voice="af_heart",
            tts_speed=1.2,
        )
        with patch("voice.notify") as mock_notify, \
             patch("voice.play_cue") as mock_cue, \
             patch("subprocess.Popen") as mock_popen:
            code = voice.start_tts_background("   \n\t  ", args)
            self.assertEqual(code, 1)
            mock_notify.assert_called_with("Voice TTS", "No text to speak.", args)
            mock_cue.assert_called_with(args, "error")
            mock_popen.assert_not_called()

    def test_stdin_piping(self) -> None:
        import io

        args = argparse.Namespace(
            speak="-",
            tts_backend="kokoro",
            tts_voice="af_heart",
            tts_speed=1.2,
            notify=True,
            beep=True,
            download_tts_assets=False,
            list_tts_voices=False,
            tts_check=False,
            tts_background=False,
            stop_tts=False,
            speak_selection=False,
            test_beep=False,
            list_devices=False,
            install_hotkey=False,
            install_hotkeys=False,
            status=False,
            toggle=False,
            record_background=False,
            check=False,
            terminal=False,
        )
        with patch("voice.parse_args", return_value=args), \
             patch("sys.stdin", io.StringIO("Piped text from stdin")), \
             patch("voice.start_tts_background", return_value=0) as mock_start:
            code = voice.main()
            self.assertEqual(code, 0)
            mock_start.assert_called_once_with("Piped text from stdin", args, source="stdin")


class TestWaylandSelectionCapture(unittest.TestCase):
    """Test suite for Wayland primary selection capture, timeout, fallback, and error handling."""

    def test_primary_prioritized_over_clipboard(self) -> None:
        with patch("voice.read_x_selection") as mock_read:
            mock_read.side_effect = lambda sel: "primary text" if sel == "primary" else "clipboard text"
            text, source = voice.selected_or_clipboard_text()
            self.assertEqual(text, "primary text")
            self.assertEqual(source, "selection")

    def test_fallback_to_clipboard_when_primary_empty(self) -> None:
        with patch("voice.read_x_selection") as mock_read:
            mock_read.side_effect = lambda sel: "" if sel == "primary" else "clipboard text"
            text, source = voice.selected_or_clipboard_text()
            self.assertEqual(text, "clipboard text")
            self.assertEqual(source, "clipboard")

    def test_timeout_on_unresponsive_wayland_client(self) -> None:
        import subprocess

        with patch("voice.display_server", return_value="wayland"), \
             patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-1"}), \
             patch("shutil.which", return_value="/usr/bin/wl-paste"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["wl-paste"], timeout=1.0)):
            result = voice.read_x_selection("primary")
            self.assertEqual(result, "")

    def test_empty_selection_error_chime_and_notification(self) -> None:
        args = argparse.Namespace(notify=True, beep=True, tts_backend="kokoro")
        with patch("voice.read_pid", return_value=None), \
             patch("voice.selected_or_clipboard_text", return_value=("", "")), \
             patch("voice.notify") as mock_notify, \
             patch("voice.play_cue") as mock_cue, \
             patch("voice.start_tts_background") as mock_start:
            code = voice.speak_selection(args)
            self.assertEqual(code, 1)
            mock_notify.assert_called_with("Voice TTS", "No selected text or clipboard text.", args)
            mock_cue.assert_called_with(args, "error")
            mock_start.assert_not_called()

    def test_toast_distinguishes_source(self) -> None:
        args = argparse.Namespace(
            notify=True,
            beep=True,
            tts_backend="kokoro",
            tts_voice="af_heart",
            tts_speed=1.2,
            kokoro_model=Path("models/kokoro/kokoro-v1.0.onnx"),
            kokoro_voices=Path("models/kokoro/voices-v1.0.bin"),
        )
        # Test primary source
        with patch("voice.read_pid", return_value=None), \
             patch("voice.selected_or_clipboard_text", return_value=("Sample primary text", "selection")), \
             patch("voice.start_tts_background", return_value=0), \
             patch("voice.notify") as mock_notify:
            voice.speak_selection(args)
            mock_notify.assert_called_with("Voice TTS", 'Speaking selection: "Sample primary text"', args)

        # Test clipboard fallback source
        with patch("voice.read_pid", return_value=None), \
             patch("voice.selected_or_clipboard_text", return_value=("Sample clipboard text", "clipboard")), \
             patch("voice.start_tts_background", return_value=0), \
             patch("voice.notify") as mock_notify:
            voice.speak_selection(args)
            mock_notify.assert_called_with("Voice TTS", 'Speaking clipboard (fallback): "Sample clipboard text"', args)

    def test_toggle_behavior(self) -> None:
        args = argparse.Namespace(notify=True, beep=True)
        with patch("voice.read_pid", return_value=12345), \
             patch("voice.process_alive", return_value=True), \
             patch("voice.stop_tts", return_value=True) as mock_stop:
            code = voice.speak_selection(args)
            self.assertEqual(code, 0)
            mock_stop.assert_called_once_with(args)


class TestAudioPlaybackAndInterruption(unittest.TestCase):
    """Test suite for PipeWire stream tagging, interruption filtering, and temp GC."""

    def test_pipewire_stream_tagging(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/ffplay"), \
             patch("subprocess.run") as mock_run:
            voice.play_tts_audio(Path("/tmp/test.wav"))
            mock_run.assert_called_once()
            call_env = mock_run.call_args[1].get("env", {})
            self.assertEqual(call_env.get("PULSE_PROP_application.name"), "voicemode")
            self.assertEqual(call_env.get("PULSE_PROP_media.name"), "voicemode-tts")

    def test_clean_interruption_filter(self) -> None:
        import subprocess

        with patch("shutil.which", return_value="/usr/bin/ffplay"):
            for sig in (-15, -2, 255, 143, 130):
                with (
                    patch("subprocess.run", side_effect=subprocess.CalledProcessError(returncode=sig, cmd="ffplay")),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    voice.play_tts_audio(Path("/tmp/test.wav"))

            # Non-interruption error should re-raise CalledProcessError
            with (
                patch("subprocess.run", side_effect=subprocess.CalledProcessError(returncode=1, cmd="ffplay")),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                voice.play_tts_audio(Path("/tmp/test.wav"))

    def test_stop_tts_terminates_process_group_and_notifies(self) -> None:
        import signal

        args = argparse.Namespace(notify=True)
        with patch("voice.read_pid", return_value=9999), \
             patch("voice.process_alive", return_value=True), \
             patch("os.killpg") as mock_killpg, \
             patch("voice.remove_pid") as mock_remove_pid, \
             patch("voice.notify") as mock_notify, \
             patch("voice.cleanup_stale_tts_files"):
            stopped = voice.stop_tts(args)
            self.assertTrue(stopped)
            mock_killpg.assert_called_once_with(9999, signal.SIGTERM)
            mock_remove_pid.assert_called_once_with(9999, voice.TTS_PID_FILE)
            mock_notify.assert_called_with("Voice TTS", "Speech stopped.", args)

    def test_cleanup_stale_tts_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch("voice.STATE_DIR", tmp_path):
                old_wav = tmp_path / "voice-tts-old.wav"
                new_wav = tmp_path / "voice-tts-new.wav"
                old_txt = tmp_path / "voice-tts-old.txt"
                other_file = tmp_path / "keep_me.txt"

                old_wav.write_text("old")
                new_wav.write_text("new")
                old_txt.write_text("old text")
                other_file.write_text("unrelated")

                # Backdate old files by 3600 seconds (1 hour)
                old_time = time.time() - 3600
                os.utime(old_wav, (old_time, old_time))
                os.utime(old_txt, (old_time, old_time))

                removed = voice.cleanup_stale_tts_files(max_age_seconds=1800)
                self.assertEqual(removed, 2)
                self.assertFalse(old_wav.exists())
                self.assertFalse(old_txt.exists())
                self.assertTrue(new_wav.exists())
                self.assertTrue(other_file.exists())


if __name__ == "__main__":
    unittest.main()
