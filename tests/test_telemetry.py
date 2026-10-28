from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
from _hermetic import TempXdgTestCase, advancing_monotonic
import voicemode_telemetry


class TestTracerContract(TempXdgTestCase):
    def test_append_one_row_per_run(self) -> None:
        row1 = {"schema": 1, "run_id": "a", "x": 1}
        row2 = {"schema": 1, "run_id": "b", "x": 2}
        voicemode_telemetry.append_ledger_row(row1)
        voicemode_telemetry.append_ledger_row(row2)
        ledger_path = voicemode_telemetry.get_ledger_path()
        content = ledger_path.read_text()
        lines = [l for l in content.splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        import json
        self.assertIsInstance(json.loads(lines[0]), dict)
        self.assertIsInstance(json.loads(lines[1]), dict)
        self.assertEqual(json.loads(lines[0])["schema"], 1)
        self.assertEqual(json.loads(lines[1])["schema"], 1)

    def test_end_to_end_run_contract(self) -> None:
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = True

        fake_recorder = MagicMock()
        fake_recorder.started_at = 1000.0
        fake_recorder.recording = True
        fake_recorder.stop_to_wav.return_value = ([Path("/tmp/x.wav")], 1.23, True)

        model_state = MagicMock()
        seg_text = "hello world"

        with patch("signal.signal"), \
             patch("voice.Recorder", return_value=fake_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.load_model", return_value=model_state), \
             patch("voice.transcribe", return_value=(seg_text, model_state)), \
             patch("voice.insert_text", return_value=True), \
             patch("voice.time.sleep"), \
             patch("time.monotonic", advancing_monotonic(1000.0, 0.01)):
            result = voice.run_background_recording(args)
            self.assertEqual(result, 0)

        ledger_path = voicemode_telemetry.get_ledger_path()
        self.assertTrue(ledger_path.exists())
        lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        import json
        row = json.loads(lines[0])
        self.assertEqual(row["schema"], 1)
        self.assertEqual(row["source"], "stt")
        self.assertIn("run_id", row)
        self.assertEqual(row["outcome"], "success")
        self.assertIn("actual", row)
        self.assertIn("total_ms", row["actual"])
        self.assertIn("config", row)
        self.assertIn("model", row["config"])
        status_path = voicemode_telemetry.get_state_dir() / "status.json"
        self.assertFalse(status_path.exists())
