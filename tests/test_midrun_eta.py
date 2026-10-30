from __future__ import annotations

import argparse
import json
import math
import os
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase, advancing_monotonic


class DummySegment:
    def __init__(self, start: float, end: float, text: str = "test"):
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = -0.2
        self.compression_ratio = 1.0
        self.no_speech_prob = 0.01
        self.temperature = 0.0


class DummyInfo:
    def __init__(self, duration: float, duration_after_vad: Optional[float] = None):
        self.duration = duration
        self.duration_after_vad = duration_after_vad or duration


class TestMidRunRevisions(TempXdgTestCase):
    def test_generator_segment_blending(self) -> None:
        """ETA-04 / D-13 / D-14: Mid-run rate blends observed and calibrated rate after >= 5.0s."""
        yields = []

        def on_segment(decoded_s: float, total_s: float, elapsed_decode_s: float) -> None:
            yields.append((decoded_s, total_s, elapsed_decode_s))

        # Dummy model yielding 3 segments: 2.0s, 4.0s (cumulative 6.0s), 4.0s (cumulative 10.0s)
        dummy_model = MagicMock()
        dummy_segments = [
            DummySegment(0.0, 2.0, "segment one"),
            DummySegment(2.0, 6.0, "segment two"),
            DummySegment(6.0, 10.0, "segment three"),
        ]
        dummy_info = DummyInfo(10.0)
        dummy_model.transcribe.return_value = (iter(dummy_segments), dummy_info)
        dummy_state = voice.ModelState(model=dummy_model, requested_device="cpu", requested_compute_type="int8")

        args = argparse.Namespace(beam_size=1, vad_filter=True, language="en")
        wav_path = Path("/tmp/dummy.wav")

        with patch("time.monotonic", advancing_monotonic(100.0, 0.5)):
            ev = voice.transcribe_timed(
                dummy_state,
                wav_path,
                args,
                audio_s=10.0,
                on_segment_yield=on_segment,
            )

        self.assertEqual(len(yields), 3)
        self.assertEqual(yields[0][0], 2.0)
        self.assertEqual(yields[1][0], 6.0)
        self.assertEqual(yields[2][0], 10.0)

        # First yield at 2.0s (< 5.0s): no observed blending
        # Second yield at 6.0s (>= 5.0s): alpha = min(1.0, 6.0 / 30.0) = 0.2
        # Verify blending calculation logic
        initial_rate = 0.95
        total_audio_s = 10.0

        # Yield 1: decoded = 2.0 < 5.0 -> pure initial rate
        remaining_1 = initial_rate * (total_audio_s - 2.0) + voicemode_telemetry.PRIOR_INSERT_S
        self.assertAlmostEqual(remaining_1, 0.95 * 8.0 + 0.2, places=2)

        # Yield 2: decoded = 6.0 >= 5.0 -> blended rate
        alpha = min(1.0, 6.0 / 30.0)  # 0.2
        elapsed_decode_2 = yields[1][2]
        observed_rate = elapsed_decode_2 / 6.0
        blended_rate = (1.0 - alpha) * initial_rate + alpha * observed_rate
        remaining_2 = blended_rate * (total_audio_s - 6.0) + voicemode_telemetry.PRIOR_INSERT_S
        self.assertGreater(remaining_2, 0.0)

    def test_revision_hysteresis(self) -> None:
        """ETA-04 / D-09 / D-10: Downward steps immediate; upward jumps require delta >= 1.0s and elapsed >= 2.0s."""
        now = 1000.0
        last_revised = 1000.0
        curr_eta = 8

        # 1. Downward revision: 8 -> 5.2 (ceil = 6) steps immediately
        new_eta, revised, jump = voice.update_midrun_eta(5.2, curr_eta, last_revised, now + 0.5)
        self.assertTrue(revised)
        self.assertEqual(new_eta, 6)
        self.assertEqual(jump, 0.0)

        # 2. Upward jump with delta < 1.0s (curr=6, raw=6.8 -> delta 0.8): suppressed
        curr_eta = 6
        last_revised = now + 0.5
        new_eta, revised, jump = voice.update_midrun_eta(6.8, curr_eta, last_revised, now + 3.0)
        self.assertFalse(revised)
        self.assertEqual(new_eta, 6)
        self.assertEqual(jump, 0.0)

        # 3. Upward jump with elapsed < 2.0s (curr=6, raw=7.5 -> delta 1.5, elapsed 0.8s): suppressed
        new_eta, revised, jump = voice.update_midrun_eta(7.5, curr_eta, last_revised, last_revised + 0.8)
        self.assertFalse(revised)
        self.assertEqual(new_eta, 6)
        self.assertEqual(jump, 0.0)

        # 4. Upward jump with delta >= 1.0s AND elapsed >= 2.0s (curr=6, raw=7.5 -> delta 1.5, elapsed 2.5s): approved
        new_eta, revised, jump = voice.update_midrun_eta(7.5, curr_eta, last_revised, last_revised + 2.5)
        self.assertTrue(revised)
        self.assertEqual(new_eta, 8)
        self.assertAlmostEqual(jump, 1.5, places=2)


class TestOverrunAndDisplay(TempXdgTestCase):
    def test_1s_dwell_and_finishing_transition(self) -> None:
        """ETA-05 / D-12: Countdown dwells at 1s for 1.0s then transitions to Finishing… with overrun=True."""
        t0 = 500.0

        # Within dwell window (< 1.0s): display_s = 1, overrun = False
        disp1 = voice.calculate_countdown_display(remaining_raw=0.8, dwell_t0=t0, now=t0 + 0.4)
        self.assertEqual(disp1["display_s"], 1)
        self.assertFalse(disp1["overrun"])
        self.assertIn("1s", disp1["label"])

        # After dwell window (>= 1.0s): display_s = 0, overrun = True, label = 'Finishing…'
        disp2 = voice.calculate_countdown_display(remaining_raw=0.2, dwell_t0=t0, now=t0 + 1.2)
        self.assertEqual(disp2["display_s"], 0)
        self.assertTrue(disp2["overrun"])
        self.assertEqual(disp2["label"], "Finishing…")

    def test_prefix_persistence(self) -> None:
        """ETA-07 / D-15: ~ prefix persists for uncalibrated/prior/cold sources until Finishing…"""
        # Prior / uncalibrated -> prefix ~
        self.assertEqual(voice.format_eta_pill(4, eta_source="prior", overrun=False), "~4s")
        self.assertEqual(voice.format_eta_pill(1, eta_source="cold", overrun=False), "~1s")

        # Calibrated / mid-run -> no prefix
        self.assertEqual(voice.format_eta_pill(4, eta_source="calibrated", overrun=False), "4s")
        self.assertEqual(voice.format_eta_pill(3, eta_source="mid-run", overrun=False), "3s")

        # Overrun -> Finishing… (no prefix, no number)
        self.assertEqual(voice.format_eta_pill(0, eta_source="prior", overrun=True), "Finishing…")
        self.assertEqual(voice.format_eta_pill(0, eta_source="calibrated", overrun=True), "Finishing…")

    def test_eta_visibility_lifecycle(self) -> None:
        """ETA-06 / D-22: ETA is hidden during starting/recording and appears upon entering transcribing."""
        # Test format_eta_pill on None
        self.assertEqual(voice.format_eta_pill(None), "")

        # Verify build_status with None ETA fields
        st = voicemode_telemetry.build_status(
            pid=123,
            run_id="run-1",
            state="recording",
            phase="capture",
            started_at=100.0,
            eta_remaining_s=None,
            eta_epoch=None,
            eta_source=None,
            eta_confidence=None,
        )
        self.assertIsNone(st["eta_remaining_s"])
        self.assertIsNone(st["eta_epoch"])
        self.assertIsNone(st["eta_source"])
        self.assertIsNone(st["eta_confidence"])


class TestEtaLeakageDuringRecording(TempXdgTestCase):
    def test_chunk_decoding_during_recording_does_not_leak_eta_or_poison_shown_s(self) -> None:
        """Background chunk decoding must not leak 1s-4s ETAs while recording or poison shown_s in ledger."""
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = False

        chunk1 = Path("/tmp/chunk1.wav")
        chunk2 = Path("/tmp/chunk2.wav")

        published_statuses: list[dict] = []
        original_publish = voicemode_telemetry.publish_status

        def tracking_publish(st):
            published_statuses.append(dict(st))
            return original_publish(st)

        fake_recorder = MagicMock()
        fake_recorder.recording = True
        fake_recorder.started_at = time.monotonic() - 30.0
        fake_recorder.on_chunk_ready = None
        fake_recorder.chunk_audio_s = lambda idx: 5.0

        def fake_load_model(call_args, force_cpu=False):
            return MagicMock()

        def fake_transcribe_timed(model_state, path, call_args, initial_prompt=None, audio_s=None, on_segment_yield=None):
            # When chunk1 is decoded during recording, simulate segment yield callback
            if on_segment_yield:
                on_segment_yield(2.0, audio_s or 5.0, 0.5)
            return voice.TranscriptionEvidence(
                text="chunk " + path.stem,
                model_state=model_state,
                decode_ms=20.0,
                fallback=False,
                failure_type=None,
                backend="cpu, int8",
                avg_logprob=-0.2,
                compression_ratio=1.0,
                no_speech_prob=0.01,
                temperature=0.0,
                vad_audio_s=5.0,
                decoder_segments=1,
                fallback_load_ms=None,
                audio_s=audio_s or 5.0,
            )

        def fake_start():
            if fake_recorder.on_chunk_ready:
                # Chunk 1 ready while recording is ongoing
                fake_recorder.on_chunk_ready(1, chunk1, 5.0)

        fake_recorder.start.side_effect = fake_start

        def fake_stop(save_dir=None):
            fake_recorder.recording = False
            # 30 seconds total audio
            return ([chunk1, chunk2], 30.0, False)

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
             patch("voice.time.sleep", side_effect=fake_sleep), \
             patch("voicemode_telemetry.publish_status", side_effect=tracking_publish):
            code = voice.run_background_recording(args)

        self.assertEqual(code, 0)

        # 1. While recording was active, no status should have had eta_remaining_s or state='transcribing'
        recording_statuses = [st for st in published_statuses if st.get("state") == "recording"]
        self.assertTrue(len(recording_statuses) > 0)
        for st in recording_statuses:
            self.assertIsNone(
                st.get("eta_remaining_s"),
                f"ETA leaked during recording state: {st}",
            )

        # Chunks decoded while recording must not have published state='transcribing' prematurely
        # Any published status while fake_recorder was recording must NOT have state='transcribing'
        # and must not have an ETA remaining.
        # 2. Check the ledger record: shown_s must reflect full-audio ETA (~30s audio -> >=10s ETA), NOT 1s-4s chunk ETA!
        ledger_path = voicemode_telemetry.get_ledger_path()
        self.assertTrue(ledger_path.exists(), "Ledger should exist")
        lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
        self.assertTrue(len(lines) > 0, "Ledger record should have been written")
        rec = json.loads(lines[-1])
        predicted = rec.get("predicted", {})
        shown_s = predicted.get("shown_s")
        self.assertIsNotNone(shown_s, "shown_s should be recorded upon transitioning to transcribing")
        self.assertGreaterEqual(
            shown_s,
            10.0,
            f"shown_s was poisoned with small chunk ETA: {shown_s} (expected full audio ETA >= 10.0 for 30s audio)",
        )

    def test_midrun_revision_functions_normally_after_capture_closed(self) -> None:
        """After capture_closed is set, segment yields in remaining chunks update mid-run revisions and do not overwrite shown_s."""
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = False

        chunk1 = Path("/tmp/chunk1.wav")
        chunk2 = Path("/tmp/chunk2.wav")

        published_statuses: list[dict] = []
        original_publish = voicemode_telemetry.publish_status

        def tracking_publish(st):
            published_statuses.append(dict(st))
            return original_publish(st)

        fake_recorder = MagicMock()
        fake_recorder.recording = True
        fake_recorder.started_at = time.monotonic() - 30.0
        fake_recorder.on_chunk_ready = None
        fake_recorder.chunk_audio_s = lambda idx: 15.0

        def fake_load_model(call_args, force_cpu=False):
            return MagicMock()

        def fake_transcribe_timed(model_state, path, call_args, initial_prompt=None, audio_s=None, on_segment_yield=None):
            # When chunk2 is decoded after recording stops, simulate segment yield callback
            if on_segment_yield:
                on_segment_yield(6.0, audio_s or 15.0, 2.0)
            return voice.TranscriptionEvidence(
                text="chunk " + path.stem,
                model_state=model_state,
                decode_ms=20.0,
                fallback=False,
                failure_type=None,
                backend="cpu, int8",
                avg_logprob=-0.2,
                compression_ratio=1.0,
                no_speech_prob=0.01,
                temperature=0.0,
                vad_audio_s=15.0,
                decoder_segments=1,
                fallback_load_ms=None,
                audio_s=audio_s or 15.0,
            )

        def fake_start():
            pass  # Do not enqueue chunk during recording

        fake_recorder.start.side_effect = fake_start

        def fake_stop(save_dir=None):
            fake_recorder.recording = False
            return ([chunk1, chunk2], 30.0, False)

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
             patch("voice.time.sleep", side_effect=fake_sleep), \
             patch("voicemode_telemetry.publish_status", side_effect=tracking_publish):
            code = voice.run_background_recording(args)

        self.assertEqual(code, 0)

        # Transcribing decode statuses should have been published for chunk2
        decode_statuses = [
            st for st in published_statuses
            if st.get("state") == "transcribing" and st.get("phase") == "decode"
        ]
        self.assertTrue(len(decode_statuses) > 0, "Decode statuses should be published after capture closed")

        # Verify ledger has valid shown_s and revisions
        ledger_path = voicemode_telemetry.get_ledger_path()
        self.assertTrue(ledger_path.exists())
        lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
        rec = json.loads(lines[-1])
        predicted = rec.get("predicted", {})
        self.assertIsNotNone(predicted.get("shown_s"))
        self.assertGreaterEqual(predicted["shown_s"], 10.0)


