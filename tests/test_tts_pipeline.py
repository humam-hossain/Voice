"""Unit tests for voicemode Text-to-Speech (TTS) asset management and verification pipeline."""

from __future__ import annotations

import argparse
import tempfile
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
    """Placeholder test stub for Plan 03-02 text normalization."""

    def test_normalization_stub(self) -> None:
        pass


class TestWaylandSelectionCapture(unittest.TestCase):
    """Placeholder test stub for Plan 03-02 Wayland selection capture."""

    def test_selection_stub(self) -> None:
        pass


class TestAudioPlaybackAndInterruption(unittest.TestCase):
    """Placeholder test stub for Plan 03-02 audio playback and interruption."""

    def test_playback_stub(self) -> None:
        pass


if __name__ == "__main__":
    unittest.main()
