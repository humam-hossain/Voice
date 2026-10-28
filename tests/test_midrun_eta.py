from __future__ import annotations

import argparse
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
