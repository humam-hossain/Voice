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


class TestKeyHierarchy(TempXdgTestCase):
    def test_extract_hierarchy_keys_structure(self) -> None:
        """ETA-02: Verify extract_hierarchy_keys formats L0 (8 fields), L1 (6 fields), L2 (4 fields), L3 (prior)."""
        config = {
            "model": "medium.en",
            "device": "cuda",
            "compute_type": "float16",
            "beam_size": 2,
            "vad_filter": False,
            "language": "en",
            "chunk_s": 90.0,
        }
        backend = "cuda, float16"

        keys = voicemode_telemetry.extract_hierarchy_keys(config, backend)
        self.assertIn("L0", keys)
        self.assertIn("L1", keys)
        self.assertIn("L2", keys)
        self.assertIn("L3", keys)

        # L0: 8 fields
        self.assertEqual(
            keys["L0"],
            "medium.en|cuda|float16|cuda, float16|beam=2|vad=0|lang=en|chunk=90.0",
        )
        # L1: 6 fields (drops chunk_s and vad_filter)
        self.assertEqual(
            keys["L1"],
            "medium.en|cuda|float16|cuda, float16|beam=2|lang=en",
        )
        # L2: 4 fields (model, device, compute_type, backend)
        self.assertEqual(
            keys["L2"],
            "medium.en|cuda|float16|cuda, float16",
        )
        # L3: prior:prefix
        self.assertEqual(keys["L3"], "prior:medium")

    def test_hierarchy_fallback_under_sample_floor(self) -> None:
        """ETA-02: Minimum sample floor n=3. Below 3, fall to broader tiers."""
        keys = {
            "L0": "m|cpu|int8|b|beam=1|vad=1|lang=en|chunk=180.0",
            "L1": "m|cpu|int8|b|beam=1|lang=en",
            "L2": "m|cpu|int8|b",
            "L3": "prior:m",
        }
        prior_rtf = 0.95

        # Case 1: All empty -> L3 prior
        rate, level, n = voicemode_telemetry.resolve_calibrated_rate(keys, {}, prior_rtf)
        self.assertEqual(level, "L3")
        self.assertEqual(n, 0)
        self.assertEqual(rate, prior_rtf)

        # Case 2: L0 has n=1 (<3), L1 has n=2 (<3), L2 has n=4 (>=3) -> falls to L2
        accs = {
            "L0": {keys["L0"]: {"n": 1, "sum_decode_s": 0.4, "sum_audio_s": 1.0}},
            "L1": {keys["L1"]: {"n": 2, "sum_decode_s": 1.0, "sum_audio_s": 2.0}},
            "L2": {keys["L2"]: {"n": 4, "sum_decode_s": 2.4, "sum_audio_s": 4.0}},
        }
        rate, level, n = voicemode_telemetry.resolve_calibrated_rate(keys, accs, prior_rtf)
        self.assertEqual(level, "L2")
        self.assertEqual(n, 4)

    def test_james_stein_shrinkage_blending(self) -> None:
        """ETA-02: James-Stein shrinkage weight = min(1.0, n/10.0)."""
        keys = {
            "L0": "m|cpu|int8|b|beam=1|vad=1|lang=en|chunk=180.0",
            "L1": "m|cpu|int8|b|beam=1|lang=en",
            "L2": "m|cpu|int8|b",
            "L3": "prior:m",
        }
        prior_rtf = 1.0

        # L1 has n=10 (fully calibrated parent rate = 0.6)
        # L0 has n=5 -> weight = 5 / 10 = 0.5
        # L0 raw rate = 0.4 / 1.0 = 0.4
        # Blended rate at L0 should be: 0.5 * 0.4 + 0.5 * 0.6 = 0.5
        accs_5 = {
            "L1": {keys["L1"]: {"n": 10, "sum_decode_s": 6.0, "sum_audio_s": 10.0}},
            "L0": {keys["L0"]: {"n": 5, "sum_decode_s": 2.0, "sum_audio_s": 5.0}},
        }
        rate, level, n = voicemode_telemetry.resolve_calibrated_rate(keys, accs_5, prior_rtf)
        self.assertEqual(level, "L0")
        self.assertEqual(n, 5)
        self.assertAlmostEqual(rate, 0.5, places=4)

        # L0 has n=10 -> weight = 1.0 -> fully trusts L0 rate (0.4)
        accs_10 = {
            "L1": {keys["L1"]: {"n": 10, "sum_decode_s": 6.0, "sum_audio_s": 10.0}},
            "L0": {keys["L0"]: {"n": 10, "sum_decode_s": 4.0, "sum_audio_s": 10.0}},
        }
        rate, level, n = voicemode_telemetry.resolve_calibrated_rate(keys, accs_10, prior_rtf)
        self.assertEqual(level, "L0")
        self.assertEqual(n, 10)
        self.assertAlmostEqual(rate, 0.4, places=4)

    def test_out_of_bounds_rate_rejection(self) -> None:
        """T-07-02: Rates outside [0.01, 10.0] are rejected and fall back to broader tier."""
        keys = {
            "L0": "m|cpu|int8|b|beam=1|vad=1|lang=en|chunk=180.0",
            "L1": "m|cpu|int8|b|beam=1|lang=en",
            "L2": "m|cpu|int8|b",
            "L3": "prior:m",
        }
        prior_rtf = 0.8

        # L0 raw rate = 25.0 / 1.0 = 25.0 (>10.0 outlier)
        # L1 raw rate = 0.5 / 1.0 = 0.5 (valid)
        accs = {
            "L0": {keys["L0"]: {"n": 10, "sum_decode_s": 25.0, "sum_audio_s": 1.0}},
            "L1": {keys["L1"]: {"n": 10, "sum_decode_s": 5.0, "sum_audio_s": 10.0}},
        }
        rate, level, n = voicemode_telemetry.resolve_calibrated_rate(keys, accs, prior_rtf)
        self.assertEqual(level, "L1")
        self.assertAlmostEqual(rate, 0.5, places=4)
