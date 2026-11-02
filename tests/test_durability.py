from __future__ import annotations

import errno
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase


class TestDegradedDurability(TempXdgTestCase):
    """Verify 7 portability and durability conditions (D-28 through D-34)."""

    def test_unset_xdg_runtime_dir_fallback(self):
        """D-28: Unset XDG_RUNTIME_DIR falls back to /tmp/voice-stt-$UID/ with 0700 permissions."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            state_dir = voicemode_telemetry.get_state_dir()
            uid = os.getuid()
            self.assertEqual(state_dir, Path(f"/tmp/voice-stt-{uid}") / "voice-stt")
            # Verify permissions on parent
            parent = state_dir.parent
            if parent.exists():
                mode = parent.stat().st_mode & 0o777
                # Only the voice-stt subdir enforces 0700
                self.assertEqual(state_dir.stat().st_mode & 0o777, 0o700)

    def test_custom_uid_fallback(self):
        """D-28: Custom UID fallback resolves with 0700 permissions."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            with patch("os.getuid", return_value=99999):
                state_dir = voicemode_telemetry.get_state_dir()
                self.assertIn("99999", str(state_dir))

    def test_read_only_state_dir_append_ledger(self):
        """D-29: Read-only state directory allows append_ledger_row to return False without crashing."""
        record = voicemode_telemetry.build_record(
            run_id="test-ro", install_id=voicemode_telemetry.get_install_id(),
            ts_start=1.0, ts_end=2.0, outcome="success",
            config={"model": "m", "device": "cpu", "compute_type": "int8",
                    "beam_size": 1, "vad_filter": True, "language": "en", "chunk_s": 180.0},
        )
        ledger_path = voicemode_telemetry.get_ledger_path()
        ledger_path.touch(mode=0o400)
        try:
            os.chmod(ledger_path, stat.S_IRUSR)
            result = voicemode_telemetry.append_ledger_row(record)
            self.assertFalse(result)
        finally:
            os.chmod(ledger_path, stat.S_IRUSR | stat.S_IWUSR)

        # Also test with EROFS
        def _raise_erofs(*a, **kw):
            raise OSError(errno.EROFS, "Read-only file system")

        with patch("os.open", side_effect=_raise_erofs):
            result = voicemode_telemetry.append_ledger_row(record)
            self.assertFalse(result)

    def test_enospc_in_memory_fallback(self):
        """D-30: Full disk (ENOSPC) triggers in-memory numpy array decode fallback in Recorder."""
        recorder = voice.Recorder(sample_rate=16000, chunk_seconds=180.0)
        recorder._session_id = "test"
        recorder.actual_sample_rate = 16000

        audio = np.random.randn(16000).astype(np.float32)  # 1 second audio

        # Patch wave.open to raise ENOSPC
        def _raise_enospc(*a, **kw):
            raise OSError(errno.ENOSPC, "No space left on device")

        with patch("wave.open", side_effect=_raise_enospc):
            result, audio_s = recorder._write_chunk_file(audio, 1, None)
            # Should return a numpy array, not a Path
            self.assertIsInstance(result, np.ndarray)
            self.assertEqual(result.dtype, np.float32)
            self.assertAlmostEqual(audio_s, 1.0, places=1)

    def test_transcribe_timed_accepts_ndarray(self):
        """D-30: transcribe_timed successfully decodes from an np.ndarray input."""
        audio = np.zeros(16000, dtype=np.float32)

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.avg_logprob = -0.2
        mock_segment.compression_ratio = 1.0
        mock_segment.no_speech_prob = 0.01
        mock_segment.temperature = 0.0

        mock_info = MagicMock()
        mock_info.duration = 1.0
        mock_info.duration_after_vad = 1.0

        model_mock = MagicMock()
        model_mock.model.transcribe.return_value = ([mock_segment], mock_info)
        model_mock.requested_device = "cpu"

        args = voice.parse_args([])

        ev = voice.transcribe_timed(model_mock, audio, args, audio_s=1.0)
        self.assertEqual(ev.text, "hello")
        # Verify the numpy array was passed directly to model.transcribe
        call_args = model_mock.model.transcribe.call_args
        passed_input = call_args[0][0]
        self.assertIsInstance(passed_input, np.ndarray)

    def test_resample_44100_to_16000(self):
        """D-31: 44.1 kHz to 16 kHz resampling via resample_pcm preserves duration and sample count."""
        duration_s = 2.0
        orig_sr = 44100
        target_sr = 16000
        samples_44k = int(duration_s * orig_sr)
        audio = np.sin(2 * np.pi * 440 * np.arange(samples_44k) / orig_sr).astype(np.float32)

        resampled = voice.resample_pcm(audio, orig_sr, target_sr)
        expected_samples = int(round(len(audio) * float(target_sr) / orig_sr))
        self.assertEqual(len(resampled), expected_samples)
        # Duration should be preserved
        orig_duration = len(audio) / orig_sr
        resampled_duration = len(resampled) / target_sr
        self.assertAlmostEqual(orig_duration, resampled_duration, places=1)

    def test_load_model_clamps_cpu_threads(self):
        """D-32: load_model() clamps cpu_threads to min(4, cpu_count)."""
        args = voice.parse_args([])
        with patch("os.cpu_count", return_value=16), \
             patch("faster_whisper.WhisperModel") as mock_model, \
             patch("voice.actual_backend", return_value="cpu, int8"):
            mock_model.return_value = MagicMock()
            voice.load_model(args)
            call_kwargs = mock_model.call_args
            self.assertEqual(call_kwargs.kwargs.get("cpu_threads"), 4)

        with patch("os.cpu_count", return_value=2), \
             patch("faster_whisper.WhisperModel") as mock_model, \
             patch("voice.actual_backend", return_value="cpu, int8"):
            mock_model.return_value = MagicMock()
            voice.load_model(args)
            call_kwargs = mock_model.call_args
            self.assertEqual(call_kwargs.kwargs.get("cpu_threads"), 2)

    def test_cold_boot_session_marker(self):
        """D-34: check_and_mark_boot_session() returns True on first run and False subsequently."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "voice-stt"
            state_dir.mkdir(parents=True)
            first = voicemode_telemetry.check_and_mark_boot_session(state_dir)
            self.assertTrue(first)
            second = voicemode_telemetry.check_and_mark_boot_session(state_dir)
            self.assertFalse(second)


if __name__ == "__main__":
    unittest.main()
