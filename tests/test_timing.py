from __future__ import annotations

import argparse
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
from _hermetic import TempXdgTestCase


class DummySegment:
    def __init__(self, text: str, avg_logprob: float, compression_ratio: float, no_speech_prob: float, temperature: float):
        self.text = text
        self.avg_logprob = avg_logprob
        self.compression_ratio = compression_ratio
        self.no_speech_prob = no_speech_prob
        self.temperature = temperature


class DummyInfo:
    def __init__(self, duration: float, duration_after_vad: float):
        self.duration = duration
        self.duration_after_vad = duration_after_vad


class TestTiming(TempXdgTestCase):
    def test_generator_consumption_timing(self) -> None:
        """Verify decode_ms covers lazy generator evaluation (sleeping generator)."""
        args = voice.parse_args([])
        wav_path = Path("/tmp/dummy.wav")

        def sleeping_generator():
            for i in range(3):
                time.sleep(0.02)
                yield DummySegment(f"segment {i}", -0.2, 1.1, 0.01, 0.0)

        mock_whisper = MagicMock()
        mock_whisper.transcribe.return_value = (sleeping_generator(), DummyInfo(1.0, 1.0))
        model_state = voice.ModelState(model=mock_whisper, requested_device="cpu", requested_compute_type="int8")

        ev = voice.transcribe_timed(model_state, wav_path, args)
        self.assertEqual(ev.text, "segment 0 segment 1 segment 2")
        self.assertEqual(ev.decoder_segments, 3)
        self.assertGreaterEqual(ev.decode_ms, 50.0)

    def test_evidence_aggregation_and_privacy(self) -> None:
        """Verify min/max aggregation across segments and that text never leaks into evidence metrics."""
        args = voice.parse_args([])
        wav_path = Path("/tmp/dummy.wav")
        secret_text = "super_secret_transcript_password"

        segments = [
            DummySegment(secret_text, -0.15, 1.2, 0.05, 0.0),
            DummySegment("second part", -0.45, 1.8, 0.01, 0.2),
        ]
        info = DummyInfo(duration=5.0, duration_after_vad=4.2)
        mock_whisper = MagicMock()
        mock_whisper.transcribe.return_value = (iter(segments), info)
        mock_whisper.model.device = "cuda"
        mock_whisper.model.device_index = 0
        mock_whisper.model.compute_type = "float16"

        model_state = voice.ModelState(model=mock_whisper, requested_device="cuda", requested_compute_type="float16")
        ev = voice.transcribe_timed(model_state, wav_path, args, audio_s=5.0)

        self.assertEqual(ev.text, f"{secret_text} second part")
        self.assertEqual(ev.avg_logprob, -0.45)
        self.assertEqual(ev.compression_ratio, 1.8)
        self.assertEqual(ev.no_speech_prob, 0.05)
        self.assertEqual(ev.temperature, 0.2)
        self.assertEqual(ev.vad_audio_s, 4.2)
        self.assertEqual(ev.decoder_segments, 2)
        self.assertEqual(ev.audio_s, 5.0)
        self.assertEqual(ev.backend, "cuda 0, float16")

        evidence_dict = {
            "fallback": ev.fallback,
            "failure_type": ev.failure_type,
            "backend": ev.backend,
            "avg_logprob": ev.avg_logprob,
            "compression_ratio": ev.compression_ratio,
            "no_speech_prob": ev.no_speech_prob,
            "temperature": ev.temperature,
            "vad_audio_s": ev.vad_audio_s,
            "decoder_segments": ev.decoder_segments,
            "fallback_load_ms": ev.fallback_load_ms,
            "audio_s": ev.audio_s,
        }
        for k, v in evidence_dict.items():
            self.assertNotIn(secret_text, str(v), f"Leaked text in field {k}")

    def test_fallback_path_instrumentation(self) -> None:
        """When requested_device is not CPU and transcribe fails, retry on CPU int8 and measure fallback_load_ms."""
        args = voice.parse_args([])
        wav_path = Path("/tmp/dummy.wav")

        gpu_whisper = MagicMock()
        gpu_whisper.transcribe.side_effect = RuntimeError("CUDA out of memory")
        gpu_state = voice.ModelState(model=gpu_whisper, requested_device="cuda", requested_compute_type="float16")

        cpu_whisper = MagicMock()
        cpu_segments = [DummySegment("recovered on cpu", -0.1, 1.0, 0.01, 0.0)]
        cpu_whisper.transcribe.return_value = (iter(cpu_segments), DummyInfo(2.0, 2.0))
        cpu_whisper.model.device = "cpu"
        cpu_whisper.model.device_index = ""
        cpu_whisper.model.compute_type = "int8"
        cpu_state = voice.ModelState(model=cpu_whisper, requested_device="cpu", requested_compute_type="int8")

        def mock_load(args_in, force_cpu=False):
            time.sleep(0.01)
            return cpu_state

        with patch("voice.load_model", side_effect=mock_load):
            ev = voice.transcribe_timed(gpu_state, wav_path, args)

        self.assertTrue(ev.fallback)
        self.assertEqual(ev.failure_type, "RuntimeError")
        self.assertEqual(ev.text, "recovered on cpu")
        self.assertIsNotNone(ev.fallback_load_ms)
        self.assertGreaterEqual(ev.fallback_load_ms, 5.0)
        self.assertEqual(ev.backend, "cpu, int8")

    def test_cpu_failure_reraises_without_loop(self) -> None:
        """When requested_device is already CPU, transcription failure immediately re-raises."""
        args = voice.parse_args([])
        wav_path = Path("/tmp/dummy.wav")

        cpu_whisper = MagicMock()
        cpu_whisper.transcribe.side_effect = ValueError("Corrupt WAV header")
        cpu_state = voice.ModelState(model=cpu_whisper, requested_device="cpu", requested_compute_type="int8")

        with patch("voice.load_model") as mock_load:
            with self.assertRaises(ValueError):
                voice.transcribe_timed(cpu_state, wav_path, args)
            mock_load.assert_not_called()

    def test_clock_domains(self) -> None:
        """Verify decode_ms and durations use monotonic time domain while timestamps use epoch time."""
        args = voice.parse_args([])
        wav_path = Path("/tmp/dummy.wav")

        segments = [DummySegment("test", -0.1, 1.0, 0.0, 0.0)]
        mock_whisper = MagicMock()
        mock_whisper.transcribe.return_value = (iter(segments), DummyInfo(1.0, 1.0))
        model_state = voice.ModelState(model=mock_whisper, requested_device="cpu", requested_compute_type="int8")

        t_mono_before = time.monotonic()
        t_epoch_before = time.time()
        ev = voice.transcribe_timed(model_state, wav_path, args)
        t_mono_after = time.monotonic()
        t_epoch_after = time.time()

        max_possible_ms = (t_mono_after - t_mono_before) * 1000.0 + 5.0
        self.assertLessEqual(ev.decode_ms, max_possible_ms)
        self.assertGreaterEqual(t_epoch_after, t_epoch_before)


if __name__ == "__main__":
    unittest.main()
