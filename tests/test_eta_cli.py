"""Tests for ETA calibration persistence, cold boot detection, CLI flags, and kill switch (ETA-03, ETA-09)."""
from __future__ import annotations

import json
import os
import sys
import time
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

from _hermetic import TempXdgTestCase
import voice
import voicemode_telemetry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_success_record(
    audio_s=5.0,
    decode_ms=500.0,
    load_ms=800.0,
    total_ms=2500.0,
    shown_s=2.8,
    source="prior",
    outcome="success",
    fallback_used=False,
    model="medium",
    device="cpu",
    compute_type="int8",
    beam_size=5,
    vad_filter=True,
    language="en",
    chunk_s=30,
    ts_start=None,
    ts_end=None,
):
    now = time.time()
    return {
        "schema": 1,
        "source": "stt",
        "run_id": "test-run-1",
        "install_id": "test-install",
        "ts_start": ts_start or now - 5.0,
        "ts_end": ts_end or now,
        "outcome": outcome,
        "error_stage": None,
        "actual": {
            "total_ms": total_ms,
            "finalize_ms": 50.0,
            "load_ms": load_ms,
            "decode_ms": decode_ms,
            "insert_ms": 30.0,
        },
        "predicted": {
            "shown_s": shown_s,
            "shown_at_epoch": now - 3.0,
            "source": source,
            "key_level": None,
            "n": None,
            "confidence": None,
            "revisions": 0,
            "actual_s": total_ms / 1000.0 if total_ms else None,
        },
        "audio_s": audio_s,
        "chars_out": 12,
        "chars_typed": 12,
        "fallback_used": fallback_used,
        "insert_ok": True,
        "segments": [],
        "config": {
            "model": model,
            "device": device,
            "compute_type": compute_type,
            "beam_size": beam_size,
            "vad_filter": vad_filter,
            "language": language,
            "chunk_s": chunk_s,
        },
        "backend": f"{device}, {compute_type}",
    }


class TestCalibrationPersistence(TempXdgTestCase):
    """Task 1: Worker finalization calibration persistence, exclusion gating, and MAD confidence."""

    def test_update_calibration_from_success_run(self):
        """Non-excluded successful run updates accumulators at L0, L1, L2."""
        rec = _make_success_record(audio_s=10.0, decode_ms=1000.0)
        result = voicemode_telemetry.update_calibration_from_run(rec)
        self.assertIsInstance(result, dict)

        cal = voicemode_telemetry.load_calibration()
        accs = cal.get("accumulators", {})
        # Should have entries at all three levels
        for tier in ("L0", "L1", "L2"):
            tier_map = accs.get(tier, {})
            self.assertTrue(len(tier_map) > 0, f"No entries in {tier}")
            for entry in tier_map.values():
                self.assertEqual(entry["n"], 1)
                self.assertAlmostEqual(entry["sum_decode_s"], 1.0, places=3)
                self.assertAlmostEqual(entry["sum_audio_s"], 10.0, places=3)

    def test_exclusion_failed_outcome(self):
        """outcome != 'success' is excluded from accumulator fitting."""
        rec = _make_success_record(outcome="error")
        self.assertTrue(voicemode_telemetry._is_calibration_excluded(rec))

    def test_exclusion_fallback_used(self):
        """fallback_used=True is excluded."""
        rec = _make_success_record(fallback_used=True)
        self.assertTrue(voicemode_telemetry._is_calibration_excluded(rec))

    def test_exclusion_cold_boot_source(self):
        """Cold boot runs (predicted.source == 'cold') are excluded."""
        rec = _make_success_record(source="cold")
        self.assertTrue(voicemode_telemetry._is_calibration_excluded(rec))

    def test_exclusion_high_load_contention(self):
        """load_ms > 3600 (contention proxy) is excluded."""
        rec = _make_success_record(load_ms=4000.0)
        self.assertTrue(voicemode_telemetry._is_calibration_excluded(rec))

    def test_exclusion_extreme_rate_outlier(self):
        """rate outside [0.01, 10.0] is excluded."""
        # Very fast (rate < 0.01): 1ms decode for 10s audio = 0.0001
        rec = _make_success_record(audio_s=10.0, decode_ms=1.0)
        self.assertTrue(voicemode_telemetry._is_calibration_excluded(rec))
        # Very slow (rate > 10.0): 200s decode for 1s audio = 200.0
        rec2 = _make_success_record(audio_s=1.0, decode_ms=200000.0)
        self.assertTrue(voicemode_telemetry._is_calibration_excluded(rec2))

    def test_normal_run_not_excluded(self):
        """A normal successful run is NOT excluded."""
        rec = _make_success_record()
        self.assertFalse(voicemode_telemetry._is_calibration_excluded(rec))

    def test_excluded_records_still_in_ledger(self):
        """Excluded records are appended to metrics.jsonl but excluded from calibration accumulators."""
        rec = _make_success_record(outcome="error")
        # Manually append to ledger
        voicemode_telemetry.append_ledger_row(rec)
        rows = list(voicemode_telemetry.read_ledger_rows())
        self.assertTrue(any(r.get("outcome") == "error" for r in rows))

        # But calibration accumulators are empty
        voicemode_telemetry.update_calibration_from_run(rec)
        cal = voicemode_telemetry.load_calibration()
        accs = cal.get("accumulators", {})
        for tier in ("L0", "L1", "L2"):
            tier_map = accs.get(tier, {})
            for entry in tier_map.values():
                self.assertEqual(entry.get("n", 0), 0)

    def test_accumulator_increments_per_level(self):
        """Multiple successful runs accumulate properly per level."""
        for i in range(5):
            rec = _make_success_record(audio_s=10.0, decode_ms=1000.0 + i * 10)
            voicemode_telemetry.update_calibration_from_run(rec)

        cal = voicemode_telemetry.load_calibration()
        accs = cal.get("accumulators", {})
        for tier in ("L0", "L1", "L2"):
            tier_map = accs.get(tier, {})
            self.assertTrue(len(tier_map) > 0)
            for entry in tier_map.values():
                self.assertEqual(entry["n"], 5)

    def test_mad_confidence_basic(self):
        """compute_mad_confidence: 1.0 - MAD/median, clamped [0, 1]."""
        # Identical residuals => MAD=0 => confidence=1.0
        self.assertEqual(voicemode_telemetry.compute_mad_confidence([1.0, 1.0, 1.0, 1.0]), 1.0)
        # < 3 residuals => 0.0
        self.assertEqual(voicemode_telemetry.compute_mad_confidence([1.0, 2.0]), 0.0)
        self.assertEqual(voicemode_telemetry.compute_mad_confidence([]), 0.0)
        # Spread residuals
        res = [1.0, 2.0, 3.0, 4.0, 5.0]
        conf = voicemode_telemetry.compute_mad_confidence(res)
        self.assertGreater(conf, 0.0)
        self.assertLessEqual(conf, 1.0)

    def test_residuals_capped_at_30(self):
        """Residuals list is capped at 30 items."""
        cal = {"accumulators": {"L0": {}, "L1": {}, "L2": {}}, "residuals": []}
        for i in range(40):
            rec = _make_success_record(
                audio_s=10.0,
                decode_ms=1000.0,
                total_ms=2500.0,
                shown_s=2.5 + i * 0.01,
            )
            voicemode_telemetry.update_calibration_from_run(rec, cal_data=cal)
        self.assertLessEqual(len(cal.get("residuals", [])), 30)

    def test_calibration_json_permissions(self):
        """calibration.json is saved with 0o600 permissions."""
        rec = _make_success_record()
        voicemode_telemetry.update_calibration_from_run(rec)
        cal_path = voicemode_telemetry.get_calibration_path()
        if cal_path.exists():
            perms = cal_path.stat().st_mode & 0o777
            self.assertEqual(perms, 0o600)

    def test_cache_rebuild_from_ledger(self):
        """If calibration.json is missing, rebuild_calibration_from_ledger rebuilds from metrics.jsonl."""
        # Write several successful records to ledger
        for i in range(3):
            rec = _make_success_record(audio_s=10.0, decode_ms=1000.0)
            voicemode_telemetry.append_ledger_row(rec)

        # Remove calibration.json
        cal_path = voicemode_telemetry.get_calibration_path()
        if cal_path.exists():
            cal_path.unlink()

        cal = voicemode_telemetry.rebuild_calibration_from_ledger()
        accs = cal.get("accumulators", {})
        # Should have rebuilt entries
        found = False
        for tier in ("L0", "L1", "L2"):
            tier_map = accs.get(tier, {})
            for entry in tier_map.values():
                if entry.get("n", 0) > 0:
                    found = True
        self.assertTrue(found, "Rebuilt calibration should have accumulator entries")

    def test_cache_rebuild_respects_reset_epoch(self):
        """Rebuild ignores ledger records timestamped before reset epoch."""
        old_time = time.time() - 3600
        new_time = time.time()

        # Old record
        old_rec = _make_success_record(audio_s=10.0, decode_ms=1000.0, ts_start=old_time - 5, ts_end=old_time)
        voicemode_telemetry.append_ledger_row(old_rec)

        # Reset calibration
        voicemode_telemetry.reset_calibration()

        # New record after reset
        new_rec = _make_success_record(audio_s=10.0, decode_ms=2000.0, ts_start=new_time - 1, ts_end=new_time)
        voicemode_telemetry.append_ledger_row(new_rec)

        cal = voicemode_telemetry.rebuild_calibration_from_ledger()
        accs = cal.get("accumulators", {})
        # Only the new record should be in accumulators
        for tier in ("L0", "L1", "L2"):
            tier_map = accs.get(tier, {})
            for entry in tier_map.values():
                if entry.get("n", 0) > 0:
                    # decode_s from the new record = 2000ms / 1000 = 2.0
                    self.assertAlmostEqual(entry["sum_decode_s"], 2.0, places=3)
                    self.assertEqual(entry["n"], 1)

    def test_post_paste_finalization_updates_calibration(self):
        """finalize_background_run calls update_calibration_from_run after appending to ledger."""
        ev = voice.TranscriptionEvidence(
            text="hello",
            model_state=MagicMock(),
            decode_ms=500.0,
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
            audio_s=5.0,
        )
        run_state = {
            "lock": None,
            "finalized": False,
            "pid": None,
            "run_id": "test-run",
            "ts_start": time.time() - 3,
            "t_start": time.monotonic() - 3,
            "args": voice.parse_args([]),
            "recorder": None,
            "wav_paths": [],
            "should_delete": False,
            "outcome": "success",
            "error_stage": None,
            "results": {0: ev},
            "results_lock": None,
            "loader_state": {"load_ms": 800.0, "backend": "cpu, int8"},
            "model_holder": {"state": None},
            "text_holder": {"text": "hello"},
            "chars_typed": [5],
            "audio_s": 5.0,
            "status_state": {},
            "status_lock": None,
            "finalize_ms": 50.0,
            "insert_ms": 30.0,
            "insert_ok": True,
            "backend": "cpu, int8",
            "predicted": {
                "shown_s": 2.5,
                "shown_at_epoch": time.time() - 2,
                "source": "prior",
                "key_level": None,
                "n": None,
                "confidence": None,
                "revisions": 0,
                "actual_s": 2.5,
            },
            "text": "hello",
        }

        with patch("voicemode_telemetry.update_calibration_from_run", wraps=voicemode_telemetry.update_calibration_from_run) as mock_update:
            voice.finalize_background_run(run_state, outcome="success")
            mock_update.assert_called_once()
            # Verify it was called with the record dict
            called_record = mock_update.call_args[0][0]
            self.assertIsInstance(called_record, dict)
            self.assertEqual(called_record.get("outcome"), "success")


class TestETACLI(TempXdgTestCase):
    """Task 2: Cold boot, CLI --reset-calibration, --status --json, VOICE_ETA=off."""

    def test_boot_session_cold_detection(self):
        """First call returns True (cold), subsequent calls return False."""
        state_dir = self.run_dir / "voice-stt"
        marker = state_dir / ".boot_session"
        # Remove if exists
        if marker.exists():
            marker.unlink()
        self.assertTrue(voicemode_telemetry.check_and_mark_boot_session(state_dir))
        self.assertTrue(marker.exists())
        # Permissions
        perms = marker.stat().st_mode & 0o777
        self.assertEqual(perms, 0o600)
        # Second call is warm
        self.assertFalse(voicemode_telemetry.check_and_mark_boot_session(state_dir))

    def test_reset_calibration_creates_epoch(self):
        """--reset-calibration deletes cache and establishes reset epoch."""
        # Create a calibration file first
        voicemode_telemetry.save_calibration({"accumulators": {"L0": {}, "L1": {}, "L2": {}}})
        cal_path = voicemode_telemetry.get_calibration_path()
        self.assertTrue(cal_path.exists())

        voicemode_telemetry.reset_calibration()

        self.assertFalse(cal_path.exists())
        reset_epoch = voicemode_telemetry.get_calibration_reset_timestamp()
        self.assertIsNotNone(reset_epoch)
        self.assertIsInstance(reset_epoch, float)
        self.assertGreater(reset_epoch, 0)

    def test_reset_calibration_cli_output(self):
        """voice --reset-calibration prints confirmation message."""
        voicemode_telemetry.save_calibration({"accumulators": {}})

        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            with patch("sys.argv", ["voice", "--reset-calibration"]):
                code = voice.main()
        finally:
            sys.stdout = old

        self.assertEqual(code, 0)
        self.assertIn("Calibration reset to priors.", f.getvalue())

    def test_status_json_eta_fields(self):
        """--status --json exposes revision_count, last_revised_at, key_level, key_n, overrun."""
        voicemode_telemetry.publish_status(voicemode_telemetry.build_status(
            pid=123, run_id="r1", state="transcribing", phase="decode",
            started_at=100.0, eta_remaining_s=4.0, eta_source="calibrated",
            eta_confidence="high", overrun=False,
            revision_count=3, last_revised_at=100.5,
            key_level="L0", key_n=12,
        ))

        args = voice.parse_args(["--status", "--json-status"])
        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            with patch("voice.process_alive", return_value=True), \
                 patch("voice.read_pid", return_value=123), \
                 patch("voicemode_telemetry.read_pid_state", return_value=(123, "transcribing")):
                voice.print_status(args)
        finally:
            sys.stdout = old

        output = f.getvalue().strip()
        self.assertTrue(output, "Expected JSON output but got empty string")
        payload = json.loads(output)
        self.assertEqual(payload["state"], "transcribing")
        self.assertEqual(payload["eta_remaining_s"], 4.0)
        self.assertEqual(payload["eta_source"], "calibrated")
        self.assertEqual(payload["eta_confidence"], "high")
        self.assertIn("revision_count", payload)
        self.assertEqual(payload["revision_count"], 3)
        self.assertIn("last_revised_at", payload)
        self.assertEqual(payload["last_revised_at"], 100.5)
        self.assertIn("key_level", payload)
        self.assertEqual(payload["key_level"], "L0")
        self.assertIn("key_n", payload)
        self.assertEqual(payload["key_n"], 12)
        self.assertIn("overrun", payload)
        self.assertFalse(payload["overrun"])
        self.assertIn("eta_epoch", payload)

    def test_status_json_with_standard_json_flag(self):
        """voice --status --json emits structured JSON with extended ETA fields."""
        voicemode_telemetry.publish_status(voicemode_telemetry.build_status(
            pid=456, run_id="r2", state="transcribing", phase="decode",
            started_at=200.0, eta_remaining_s=3.0, eta_source="prior",
            eta_confidence="low", overrun=False,
            revision_count=1, last_revised_at=201.0,
            key_level="L3", key_n=0,
        ))

        args = voice.parse_args(["--status", "--json"])
        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            with patch("voice.process_alive", return_value=True), \
                 patch("voice.read_pid", return_value=456), \
                 patch("voicemode_telemetry.read_pid_state", return_value=(456, "transcribing")):
                voice.print_status(args)
        finally:
            sys.stdout = old

        payload = json.loads(f.getvalue().strip())
        self.assertEqual(payload["state"], "transcribing")
        self.assertEqual(payload["eta_remaining_s"], 3.0)
        self.assertEqual(payload["eta_source"], "prior")
        self.assertEqual(payload["key_level"], "L3")
        self.assertEqual(payload["key_n"], 0)

    def test_status_json_suppressed_when_voice_eta_off(self):
        """voice --status --json sets eta fields to null when VOICE_ETA=off."""
        voicemode_telemetry.publish_status(voicemode_telemetry.build_status(
            pid=789, run_id="r3", state="transcribing", phase="decode",
            started_at=300.0, eta_remaining_s=5.0, eta_source="calibrated",
            eta_confidence="high", overrun=False,
            revision_count=2, last_revised_at=301.0,
            key_level="L0", key_n=5,
        ))

        args = voice.parse_args(["--status", "--json"])
        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            with patch.dict(os.environ, {"VOICE_ETA": "off"}), \
                 patch("voice.process_alive", return_value=True), \
                 patch("voice.read_pid", return_value=789), \
                 patch("voicemode_telemetry.read_pid_state", return_value=(789, "transcribing")):
                voice.print_status(args)
        finally:
            sys.stdout = old

        payload = json.loads(f.getvalue().strip())
        self.assertEqual(payload["state"], "transcribing")
        self.assertIsNone(payload["eta_remaining_s"])
        self.assertIsNone(payload["eta_epoch"])
        self.assertIsNone(payload["eta_source"])
        self.assertIsNone(payload["eta_confidence"])
        self.assertIsNone(payload["key_level"])
        self.assertIsNone(payload["key_n"])

    def test_voice_eta_kill_switch(self):
        """VOICE_ETA=off cleanly suppresses ETA calculation."""
        with patch.dict(os.environ, {"VOICE_ETA": "off"}):
            eta, src, lvl, n, conf = voicemode_telemetry.calibrated_eta_seconds(10.0)
            self.assertIsNone(eta)
            self.assertIsNone(src)
            self.assertIsNone(lvl)
            self.assertIsNone(conf)

    def test_voice_eta_kill_switch_variants(self):
        """VOICE_ETA recognizes 0, false, no, off as kill values."""
        for val in ("0", "false", "no", "off", "OFF", "False"):
            with patch.dict(os.environ, {"VOICE_ETA": val}):
                eta, src, lvl, n, conf = voicemode_telemetry.calibrated_eta_seconds(10.0)
                self.assertIsNone(eta, f"Kill switch failed for VOICE_ETA={val}")

    def test_voice_eta_not_set_allows_eta(self):
        """Without VOICE_ETA set, ETA calculation proceeds normally."""
        env = dict(os.environ)
        env.pop("VOICE_ETA", None)
        with patch.dict(os.environ, env, clear=True):
            eta, src, lvl, n, conf = voicemode_telemetry.calibrated_eta_seconds(10.0)
            self.assertIsNotNone(eta)
            self.assertGreater(eta, 0)

    def test_cold_boot_eta_source(self):
        """Cold boot produces source='cold' and confidence='low'."""
        eta, src, lvl, n, conf = voicemode_telemetry.calibrated_eta_seconds(
            10.0, is_cold=True
        )
        self.assertIsNotNone(eta)
        self.assertEqual(src, "cold")
        self.assertEqual(conf, "low")

    def test_calibration_confidence_in_cache(self):
        """After enough runs with residuals, confidence is stored in cache."""
        cal = {"accumulators": {"L0": {}, "L1": {}, "L2": {}}, "residuals": []}
        for i in range(5):
            rec = _make_success_record(
                audio_s=10.0,
                decode_ms=1000.0,
                total_ms=2500.0,
                shown_s=2.5 + i * 0.05,
            )
            voicemode_telemetry.update_calibration_from_run(rec, cal_data=cal)

        self.assertIn("confidence", cal)
        self.assertIsInstance(cal["confidence"], float)
        self.assertGreaterEqual(cal["confidence"], 0.0)
        self.assertLessEqual(cal["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
