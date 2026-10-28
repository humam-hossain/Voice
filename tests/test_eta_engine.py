from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase


class TestETAEngine(TempXdgTestCase):
    def test_ratio_of_sums_formula(self) -> None:
        """ETA-01: Verify rate is sum(decode_s) / sum(audio_s), NOT mean of ratios."""
        cal = {}
        # Run 1: Short audio (0.8s), decode=1.2s -> RTF=1.5
        rec1 = {
            "audio_s": 0.8,
            "actual": {"decode_ms": 1200.0, "load_ms": 1200.0},
            "outcome": "success",
            "config": {"model": "medium", "device": "cpu", "compute_type": "int8"},
            "backend": "cpu, int8",
        }
        # Run 2: Long audio (20.0s), decode=10.0s -> RTF=0.5
        rec2 = {
            "audio_s": 20.0,
            "actual": {"decode_ms": 10000.0, "load_ms": 1200.0},
            "outcome": "success",
            "config": {"model": "medium", "device": "cpu", "compute_type": "int8"},
            "backend": "cpu, int8",
        }

        voicemode_telemetry.update_calibration_from_run(rec1, cal_data=cal)
        voicemode_telemetry.update_calibration_from_run(rec2, cal_data=cal)

        # Mean of ratios would be (1.5 + 0.5) / 2 = 1.0
        # Ratio of sums is (1.2 + 10.0) / (0.8 + 20.0) = 11.2 / 20.8 = 0.5384615...
        keys = voicemode_telemetry.extract_hierarchy_keys(rec1["config"], rec1["backend"])
        l2_key = keys["L2"]
        entry = cal["accumulators"]["L2"][l2_key]
        expected_rate = (1.2 + 10.0) / (0.8 + 20.0)
        actual_rate = entry["sum_decode_s"] / entry["sum_audio_s"]
        arithmetic_mean_rate = (1.5 + 0.5) / 2.0

        self.assertAlmostEqual(actual_rate, expected_rate, places=4)
        self.assertNotAlmostEqual(actual_rate, arithmetic_mean_rate, places=2)

    def test_tracer_pipeline(self) -> None:
        """Tracer: hierarchy -> ratio-of-sums -> dynamic load subtraction -> prediction record."""
        config = {
            "model": "medium",
            "device": "cpu",
            "compute_type": "int8",
            "beam_size": 1,
            "vad_filter": True,
            "language": "en",
            "chunk_s": 180.0,
        }
        backend = "cpu, int8"

        # Pre-seed calibration cache with 10 runs so n=10, shrinkage weight=1.0 at L0
        cal = {}
        for _ in range(10):
            rec = {
                "audio_s": 10.0,
                "actual": {"decode_ms": 5000.0, "load_ms": 1200.0, "total_ms": 6800.0},
                "outcome": "success",
                "config": config,
                "backend": backend,
                "predicted": {"shown_s": 6.8},
            }
            voicemode_telemetry.update_calibration_from_run(rec, cal_data=cal)

        voicemode_telemetry.save_calibration(cal)

        # Call calibrated_eta_seconds with audio_s=10.0, elapsed_record_s=2.0
        # load_s is 1.2s, so remaining_load = max(0.0, 1.2 - 2.0) = 0.0s
        # finalize_s = 0.4s, insert_s = 0.2s
        # rate at L0 is 5.0 / 10.0 = 0.50
        # eta = 0.4 + 0.0 + (0.50 * 10.0) + 0.2 = 5.6s
        eta, source, key_level, n, confidence = voicemode_telemetry.calibrated_eta_seconds(
            audio_s=10.0,
            config=config,
            backend=backend,
            elapsed_record_s=2.0,
            is_cold=False,
        )

        self.assertEqual(key_level, "L0")
        self.assertEqual(source, "calibrated")
        self.assertEqual(n, 10)
        self.assertAlmostEqual(eta, 5.6, places=2)
