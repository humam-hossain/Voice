from __future__ import annotations

import os
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

import voice


class TestAudioChunking(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_chunk_seconds_resolution(self) -> None:
        # Default
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(voice.chunk_seconds(), 180.0)

        # Environment variable
        with patch.dict(os.environ, {"VOICE_CHUNK_SECONDS": "90.0"}):
            self.assertEqual(voice.chunk_seconds(), 90.0)

        # CLI args override
        args = voice.parse_args(["--chunk-seconds", "45.0"])
        self.assertEqual(voice.chunk_seconds(args), 45.0)

        # Invalid env var fallback
        with patch.dict(os.environ, {"VOICE_CHUNK_SECONDS": "invalid"}):
            self.assertEqual(voice.chunk_seconds(), 180.0)

    def test_recorder_single_chunk_under_threshold(self) -> None:
        # 16 kHz sample rate, 1 second chunk duration = 16,000 samples per chunk
        recorder = voice.Recorder(sample_rate=16000, chunk_seconds=1.0)
        recorder.started_at = time.monotonic()
        recorder.stream = MagicMock()

        # Simulate 8,000 samples (< 16,000 threshold)
        frames = np.zeros((8000, 1), dtype=np.float32)
        recorder._callback(frames, 8000, None, None)

        paths, _duration, should_delete = recorder.stop_to_wav(self.test_dir)
        try:
            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].exists())
            self.assertFalse(should_delete)

            with wave.open(str(paths[0]), "rb") as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getsampwidth(), 2)
                self.assertEqual(wf.getframerate(), 16000)
                self.assertEqual(wf.getnframes(), 8000)
        finally:
            for p in paths:
                p.unlink(missing_ok=True)

    def test_recorder_gapless_multiple_chunks(self) -> None:
        # 16 kHz, 0.1 second chunk = 1,600 samples per chunk
        recorder = voice.Recorder(sample_rate=16000, chunk_seconds=0.1, save_dir=self.test_dir)
        recorder.started_at = time.monotonic()
        recorder.stream = MagicMock()

        # Deliver 3,600 samples in blocks of 400 (9 blocks total -> 2 full chunks of 1600, plus 400 remaining)
        block = np.full((400, 1), 0.1, dtype=np.float32)
        for _ in range(9):
            recorder._callback(block, 400, None, None)

        paths, _duration, _should_delete = recorder.stop_to_wav(self.test_dir)
        try:
            self.assertEqual(len(paths), 3)
            # Verify chronological order
            self.assertTrue(paths[0].name.endswith("seg01.wav"))
            self.assertTrue(paths[1].name.endswith("seg02.wav"))
            self.assertTrue(paths[2].name.endswith("seg03.wav"))

            for p in paths:
                self.assertTrue(p.exists())

            with wave.open(str(paths[0]), "rb") as wf:
                self.assertEqual(wf.getnframes(), 1600)
            with wave.open(str(paths[1]), "rb") as wf:
                self.assertEqual(wf.getnframes(), 1600)
            with wave.open(str(paths[2]), "rb") as wf:
                self.assertEqual(wf.getnframes(), 400)
        finally:
            for p in paths:
                p.unlink(missing_ok=True)

    def test_run_background_recording_multi_chunk_sequential_transcription(self) -> None:
        args = voice.parse_args([])
        args.paste = True
        args.beep = False
        args.save_dir = None

        chunk1 = self.test_dir / "chunk1.wav"
        chunk2 = self.test_dir / "chunk2.wav"
        chunk3 = self.test_dir / "chunk3.wav"
        chunk1.write_bytes(b"dummy wav 1")
        chunk2.write_bytes(b"dummy wav 2")
        chunk3.write_bytes(b"dummy wav 3")

        mock_recorder = MagicMock()
        mock_recorder.recording = True
        mock_recorder.started_at = time.monotonic()
        mock_recorder.stop_to_wav.return_value = ([chunk1, chunk2, chunk3], 9.0, True)

        handlers = {}

        def fake_signal(sig, handler):
            handlers[sig] = handler

        def trigger_usr1():
            if voice.signal.SIGUSR1 in handlers:
                handlers[voice.signal.SIGUSR1](voice.signal.SIGUSR1, None)

        transcribe_calls = []

        def fake_transcribe(model_state, wav_path, call_args, initial_prompt=None):
            transcribe_calls.append((wav_path, initial_prompt))
            if wav_path == chunk1:
                return "Part one.", model_state
            if wav_path == chunk2:
                return "Part two.", model_state
            return "Part three.", model_state

        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=mock_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model", return_value=MagicMock()), \
             patch("voice.transcribe", side_effect=fake_transcribe), \
             patch("voice.insert_text", return_value=True) as mock_insert, \
             patch("time.sleep", side_effect=lambda _: trigger_usr1()):

            code = voice.run_background_recording(args)
            self.assertEqual(code, 0)
            self.assertEqual(len(transcribe_calls), 3)

            # Check prompt chaining across chunks
            self.assertIsNone(transcribe_calls[0][1])
            self.assertEqual(transcribe_calls[1][1], "Part one.")
            self.assertEqual(transcribe_calls[2][1], "Part two.")

            # Combined text inserted at the end
            mock_insert.assert_called_once_with("Part one. Part two. Part three.", args, raise_errors=True)

            # Temporary files cleaned up
            self.assertFalse(chunk1.exists())
            self.assertFalse(chunk2.exists())
            self.assertFalse(chunk3.exists())

    def test_run_background_recording_error_skipping_resilience(self) -> None:
        """Verify that when a chunk fails, it is skipped with [SKIPPING 3MIN SEG] without halting the rest."""
        args = voice.parse_args([])
        args.paste = True
        args.beep = False
        args.save_dir = None

        chunk1 = self.test_dir / "chunk1.wav"
        chunk2 = self.test_dir / "chunk2.wav"
        chunk3 = self.test_dir / "chunk3.wav"
        chunk1.write_bytes(b"dummy wav 1")
        chunk2.write_bytes(b"dummy wav 2")
        chunk3.write_bytes(b"dummy wav 3")

        mock_recorder = MagicMock()
        mock_recorder.recording = True
        mock_recorder.started_at = time.monotonic()
        mock_recorder.stop_to_wav.return_value = ([chunk1, chunk2, chunk3], 9.0, True)

        handlers = {}

        def fake_signal(sig, handler):
            handlers[sig] = handler

        def trigger_usr1():
            if voice.signal.SIGUSR1 in handlers:
                handlers[voice.signal.SIGUSR1](voice.signal.SIGUSR1, None)

        def fake_transcribe(model_state, wav_path, call_args, initial_prompt=None):
            if wav_path == chunk1:
                return "Beginning of talk.", model_state
            if wav_path == chunk2:
                raise RuntimeError("CTranslate2 OOM or corrupted audio")
            return "Conclusion of talk.", model_state

        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=mock_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model", return_value=MagicMock()), \
             patch("voice.transcribe", side_effect=fake_transcribe), \
             patch("voice.report_stt_failure") as mock_report, \
             patch("voice.insert_text", return_value=True) as mock_insert, \
             patch("time.sleep", side_effect=lambda _: trigger_usr1()):

            code = voice.run_background_recording(args)
            self.assertEqual(code, 0)

            # Failure for segment 2 reported with recovery WAV
            self.assertTrue(any(call_item[0][0] == "transcription of segment 2/3" for call_item in mock_report.call_args_list))

            # Full text includes the [SKIPPING 3MIN SEG] marker in place of chunk 2
            expected_text = f"Beginning of talk. {voice.SKIPPED_SEGMENT_MARKER} Conclusion of talk."
            mock_insert.assert_called_once_with(expected_text, args, raise_errors=True)

            # Temporary chunk files cleaned up
            self.assertFalse(chunk1.exists())
            self.assertFalse(chunk2.exists())
            self.assertFalse(chunk3.exists())


if __name__ == "__main__":
    unittest.main()
