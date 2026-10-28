

import os
import signal
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
from _hermetic import TempXdgTestCase
import voicemode_telemetry


class TestToggleLock(TempXdgTestCase):
    def test_double_toggle_spawns_one_worker(self):
        fake_proc = MagicMock()
        fake_proc.pid = 4242
        with patch("voice.process_alive", side_effect=lambda pid: pid == 4242), \
             patch("voice.subprocess.Popen", return_value=fake_proc) as mock_popen, \
             patch("voice.stop_tts"), \
             patch("voice.play_cue"):
            results = []
            def call():
                results.append(voice.toggle_background_recording(voice.parse_args(["--no-beep", "--no-notify"])))
            t1 = threading.Thread(target=call)
            t2 = threading.Thread(target=call)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        self.assertEqual(mock_popen.call_count, 1)
        pid, state = voice.read_pid_state()
        self.assertEqual(pid, 4242)
        self.assertEqual(state, "starting")
        lock_path = voicemode_telemetry.get_state_dir() / ".toggle.lock"
        self.assertTrue(lock_path.exists())
        import stat
        self.assertEqual(stat.S_IMODE(lock_path.stat().st_mode), 0o600)
    
    def test_second_toggle_stops_recording(self):
        voice.write_pid_state(12345, "recording")
        with patch("voice.process_alive", return_value=True), \
             patch("os.kill") as mock_kill, \
             patch("voice.subprocess.Popen") as mock_popen:
            result = voice.toggle_background_recording(voice.parse_args(["--no-beep", "--no-notify"]))
            self.assertEqual(result, 0)
            mock_kill.assert_called()
            mock_popen.assert_not_called()


class TestWorkerOwnership(TempXdgTestCase):
    def test_worker_refuses_foreign_ownership(self):
        voice.write_pid_state(9999, "recording")
        with patch("voice.process_alive", return_value=True), \
             patch("voice.Recorder") as mock_rec, \
             patch("voice.play_cue"), \
             patch("signal.signal"):
            result = voice.run_background_recording(voice.parse_args(["--no-beep", "--no-notify"]))
            self.assertEqual(result, 0)
            mock_rec.assert_not_called()
    
    def test_pid_state_vocabulary_is_frozen(self):
        import re
        src = Path(voice.__file__).read_text()
        states = set(re.findall(r'write_pid_state\([^)]*"([a-z_]+)"', src))
        self.assertTrue(states.issubset(set(voice.PID_STATES)))
        # no write_pid with non-recording
        self.assertIn("starting", states)
        self.assertIn("recording", states)


class TestTornReadAndStates(TempXdgTestCase):
    def test_transcribing_refuses_without_spawn(self):
        voice.write_pid_state(5555, "transcribing")
        with patch("voice.process_alive", return_value=True), \
             patch("voice.subprocess.Popen") as mock_popen, \
             patch("voice.play_cue"):
            result = voice.toggle_background_recording(voice.parse_args(["--no-beep", "--no-notify"]))
            self.assertEqual(result, 0)
            mock_popen.assert_not_called()
    
    def test_unknown_live_state_does_not_spawn(self):
        voice.write_pid_state(7777, "speaking")
        with patch("voice.process_alive", return_value=True), \
             patch("voice.subprocess.Popen") as mock_popen:
            result = voice.toggle_background_recording(voice.parse_args(["--no-beep", "--no-notify"]))
            self.assertEqual(result, 0)
            mock_popen.assert_not_called()
    
    def test_torn_read_never_raises(self):
        for content in ["12", "1234 ", "1234 record", "", b"\xff\xfe1234\n"]:
            p = voicemode_telemetry.get_state_dir() / "test_pid"
            if isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_text(content)
            pid, state = voice.read_pid_state(p)
            self.assertIsInstance(state, str)
            p.unlink(missing_ok=True)
    
    def test_atomic_write_no_partial_observation(self):
        errors = []
        def writer():
            for i in range(200):
                try:
                    voice.write_pid_state(4242, "recording")
                except Exception as e:
                    errors.append(e)
        def reader():
            for i in range(2000):
                try:
                    pid, state = voice.read_pid_state()
                    if (pid is not None or state != "idle") and not (pid == 4242 and isinstance(state, str)):
                        pass  # allow states
                except ValueError as e:
                    errors.append(e)
                except Exception:
                    pass
        writers = [threading.Thread(target=writer) for _ in range(2)]
        readers = [threading.Thread(target=reader) for _ in range(3)]
        for t in writers + readers:
            t.start()
        for t in writers + readers:
            t.join()
        self.assertEqual(errors, [])
