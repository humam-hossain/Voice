from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase, advancing_monotonic


def _setup_hermetic_check():
    import test_audio_chunking
    import test_hyprland_daemon
    import _hermetic
    for mod in [test_audio_chunking, test_hyprland_daemon]:
        for name, obj in vars(mod).items():
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
                if not issubclass(obj, _hermetic.TempXdgTestCase):
                    raise AssertionError(f"{mod.__name__}.{name} is not hermetic")


_setup_hermetic_check()


class TestStatusContract(TempXdgTestCase):
    def test_schema_is_closed_and_sized(self):
        s = voicemode_telemetry.build_status(pid=123, run_id='r1', state='transcribing', phase='load',
                                            started_at=1.0, updated_at=1000.0, audio_s=1.0, segments=1,
                                            segments_done=0, eta_remaining_s=5.0, eta_confidence='low',
                                            eta_source='prior')
        self.assertEqual(tuple(s.keys()), tuple(voicemode_telemetry.STATUS_V1_KEYS))
        for bad in ['text', 'transcript', 'clipboard']:
            with self.subTest(key=bad):
                br = dict(s)
                br[bad] = 'x'
                with self.assertRaises(ValueError):
                    voicemode_telemetry.validate_status(br)
        big = dict(s)
        big['run_id'] = 'x' * 900
        with self.assertRaises(ValueError):
            voicemode_telemetry.validate_status(big)
        with self.assertRaises(ValueError):
            voicemode_telemetry.validate_status(dict(s, state='listening'))
        with self.assertRaises(ValueError):
            voicemode_telemetry.validate_status(dict(s, phase='thinking'))
        s2 = voicemode_telemetry.build_status(pid=123, run_id='r1', state='transcribing', phase='load',
                                             started_at=1.0, updated_at=1000.0, eta_remaining_s=-0.5)
        self.assertEqual(s2['eta_remaining_s'], 0.0)
        self.assertEqual(s2['eta_epoch'], 1000.0)
    
    def test_publish_is_atomic_under_readers(self):
        state_dir = voicemode_telemetry.get_state_dir()
        errors = []
        def writer():
            for i in range(200):
                try:
                    voicemode_telemetry.publish_status(voicemode_telemetry.build_status(
                        pid=1, run_id='r', state='recording', phase='capture',
                        started_at=1.0, updated_at=time.time(), audio_s=float(i)
                    ))
                except Exception as e:
                    errors.append(e)
        def reader():
            for _ in range(2000):
                try:
                    st = voicemode_telemetry.read_status()
                    if st is not None:
                        self.assertIsInstance(st, dict)
                        self.assertEqual(st.get('schema'), 1)
                except Exception as e:
                    errors.append(e)
        tw = [__import__('threading').Thread(target=writer) for _ in range(1)]
        tr = [__import__('threading').Thread(target=reader) for _ in range(3)]
        for t in tw + tr: t.start()
        for t in tw + tr: t.join()
        self.assertEqual(errors, [])
        # no tmp files
        for f in state_dir.iterdir():
            self.assertNotIn('tmp', f.name)
    
    def test_transitions_publish_in_order(self):
        published = []
        orig = voicemode_telemetry.publish_status
        def rec(s):
            published.append(dict(s))
            return orig(s)
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = True
        fake_recorder = MagicMock()
        fake_recorder.started_at = 1000.0
        fake_recorder.recording = True
        fake_recorder.stop_to_wav.return_value = ([Path('/tmp/x.wav')], 1.23, True)
        model_state = MagicMock()
        ev = voice.TranscriptionEvidence(
            text='hello',
            model_state=model_state,
            decode_ms=10.0,
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
        with patch('voicemode_telemetry.publish_status', side_effect=rec), \
             patch('signal.signal'), \
             patch('voice.Recorder', return_value=fake_recorder), \
             patch('voice.play_cue'), \
             patch('voice.play_cue_async'), \
             patch('voice.load_model', return_value=model_state), \
             patch('voice.transcribe_timed', return_value=ev), \
             patch('voice.insert_text', return_value=True), \
             patch('voice.time.sleep'), \
             patch('time.monotonic', advancing_monotonic(1000.0, 0.01)):
            voice.run_background_recording(args)
        states = [p.get('state') for p in published]
        self.assertEqual(states[0], 'starting')
        self.assertIn('recording', states)
        self.assertIn('transcribing', states)
        self.assertIn('typing', states)
        for p in published:
            self.assertIn(p.get('phase'), voicemode_telemetry.STATUS_PHASES)
    
    def test_first_eta_exists_before_model_load(self):
        captured = {}
        ev = voice.TranscriptionEvidence(
            text='hello',
            model_state=MagicMock(),
            decode_ms=10.0,
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
        def cap_decode(model_state, path, call_args, **kwargs):
            captured['status'] = voicemode_telemetry.read_status()
            return ev
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = True
        fake_recorder = MagicMock()
        fake_recorder.started_at = 1000.0
        fake_recorder.recording = True
        fake_recorder.stop_to_wav.return_value = ([Path('/tmp/x.wav')], 5.0, True)
        with patch('signal.signal'), \
             patch('voice.Recorder', return_value=fake_recorder), \
             patch('voice.play_cue'), \
             patch('voice.play_cue_async'), \
             patch('voice.load_model', return_value=MagicMock()), \
             patch('voice.transcribe_timed', side_effect=cap_decode), \
             patch('voice.insert_text', return_value=True), \
             patch('voice.time.sleep'), \
             patch('time.monotonic', advancing_monotonic(1000.0, 0.01)):
            voice.run_background_recording(args)
        s = captured.get('status')
        self.assertIsNotNone(s)
        self.assertEqual(s['state'], 'transcribing')
        self.assertIn(s['eta_source'], ('prior', 'cold'))
        self.assertEqual(s['eta_confidence'], 'low')
        self.assertGreater(s['eta_remaining_s'], 0)
        self.assertGreaterEqual(s['eta_epoch'], s['updated_at'])
        self.assertGreaterEqual(s['segments'], 1)
    
    def test_heartbeat_while_recording(self):
        self.assertEqual(voicemode_telemetry.STATUS_HEARTBEAT_S, 5.0)
        self.assertTrue(0 < voicemode_telemetry.STATUS_TTL_S <= 60)
        published = []
        orig = voicemode_telemetry.publish_status
        def rec(s):
            published.append(dict(s))
            return orig(s)
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = True
        fake_recorder = MagicMock()
        fake_recorder.started_at = 1000.0
        fake_recorder.recording = True
        fake_recorder.stop_to_wav.return_value = ([Path('/tmp/x.wav')], 1.0, True)
        handlers = {}
        def fake_signal(sig, handler):
            handlers[sig] = handler
        sleep_calls = [0]
        def sleep_fn(t):
            sleep_calls[0] += 1
            if sleep_calls[0] >= 3:
                if voice.signal.SIGUSR1 in handlers:
                    handlers[voice.signal.SIGUSR1](voice.signal.SIGUSR1, None)
            return
        ev = voice.TranscriptionEvidence(
            text='hi',
            model_state=MagicMock(),
            decode_ms=10.0,
            fallback=False,
            failure_type=None,
            backend="cpu, int8",
            avg_logprob=-0.2,
            compression_ratio=1.0,
            no_speech_prob=0.01,
            temperature=0.0,
            vad_audio_s=1.0,
            decoder_segments=1,
            fallback_load_ms=None,
            audio_s=1.0,
        )
        with patch('voicemode_telemetry.STATUS_HEARTBEAT_S', 0.0), \
             patch('voicemode_telemetry.publish_status', side_effect=rec), \
             patch('signal.signal', side_effect=fake_signal), \
             patch('voice.Recorder', return_value=fake_recorder), \
             patch('voice.play_cue'), \
             patch('voice.play_cue_async'), \
             patch('voice.load_model', return_value=MagicMock()), \
             patch('voice.transcribe_timed', return_value=ev), \
             patch('voice.insert_text', return_value=True), \
             patch('voice.time.sleep', side_effect=sleep_fn), \
             patch('time.monotonic', advancing_monotonic(1000.0, 0.001)):
            voice.run_background_recording(args)
        rec_snaps = [p for p in published if p.get('state') == 'recording']
        self.assertGreaterEqual(len(rec_snaps), 3)
        for p in rec_snaps:
            self.assertGreaterEqual(p.get('audio_s', -1), 0)
    
    def test_terminal_exit_removes_status(self):
        # success
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = True
        fake_recorder = MagicMock()
        fake_recorder.started_at = 1000.0
        fake_recorder.recording = True
        fake_recorder.stop_to_wav.return_value = ([Path('/tmp/x.wav')], 1.0, True)
        ev = voice.TranscriptionEvidence(
            text='hi',
            model_state=MagicMock(),
            decode_ms=10.0,
            fallback=False,
            failure_type=None,
            backend="cpu, int8",
            avg_logprob=-0.2,
            compression_ratio=1.0,
            no_speech_prob=0.01,
            temperature=0.0,
            vad_audio_s=1.0,
            decoder_segments=1,
            fallback_load_ms=None,
            audio_s=1.0,
        )
        with patch('signal.signal'), patch('voice.Recorder', return_value=fake_recorder), \
             patch('voice.play_cue'), patch('voice.play_cue_async'), \
             patch('voice.load_model', return_value=MagicMock()), \
             patch('voice.transcribe_timed', return_value=ev), \
             patch('voice.insert_text', return_value=True), \
             patch('voice.time.sleep'), patch('time.monotonic', advancing_monotonic(1000.0, 0.01)):
            voice.run_background_recording(args)
        self.assertIsNone(voicemode_telemetry.read_status())
        self.assertFalse((voicemode_telemetry.get_state_dir() / 'status.json').exists())
    
    def test_status_is_advisory_pid_is_authority(self):
        from io import StringIO
        import sys
        voice.write_pid_state(4242, "recording")
        with patch('voice.process_alive', return_value=True), \
             patch('voice.read_pid', return_value=4242), \
             patch('voice.read_pid_state', return_value=(4242, "recording")):
            voicemode_telemetry.publish_status(voicemode_telemetry.build_status(
                pid=4242, run_id='x', state='recording', phase='capture', started_at=1.0
            ))
            f = StringIO()
            old = sys.stdout
            try:
                sys.stdout = f
                voice.print_status()
            finally:
                sys.stdout = old
            out1 = f.getvalue()
            (voicemode_telemetry.get_state_dir() / 'status.json').unlink(missing_ok=True)
            f = StringIO()
            old = sys.stdout
            try:
                sys.stdout = f
                voice.print_status()
            finally:
                sys.stdout = old
            out2 = f.getvalue()
            self.assertIn('recording pid 4242', out1)
            self.assertIn('recording pid 4242', out2)
        # no pid
        try:
            (voicemode_telemetry.get_state_dir() / 'pid').unlink()
        except Exception:
            pass
        with patch('voice.process_alive', return_value=False), \
             patch('voice.read_pid', return_value=None), \
             patch('voice.read_pid_state', return_value=(None, "idle")):
            voicemode_telemetry.publish_status(voicemode_telemetry.build_status(
                pid=1, run_id='x', state='recording', phase='capture', started_at=1.0
            ))
            f = StringIO()
            old = sys.stdout
            try:
                sys.stdout = f
                voice.print_status()
            finally:
                sys.stdout = old
            self.assertIn('idle', f.getvalue())
            self.assertTrue((voicemode_telemetry.get_state_dir() / 'status.json').exists())
    
    def test_expiry_marks_stale_snapshots(self):
        now = time.time()
        s = voicemode_telemetry.build_status(pid=1, run_id='x', state='recording', phase='capture', started_at=1.0, updated_at=now-60)
        self.assertTrue(voicemode_telemetry.status_expired(s, now=now))
        s2 = voicemode_telemetry.build_status(pid=1, run_id='x', state='recording', phase='capture', started_at=1.0)
        self.assertFalse(voicemode_telemetry.status_expired(s2, now=time.time()))
        self.assertTrue(voicemode_telemetry.status_expired({}, now=now))
        self.assertTrue(voicemode_telemetry.status_expired({'expires_at': None}, now=now))
        voicemode_telemetry.publish_status(s)
        self.assertIsNotNone(voicemode_telemetry.read_status())
    
    def test_status_write_respects_kill_switch(self):
        os.environ['VOICE_METRICS'] = 'off'
        try:
            args = voice.parse_args([])
            args.no_beep = True
            args.no_notify = True
            args.paste = True
            fake_recorder = MagicMock()
            fake_recorder.started_at = 1000.0
            fake_recorder.recording = True
            fake_recorder.stop_to_wav.return_value = ([Path('/tmp/x.wav')], 1.0, True)
            ev = voice.TranscriptionEvidence(
                text='hi',
                model_state=MagicMock(),
                decode_ms=10.0,
                fallback=False,
                failure_type=None,
                backend="cpu, int8",
                avg_logprob=-0.2,
                compression_ratio=1.0,
                no_speech_prob=0.01,
                temperature=0.0,
                vad_audio_s=1.0,
                decoder_segments=1,
                fallback_load_ms=None,
                audio_s=1.0,
            )
            with patch('signal.signal'), patch('voice.Recorder', return_value=fake_recorder), \
                 patch('voice.play_cue'), patch('voice.play_cue_async'), \
                 patch('voice.load_model', return_value=MagicMock()), \
                 patch('voice.transcribe_timed', return_value=ev), \
                 patch('voice.insert_text', return_value=True), \
                 patch('voice.time.sleep'), patch('time.monotonic', advancing_monotonic(1000.0, 0.01)):
                voice.run_background_recording(args)
            self.assertIsNone(voicemode_telemetry.read_status())
            self.assertFalse((voicemode_telemetry.get_state_dir() / 'status.json').exists())
        finally:
            os.environ.pop('VOICE_METRICS', None)

    def test_transcribed_audio_s_schema_acceptance(self):
        """transcribed_audio_s is accepted in STATUS_V1_KEYS and round-trips through build/validate."""
        self.assertIn('transcribed_audio_s', voicemode_telemetry.STATUS_V1_KEYS)
        s = voicemode_telemetry.build_status(
            pid=123, run_id='r1', state='recording', phase='capture',
            started_at=1.0, updated_at=1000.0, transcribed_audio_s=5.5,
        )
        self.assertEqual(s['transcribed_audio_s'], 5.5)
        # None is accepted
        s2 = voicemode_telemetry.build_status(
            pid=123, run_id='r1', state='recording', phase='capture',
            started_at=1.0, updated_at=1000.0, transcribed_audio_s=None,
        )
        self.assertIsNone(s2['transcribed_audio_s'])
        # Default is None
        s3 = voicemode_telemetry.build_status(
            pid=123, run_id='r1', state='recording', phase='capture',
            started_at=1.0, updated_at=1000.0,
        )
        self.assertIsNone(s3['transcribed_audio_s'])

    def test_transcribed_audio_s_negative_clamped(self):
        """Negative transcribed_audio_s is clamped to 0.0."""
        s = voicemode_telemetry.build_status(
            pid=123, run_id='r1', state='recording', phase='capture',
            started_at=1.0, updated_at=1000.0, transcribed_audio_s=-1.0,
        )
        self.assertEqual(s['transcribed_audio_s'], 0.0)

    def test_transcribed_audio_s_json_serialization(self):
        """transcribed_audio_s appears in JSON output and survives round-trip."""
        s = voicemode_telemetry.build_status(
            pid=123, run_id='r1', state='recording', phase='capture',
            started_at=1.0, updated_at=1000.0, transcribed_audio_s=12.345,
        )
        j = json.dumps(s)
        parsed = json.loads(j)
        self.assertAlmostEqual(parsed['transcribed_audio_s'], 12.345, places=3)
