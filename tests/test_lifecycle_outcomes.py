from __future__ import annotations

import os
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase


class TestLifecycleOutcomes(TempXdgTestCase):
    def test_success_produces_exactly_one_row(self) -> None:
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = False

        fake_recorder = MagicMock()
        fake_recorder.recording = True
        fake_recorder.started_at = time.monotonic()
        fake_recorder.stop_to_wav.return_value = ([Path("/tmp/test.wav")], 2.5, False)

        ev = voice.TranscriptionEvidence(
            text="success transcript",
            model_state=MagicMock(),
            decode_ms=20.0,
            fallback=False,
            failure_type=None,
            backend="cpu, int8",
            avg_logprob=-0.2,
            compression_ratio=1.0,
            no_speech_prob=0.01,
            temperature=0.0,
            vad_audio_s=2.5,
            decoder_segments=1,
            fallback_load_ms=None,
            audio_s=2.5,
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
             patch("voice.load_model", return_value=MagicMock()), \
             patch("voice.transcribe_timed", return_value=ev), \
             patch("voice.time.sleep", side_effect=stop_now):
            code = voice.run_background_recording(args)

        self.assertEqual(code, 0)
        rows = list(voicemode_telemetry.read_ledger_rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "success")
        self.assertEqual(rows[0]["chars_out"], len("success transcript"))
        self.assertFalse((voicemode_telemetry.get_state_dir() / "status.json").exists())
        self.assertFalse(voice.PID_FILE.exists())

    def test_cancel_produces_exactly_one_row(self) -> None:
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
             patch("voice.load_model", return_value=MagicMock()), \
             patch("voice.time.sleep", side_effect=cancel_now):
            code = voice.run_background_recording(args)

        self.assertEqual(code, 0)
        rows = list(voicemode_telemetry.read_ledger_rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "cancelled")
        self.assertFalse((voicemode_telemetry.get_state_dir() / "status.json").exists())
        self.assertFalse(voice.PID_FILE.exists())

    def test_error_produces_exactly_one_row(self) -> None:
        args = voice.parse_args([])
        args.no_beep = True
        args.no_notify = True
        args.paste = False

        fake_recorder = MagicMock()
        fake_recorder.recording = True
        fake_recorder.started_at = time.monotonic()
        fake_recorder.stop_to_wav.side_effect = RuntimeError("Fatal disk full")

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
             patch("voice.load_model", return_value=MagicMock()), \
             patch("voice.report_stt_failure"), \
             patch("voice.time.sleep", side_effect=stop_now):
            code = voice.run_background_recording(args)

        self.assertEqual(code, 1)
        rows = list(voicemode_telemetry.read_ledger_rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "error")
        self.assertEqual(rows[0]["error_stage"], "WAV finalization")
        self.assertFalse((voicemode_telemetry.get_state_dir() / "status.json").exists())
        self.assertFalse(voice.PID_FILE.exists())

    def test_watchdog_timeout_produces_terminal_row_and_cleans_up(self) -> None:
        args = voice.parse_args([])
        pid = 7777
        voice.write_pid_state(pid, "transcribing")

        status_obj = voicemode_telemetry.build_status(
            pid=pid,
            run_id="run-watchdog-1",
            state="transcribing",
            phase="decode",
            started_at=time.time() - 35,
            audio_s=30.0,
        )
        voicemode_telemetry.publish_status(status_obj)

        run_state = {
            "lock": threading.Lock(),
            "finalized": False,
            "pid": pid,
            "run_id": "run-watchdog-1",
            "ts_start": time.time() - 35,
            "t_start": time.monotonic() - 35,
            "args": args,
            "outcome": "success",
            "audio_s": 30.0,
            "results": {},
        }

        expired = threading.Event()
        wav_path = Path("/tmp/hung.wav")

        with patch("voice.report_stt_failure"), \
             patch("os._exit") as mock_exit:
            voice.transcription_watchdog_handler(
                run_state,
                args,
                wav_path,
                30.0,
                time.monotonic() - 35,
                expired,
            )
            mock_exit.assert_called_once_with(1)

        self.assertTrue(expired.is_set())
        rows = list(voicemode_telemetry.read_ledger_rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "watchdog_timeout")
        self.assertEqual(rows[0]["error_stage"], "Whisper transcription")
        self.assertFalse((voicemode_telemetry.get_state_dir() / "status.json").exists())
        self.assertFalse(voice.PID_FILE.exists())

    def test_dead_worker_reconciled_as_abandoned(self) -> None:
        pid = 8888
        voice.write_pid_state(pid, "recording")
        status_obj = voicemode_telemetry.build_status(
            pid=pid,
            run_id="run-abandoned-1",
            state="recording",
            phase="capture",
            started_at=time.time() - 10,
            audio_s=10.0,
        )
        voicemode_telemetry.publish_status(status_obj)

        with patch("voice.process_alive", return_value=False):
            reconciled = voice.reconcile_abandoned_run()

        self.assertTrue(reconciled)
        rows = list(voicemode_telemetry.read_ledger_rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "abandoned")
        self.assertEqual(rows[0]["error_stage"], "capture")
        self.assertEqual(rows[0]["run_id"], "run-abandoned-1")
        self.assertFalse((voicemode_telemetry.get_state_dir() / "status.json").exists())
        self.assertFalse(voice.PID_FILE.exists())

    def test_live_worker_not_reconciled(self) -> None:
        pid = 9999
        voice.write_pid_state(pid, "recording")
        status_obj = voicemode_telemetry.build_status(
            pid=pid,
            run_id="run-live-1",
            state="recording",
            phase="capture",
            started_at=time.time() - 2,
            audio_s=2.0,
        )
        voicemode_telemetry.publish_status(status_obj)

        with patch("voice.process_alive", return_value=True):
            reconciled = voice.reconcile_abandoned_run()

        self.assertFalse(reconciled)
        rows = list(voicemode_telemetry.read_ledger_rows())
        self.assertEqual(len(rows), 0)
        self.assertTrue((voicemode_telemetry.get_state_dir() / "status.json").exists())
        self.assertTrue(voice.PID_FILE.exists())

    def test_expired_snapshot_cleared_without_row(self) -> None:
        pid = 6666
        voice.write_pid_state(pid, "recording")
        # Stale snapshot: updated 60s ago (> 30s TTL)
        status_obj = voicemode_telemetry.build_status(
            pid=pid,
            run_id="run-expired-1",
            state="recording",
            phase="capture",
            started_at=time.time() - 70,
            updated_at=time.time() - 60,
            audio_s=10.0,
        )
        voicemode_telemetry.publish_status(status_obj)

        with patch("voice.process_alive", return_value=False):
            reconciled = voice.reconcile_abandoned_run()

        self.assertTrue(reconciled)
        rows = list(voicemode_telemetry.read_ledger_rows())
        # Expired snapshots must not generate ledger rows
        self.assertEqual(len(rows), 0)
        self.assertFalse((voicemode_telemetry.get_state_dir() / "status.json").exists())
        self.assertFalse(voice.PID_FILE.exists())


if __name__ == "__main__":
    unittest.main()
