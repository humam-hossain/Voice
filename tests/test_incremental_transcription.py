from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase


class TestIncrementalTranscription(TempXdgTestCase):
    def test_model_loads_and_chunks_decode_before_stop(self) -> None:
        """Verify model loads while recording is active and chunks decode incrementally via consumer queue."""
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = False

        chunk1 = Path("/tmp/chunk1.wav")
        chunk2 = Path("/tmp/chunk2.wav")
        chunk3 = Path("/tmp/chunk3.wav")

        model_loaded_while_recording = []
        chunks_decoded_during_recording = []

        fake_recorder = MagicMock()
        fake_recorder.recording = True
        fake_recorder.started_at = time.monotonic()
        fake_recorder.on_chunk_ready = None
        fake_recorder.chunk_audio_s = lambda idx: 3.0

        def fake_load_model(call_args, force_cpu=False):
            model_loaded_while_recording.append(fake_recorder.recording)
            return MagicMock()

        def fake_transcribe_timed(model_state, path, call_args, initial_prompt=None, audio_s=None):
            chunks_decoded_during_recording.append((path, fake_recorder.recording, initial_prompt))
            text = "chunk " + path.stem
            return voice.TranscriptionEvidence(
                text=text,
                model_state=model_state,
                decode_ms=12.0,
                fallback=False,
                failure_type=None,
                backend="cpu, int8",
                avg_logprob=-0.2,
                compression_ratio=1.0,
                no_speech_prob=0.01,
                temperature=0.0,
                vad_audio_s=3.0,
                decoder_segments=1,
                fallback_load_ms=None,
                audio_s=audio_s or 3.0,
            )

        def fake_start():
            if fake_recorder.on_chunk_ready:
                fake_recorder.on_chunk_ready(1, chunk1, 3.0)

        fake_recorder.start.side_effect = fake_start

        def fake_stop(save_dir=None):
            fake_recorder.recording = False
            return ([chunk1, chunk2, chunk3], 9.0, False)

        fake_recorder.stop_to_wav.side_effect = fake_stop

        handlers = {}
        def fake_signal(sig, handler):
            handlers[sig] = handler

        def fake_sleep(duration):
            import threading
            threading.Event().wait(0.05)
            if voice.signal.SIGUSR1 in handlers:
                handlers[voice.signal.SIGUSR1](voice.signal.SIGUSR1, None)

        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=fake_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model", side_effect=fake_load_model), \
             patch("voice.transcribe_timed", side_effect=fake_transcribe_timed), \
             patch("voice.time.sleep", side_effect=fake_sleep):
            code = voice.run_background_recording(args)

        self.assertEqual(code, 0)
        self.assertTrue(len(model_loaded_while_recording) > 0)
        self.assertTrue(model_loaded_while_recording[0], "Model should load while recording is True")
        self.assertTrue(any(item[0] == chunk1 and item[1] is True for item in chunks_decoded_during_recording))
        self.assertEqual(len(chunks_decoded_during_recording), 3)

    def test_output_ordering_and_prompt_chaining(self) -> None:
        """Verify chunks assemble in index order and prompt chaining passes previous chunk text."""
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = True

        c1 = Path("/tmp/c1.wav")
        c2 = Path("/tmp/c2.wav")
        c3 = Path("/tmp/c3.wav")

        fake_recorder = MagicMock()
        fake_recorder.recording = True
        fake_recorder.started_at = time.monotonic()
        fake_recorder.stop_to_wav.return_value = ([c1, c2, c3], 9.0, False)
        fake_recorder.chunk_audio_s = lambda idx: 3.0

        prompts_received = []

        def fake_transcribe_timed(model_state, path, call_args, initial_prompt=None, audio_s=None):
            prompts_received.append((path, initial_prompt))
            t = "first" if path == c1 else ("second" if path == c2 else "third")
            return voice.TranscriptionEvidence(
                text=t,
                model_state=model_state,
                decode_ms=10.0,
                fallback=False,
                failure_type=None,
                backend="cpu, int8",
                avg_logprob=-0.2,
                compression_ratio=1.0,
                no_speech_prob=0.01,
                temperature=0.0,
                vad_audio_s=3.0,
                decoder_segments=1,
                fallback_load_ms=None,
                audio_s=3.0,
            )

        handlers = {}
        def fake_signal(sig, handler):
            handlers[sig] = handler

        def stop_now(_):
            if voice.signal.SIGUSR1 in handlers:
                handlers[voice.signal.SIGUSR1](voice.signal.SIGUSR1, None)

        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=fake_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model", return_value=MagicMock()), \
             patch("voice.transcribe_timed", side_effect=fake_transcribe_timed), \
             patch("voice.insert_text", return_value=True) as mock_insert, \
             patch("voice.time.sleep", side_effect=stop_now):
            voice.run_background_recording(args)

        mock_insert.assert_called_once_with("first second third", args, raise_errors=True)
        self.assertIsNone(prompts_received[0][1])
        self.assertEqual(prompts_received[1][1], "first")
        self.assertEqual(prompts_received[2][1], "second")

    def test_failed_chunk_skipped_and_audio_s_reaches_ledger(self) -> None:
        """Verify failed chunk produces SKIPPED_SEGMENT_MARKER and chunk audio_s reaches ledger row."""
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = False

        c1 = Path("/tmp/part1.wav")
        c2 = Path("/tmp/part2.wav")

        fake_recorder = MagicMock()
        fake_recorder.recording = True
        fake_recorder.started_at = time.monotonic()
        fake_recorder.stop_to_wav.return_value = ([c1, c2], 6.0, False)
        fake_recorder.chunk_audio_s = lambda idx: 3.14 if idx == 1 else 2.86

        def fake_transcribe(model_state, path, call_args, initial_prompt=None, audio_s=None):
            if path == c2:
                raise RuntimeError("segment failure")
            return voice.TranscriptionEvidence(
                text="valid part",
                model_state=model_state,
                decode_ms=25.0,
                fallback=False,
                failure_type=None,
                backend="cpu, int8",
                avg_logprob=-0.2,
                compression_ratio=1.0,
                no_speech_prob=0.01,
                temperature=0.0,
                vad_audio_s=3.14,
                decoder_segments=1,
                fallback_load_ms=None,
                audio_s=audio_s,
            )

        handlers = {}
        def fake_signal(sig, handler):
            handlers[sig] = handler

        def stop_now(_):
            if voice.signal.SIGUSR1 in handlers:
                handlers[voice.signal.SIGUSR1](voice.signal.SIGUSR1, None)

        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=fake_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model", return_value=MagicMock()), \
             patch("voice.transcribe_timed", side_effect=fake_transcribe), \
             patch("voice.report_stt_failure"), \
             patch("voice.time.sleep", side_effect=stop_now):
            voice.run_background_recording(args)

        rows = list(voicemode_telemetry.read_ledger_rows())
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(len(r["segments"]), 2)
        self.assertEqual(r["segments"][0]["idx"], 1)
        self.assertEqual(r["segments"][0]["audio_s"], 3.14)
        self.assertTrue(r["segments"][0]["ok"])
        self.assertEqual(r["segments"][1]["idx"], 2)
        self.assertEqual(r["segments"][1]["audio_s"], 2.86)
        self.assertFalse(r["segments"][1]["ok"])
        self.assertEqual(r["segments"][1]["error_type"], "RuntimeError")

    def test_cancel_does_not_wait_for_in_flight(self) -> None:
        """Verify SIGTERM cancellation exits promptly and writes a cancelled ledger row."""
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = False

        fake_recorder = MagicMock()
        fake_recorder.recording = True
        fake_recorder.started_at = time.monotonic()

        handlers = {}
        def fake_signal(sig, handler):
            handlers[sig] = handler

        def cancel_now(_):
            if voice.signal.SIGTERM in handlers:
                handlers[voice.signal.SIGTERM](voice.signal.SIGTERM, None)

        with patch("signal.signal", side_effect=fake_signal), \
             patch("voice.Recorder", return_value=fake_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.write_pid_state"), \
             patch("voice.remove_pid"), \
             patch("voice.load_model", return_value=MagicMock()), \
             patch("voice.time.sleep", side_effect=cancel_now):
            ret = voice.run_background_recording(args)

        self.assertEqual(ret, 0)
        rows = list(voicemode_telemetry.read_ledger_rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "cancelled")


if __name__ == "__main__":
    unittest.main()
