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
        import voicemode_telemetry as t
        row1 = t.build_record(run_id="a", install_id=t.get_install_id(), ts_start=1.0, ts_end=2.0, outcome="success",
                             config={"model": "m", "device": "cpu", "compute_type": "int8", "beam_size": 1,
                                     "vad_filter": True, "language": "en", "chunk_s": 180.0})
        row2 = t.build_record(run_id="b", install_id=t.get_install_id(), ts_start=1.0, ts_end=2.0, outcome="success",
                             config={"model": "m", "device": "cpu", "compute_type": "int8", "beam_size": 1,
                                     "vad_filter": True, "language": "en", "chunk_s": 180.0})
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
        ev = voice.TranscriptionEvidence(
            text=seg_text,
            model_state=model_state,
            decode_ms=15.0,
            fallback=False,
            failure_type=None,
            backend="cpu, int8",
            avg_logprob=-0.2,
            compression_ratio=1.0,
            no_speech_prob=0.01,
            temperature=0.0,
            vad_audio_s=1.23,
            decoder_segments=1,
            fallback_load_ms=None,
            audio_s=1.23,
        )

        with patch("signal.signal"), \
             patch("voice.Recorder", return_value=fake_recorder), \
             patch("voice.play_cue"), \
             patch("voice.play_cue_async"), \
             patch("voice.load_model", return_value=model_state), \
             patch("voice.transcribe_timed", return_value=ev), \
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


from _hermetic import TempXdgTestCase
import voicemode_telemetry as t
import json
import os
from pathlib import Path


class TestSchemaV1(TempXdgTestCase):
    def test_every_top_level_key_present(self):
        r = t.build_record(run_id='r1', install_id=t.get_install_id(), ts_start=1.0, ts_end=2.0,
                          outcome='success', audio_s=1.0, chars_out=10, chars_typed=9,
                          config={'model': 'm', 'device': 'cpu', 'compute_type': 'int8',
                                  'beam_size': 1, 'vad_filter': True, 'language': 'en', 'chunk_s': 180.0},
                          backend='cpu, int8', segments=[{'idx': 0, 'audio_s': 1.0, 'decode_ms': 100, 'chars': 10,
                                                          'ok': True, 'fallback': False, 'avg_logprob': -0.1,
                                                          'compression_ratio': 1.2, 'no_speech_prob': 0.01,
                                                          'temperature': 0.0, 'vad_audio_s': 1.0, 'error_type': None}])
        self.assertEqual(set(r.keys()), set(t.SCHEMA_V1_KEYS))
        self.assertIn('shown_s', r['predicted'])
        self.assertIn('avg_logprob', r['segments'][0])
        self.assertEqual(r['tts'], t.tts_reserved())
        self.assertEqual(r['source'], 'stt')


class TestPrivacy(TempXdgTestCase):
    def test_allowlist_rejects_extra_keys(self):
        r = t.build_record(run_id='r1', install_id=t.get_install_id(), ts_start=1.0, ts_end=2.0,
                          outcome='success', config={'model': 'm', 'device': 'cpu', 'compute_type': 'int8',
                                                    'beam_size': 1, 'vad_filter': True, 'language': 'en', 'chunk_s': 180.0})
        for bad in ['transcript', 'text', 'prompt', 'hotwords', 'clipboard', 'argv', 'cwd', 'hostname', 'username', 'path']:
            with self.subTest(key=bad):
                br = dict(r)
                br[bad] = 'x'
                with self.assertRaises(ValueError):
                    t.validate_record(br)
    
    def test_no_disclosure_patterns(self):
        r = t.build_record(run_id='r1', install_id=t.get_install_id(), ts_start=1.0, ts_end=2.0,
                          outcome='success', chars_out=5,
                          config={'model': 'm', 'device': 'cpu', 'compute_type': 'int8',
                                  'beam_size': 1, 'vad_filter': True, 'language': 'en', 'chunk_s': 180.0})
        import re
        line = json.dumps(r)
        sentinel = "SECRET_TRANSCRIPT_12345"
        self.assertNotIn(sentinel, line)
        for pat in [r'/home/', r'/tmp/', r'/usr/', r'\bpid \d+', r'@[a-z0-9.-]+\.(com|org|net)',
                    r'\b[a-z0-9._%+-]+@[a-z0-9.-]+\b', r'/etc/']:
            self.assertIsNone(re.search(pat, line))
        def walk(d):
            if isinstance(d, dict):
                for k, v in d.items():
                    self.assertNotEqual(k, 'words')
                    self.assertNotIn('text', k)
                    walk(v)
            elif isinstance(d, list):
                for i in d:
                    walk(i)
        walk(r)


class TestCharsOnly(TempXdgTestCase):
    def test_chars_counts(self):
        r = t.build_record(run_id='r1', install_id=t.get_install_id(), ts_start=1.0, ts_end=2.0,
                          outcome='success', chars_out=11, chars_typed=0,
                          config={'model': 'm', 'device': 'cpu', 'compute_type': 'int8',
                                  'beam_size': 1, 'vad_filter': True, 'language': 'en', 'chunk_s': 180.0})
        self.assertEqual(r['chars_out'], 11)
        self.assertEqual(r['chars_typed'], 0)
        self.assertFalse(r['insert_ok'])


class TestInstallId(TempXdgTestCase):
    def test_stable_and_unique(self):
        id1 = t.get_install_id()
        id2 = t.get_install_id()
        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 32)
        all(c in '0123456789abcdef' for c in id1)
        state_dir = t.get_state_dir()
        self.assertTrue((state_dir / 'install_salt').exists())
        self.assertTrue((state_dir / 'install_id').exists())
        # modes
        self.assertEqual((state_dir / 'install_id').stat().st_mode & 0o777, 0o600)
        self.assertEqual((state_dir / 'install_salt').stat().st_mode & 0o777, 0o600)


class TestKillSwitchCoversEverything(TempXdgTestCase):
    def test_kill_switch(self):
        import os
        os.environ['VOICE_METRICS'] = 'off'
        r = {'schema': 1}
        self.assertFalse(t.append_ledger_row(r))
        self.assertFalse(t.publish_status({}))
        h = t.ledger_health()
        self.assertFalse(h['enabled'])
        tmp = Path(self.xdg_root)
        self.assertFalse((tmp / 'state' / 'voicemode' / 'metrics.jsonl').exists())
        os.environ.pop('VOICE_METRICS', None)
