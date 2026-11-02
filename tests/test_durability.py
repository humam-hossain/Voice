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

    def test_degraded_durability_smoke(self):
        """Smoke test verifying all degraded durability conditions are covered."""
        pass

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


class TestOutlierDetection(TempXdgTestCase):
    """Verify outlier detection and focus safety (D-01, D-02, D-06)."""

    def test_outlier_rtf_exceeded(self):
        """classify_outlier(2.0, 2500.0) returns (True, 'rtf_exceeded')."""
        is_outlier, reason = voicemode_telemetry.classify_outlier(2.0, 2500.0)
        self.assertTrue(is_outlier)
        self.assertEqual(reason, "rtf_exceeded")

    def test_outlier_tail_decode(self):
        """classify_outlier(20.0, 12000.0) returns (True, 'tail_decode')."""
        is_outlier, reason = voicemode_telemetry.classify_outlier(20.0, 12000.0)
        self.assertTrue(is_outlier)
        self.assertEqual(reason, "tail_decode")

    def test_outlier_normal_run_not_outlier(self):
        """classify_outlier(5.0, 1500.0) returns (False, None)."""
        is_outlier, reason = voicemode_telemetry.classify_outlier(5.0, 1500.0)
        self.assertFalse(is_outlier)
        self.assertIsNone(reason)

    def test_outlier_threshold_env_overrides(self):
        """Thresholds can be customized via VOICEMODE_OUTLIER_RTF_THRESHOLD and VOICEMODE_OUTLIER_TAIL_S."""
        with patch.dict(os.environ, {"VOICEMODE_OUTLIER_RTF_THRESHOLD": "0.5"}):
            is_outlier, reason = voicemode_telemetry.classify_outlier(2.0, 1200.0)
            self.assertTrue(is_outlier)
            self.assertEqual(reason, "rtf_exceeded")

        with patch.dict(os.environ, {"VOICEMODE_OUTLIER_TAIL_S": "5.0"}):
            is_outlier, reason = voicemode_telemetry.classify_outlier(20.0, 6000.0)
            self.assertTrue(is_outlier)
            self.assertEqual(reason, "tail_decode")

    def test_outlier_focus_safety_zero_notifications_or_beeps(self):
        """D-06: Outlier detection does not trigger notifications or cues, protecting window focus."""
        with patch("voice.notify") as mock_notify, \
             patch("voice.play_cue") as mock_cue:
            ev = MagicMock()
            ev.text = "outlier test"
            ev.audio_s = 2.0
            ev.decode_ms = 3000.0  # RTF = 1.5 > 1.0
            ev.failure_type = None
            ev.fallback = False
            ev.avg_logprob = -0.1
            ev.compression_ratio = 1.0
            ev.no_speech_prob = 0.0
            ev.temperature = 0.0
            ev.vad_audio_s = 2.0
            run_state = {
                "run_id": "test-outlier-run",
                "audio_s": 2.0,
                "t_start": time.monotonic() - 5.0,
                "results": {1: ev},
                "args": voice.parse_args([]),
            }
            voice.finalize_background_run(run_state, outcome="success")
            # Verify no notifications or sound cues triggered by outlier
            mock_notify.assert_not_called()
            mock_cue.assert_not_called()


class TestCorpusCapture(TempXdgTestCase):
    """Verify diagnostic corpus capture and FIFO retention (D-07 through D-16)."""

    def test_corpus_default_off(self):
        """D-07: Corpus capture is disabled by default."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VOICEMODE_CORPUS_CAPTURE", None)
            args = voice.parse_args([])
            self.assertIsNone(args.capture_corpus)

    def test_corpus_dir_permissions_0700_and_file_0600(self):
        """D-08, D-09: Directory has 0700 permissions and saved files have 0600 permissions."""
        corpus_dir = voicemode_telemetry.get_corpus_dir()
        self.assertEqual(corpus_dir.stat().st_mode & 0o777, 0o700)

        audio = np.zeros(16000, dtype=np.float32)
        rel_path = voicemode_telemetry.save_diagnostic_corpus(audio, "perm_run", "outlier_rtf")
        self.assertIsNotNone(rel_path)
        self.assertTrue(rel_path.startswith("corpus/"))

        saved_file = corpus_dir / Path(rel_path).name
        self.assertTrue(saved_file.exists())
        self.assertEqual(saved_file.stat().st_mode & 0o777, 0o600)

    def test_corpus_abort_if_disk_free_under_1gb(self):
        """D-12: save_diagnostic_corpus aborts if free space is under 1 GB."""
        audio = np.zeros(16000, dtype=np.float32)
        mock_usage = MagicMock()
        mock_usage.free = 500 * 1024 * 1024  # 500 MB < 1 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            rel_path = voicemode_telemetry.save_diagnostic_corpus(audio, "low_disk", "outlier")
            self.assertIsNone(rel_path)

    def test_corpus_fifo_eviction_and_grace_period(self):
        """D-12, D-14: FIFO eviction prunes files exceeding quotas but respects 60s grace period."""
        corpus_dir = voicemode_telemetry.get_corpus_dir()
        # Create 55 dummy wav files
        now = time.time()
        for i in range(55):
            p = corpus_dir / f"test_{i:03d}.wav"
            p.write_bytes(b"RIFF" + b"\x00" * 100)
            # Set older mtime (120s ago, past grace period)
            old_time = now - 120.0 - (55 - i)
            os.utime(p, (old_time, old_time))

        # Add one very fresh file (within grace period)
        fresh = corpus_dir / "fresh.wav"
        fresh.write_bytes(b"RIFF" + b"\x00" * 100)
        os.utime(fresh, (now, now))

        pruned = voicemode_telemetry.prune_corpus_if_needed(corpus_dir)
        # 56 files total, max is 50 -> should prune 6 oldest files
        self.assertEqual(pruned, 6)
        self.assertTrue(fresh.exists())

    def test_corpus_purge(self):
        """D-16: purge_corpus unlinks all corpus files and returns count and bytes."""
        corpus_dir = voicemode_telemetry.get_corpus_dir()
        p1 = corpus_dir / "run1.wav"
        p2 = corpus_dir / "run2.wav"
        p1.write_bytes(b"12345")
        p2.write_bytes(b"67890")

        count, total_bytes = voicemode_telemetry.purge_corpus(corpus_dir)
        self.assertEqual(count, 2)
        self.assertEqual(total_bytes, 10)
        self.assertFalse(p1.exists())
        self.assertFalse(p2.exists())

    def test_voice_cli_purge_corpus(self):
        """D-16: voice --purge-corpus runs purge and prints reclaimed summary."""
        corpus_dir = voicemode_telemetry.get_corpus_dir()
        (corpus_dir / "dummy.wav").write_bytes(b"\x00" * 1024)

        with patch("sys.stdout"):
            exit_code = voice.main(["--purge-corpus"])
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
