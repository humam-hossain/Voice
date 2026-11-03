from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase


def format_duration(sec: float | int) -> str:
    """Python reference implementation of Voice.qml formatDuration()."""
    s_int = max(0, int(sec))
    m = s_int // 60
    s = s_int % 60
    return f"{m}:{s:02d}"


def is_safe_report_path(runtime_dir: str, target: str) -> bool:
    """Python reference validation matching Voice.qml openReport() safety check."""
    if not (target.startswith(runtime_dir) and target.endswith("report.html")):
        return False
    try:
        resolved = Path(target).resolve()
        resolved_runtime = Path(runtime_dir).resolve()
        return (resolved_runtime == resolved.parent or resolved_runtime in resolved.parents) and resolved.name == "report.html"
    except Exception:
        return False


def parse_recent_runs_simulation(text: str, max_count: int = 10) -> list[dict]:
    """Python simulation matching VoicePopup.qml parseRecentRuns()."""
    if not text or not isinstance(text, str):
        return []
    lines = text.strip().split("\n")
    result = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if not isinstance(item, dict):
                continue
            audio_s = item.get("audio_s")
            rtf_val = item.get("rtf")
            if rtf_val is None and item.get("actual", {}).get("decode_ms") is not None and audio_s and float(audio_s) > 0:
                rtf_val = (float(item["actual"]["decode_ms"]) / 1000.0) / float(audio_s)

            outcome = item.get("outcome") or ("failed" if item.get("failed") is True or bool(item.get("failure_reason")) else "success")
            is_cancelled = outcome == "cancelled"
            is_failed = outcome in ("failed", "error") or item.get("failed") is True or bool(item.get("failure_reason"))
            is_outlier = bool(item.get("is_outlier") or item.get("outlier"))
            duration_str = f"{float(audio_s):.1f}s" if audio_s is not None else "--"

            char_val = item.get("chars_out") if item.get("chars_out") is not None else (
                item.get("chars_typed") if item.get("chars_typed") is not None else (
                    item.get("chars") if item.get("chars") is not None else item.get("characters")
                )
            )
            chars_str = str(char_val) if char_val is not None else "--"
            rtf_str = f"{float(rtf_val):.2f}x" if rtf_val is not None else "--"
            result.append({
                "runId": item.get("run_id", ""),
                "duration": duration_str,
                "chars": chars_str,
                "rtf": rtf_str,
                "outlier": is_outlier,
                "isCancelled": is_cancelled,
                "isFailed": is_failed,
                "success": not is_cancelled and not is_failed,
                "outcome": outcome,
            })
            if len(result) >= max_count:
                break
        except Exception:
            continue
    return result


class TestPillIntegrationSimulation(TempXdgTestCase):
    """End-to-end integration simulation testing the status contract and pill expectations."""

    def test_full_lifecycle_status_snapshots(self):
        """Simulate status progression: idle -> recording -> concurrent decode -> tail decode -> typing -> idle."""
        runtime_dir_str = str(self.run_dir / "voice-stt")
        pid = 12345
        run_id = "test_run_sim_01"
        start_time = 1000.0

        # Step 1: Idle -> Recording (initial capture)
        voice.write_pid_state(pid, "recording")
        status_rec_init = voicemode_telemetry.build_status(
            pid=pid,
            run_id=run_id,
            state="recording",
            phase="capture",
            started_at=start_time,
            audio_s=0.0,
            segments=0,
            segments_done=0,
            transcribed_audio_s=0.0,
        )
        voicemode_telemetry.validate_status(status_rec_init)
        voicemode_telemetry.publish_status(status_rec_init)

        read_st1 = voicemode_telemetry.read_status()
        self.assertIsNotNone(read_st1)
        self.assertEqual(read_st1["state"], "recording")
        self.assertEqual(read_st1["phase"], "capture")
        self.assertEqual(read_st1["audio_s"], 0.0)
        self.assertEqual(read_st1["transcribed_audio_s"], 0.0)
        # Dual timer before chunk decode
        dual_timer_1 = f"{format_duration(read_st1['audio_s'])} | {format_duration(read_st1['transcribed_audio_s'])}"
        self.assertEqual(dual_timer_1, "0:00 | 0:00")

        # Step 2: Concurrent chunk decode while still recording
        status_rec_chunk = voicemode_telemetry.build_status(
            pid=pid,
            run_id=run_id,
            state="recording",
            phase="capture",
            started_at=start_time,
            audio_s=5.0,
            segments=2,
            segments_done=1,
            transcribed_audio_s=3.2,
        )
        voicemode_telemetry.validate_status(status_rec_chunk)
        voicemode_telemetry.publish_status(status_rec_chunk)

        read_st2 = voicemode_telemetry.read_status()
        self.assertIsNotNone(read_st2)
        self.assertEqual(read_st2["state"], "recording")
        self.assertEqual(read_st2["audio_s"], 5.0)
        self.assertEqual(read_st2["transcribed_audio_s"], 3.2)
        # Concurrent decode triggers breathing color pulse in QML
        is_concurrently_decoding = (read_st2["state"] == "recording" and (read_st2["transcribed_audio_s"] or 0) > 0)
        self.assertTrue(is_concurrently_decoding)
        dual_timer_2 = f"{format_duration(read_st2['audio_s'])} | {format_duration(read_st2['transcribed_audio_s'])}"
        self.assertEqual(dual_timer_2, "0:05 | 0:03")

        # Step 3: Recording stop -> Transcribing (tail decode)
        voice.write_pid_state(pid, "transcribing")
        status_tail = voicemode_telemetry.build_status(
            pid=pid,
            run_id=run_id,
            state="transcribing",
            phase="decode",
            started_at=start_time,
            audio_s=6.5,
            segments=2,
            segments_done=2,
            transcribed_audio_s=6.5,
            report_path=f"{runtime_dir_str}/report.html",
        )
        voicemode_telemetry.validate_status(status_tail)
        voicemode_telemetry.publish_status(status_tail)

        read_st3 = voicemode_telemetry.read_status()
        self.assertIsNotNone(read_st3)
        self.assertEqual(read_st3["state"], "transcribing")
        self.assertEqual(read_st3["phase"], "decode")
        self.assertEqual(read_st3["audio_s"], 6.5)
        self.assertEqual(read_st3["transcribed_audio_s"], 6.5)
        # 3-bar progress timer during tail decode
        total_wall_clock_s = 7.2
        triple_timer_3 = (
            f"{format_duration(read_st3['audio_s'])} | "
            f"{format_duration(read_st3['transcribed_audio_s'])} | "
            f"{format_duration(total_wall_clock_s)}"
        )
        self.assertEqual(triple_timer_3, "0:06 | 0:06 | 0:07")
        # Visual styling checks for transcribing
        effective_state_3 = read_st3["state"]
        is_clickable_3 = effective_state_3 in ("transcribing", "typing", "wrapup")
        self.assertTrue(is_clickable_3)

        # Step 4: Transcribing -> Typing / Text Injection
        voice.write_pid_state(pid, "typing")
        status_typing = voicemode_telemetry.build_status(
            pid=pid,
            run_id=run_id,
            state="typing",
            phase="insert",
            started_at=start_time,
            audio_s=6.5,
            segments=2,
            segments_done=2,
            transcribed_audio_s=6.5,
            report_path=f"{runtime_dir_str}/report.html",
        )
        voicemode_telemetry.validate_status(status_typing)
        voicemode_telemetry.publish_status(status_typing)

        read_st4 = voicemode_telemetry.read_status()
        self.assertIsNotNone(read_st4)
        self.assertEqual(read_st4["state"], "typing")
        self.assertEqual(read_st4["phase"], "insert")
        self.assertEqual(read_st4["audio_s"], 6.5)
        self.assertEqual(read_st4["transcribed_audio_s"], 6.5)
        # Glyph shifts to 'edit' pen in QML during typing
        glyph_icon_4 = "edit" if read_st4["state"] in ("typing", "wrapup") else "graphic_eq"
        self.assertEqual(glyph_icon_4, "edit")

        # Step 5: Completion / Terminal exit
        voice.remove_pid(pid)
        status_file = Path(runtime_dir_str) / "status.json"
        if status_file.exists():
            status_file.unlink()

        self.assertIsNone(voicemode_telemetry.read_status())
        pid_read, state_read = voice.read_pid_state()
        self.assertIsNone(pid_read)
        self.assertEqual(state_read, "idle")

    def test_report_path_safety_validation(self):
        """Verify report path validation rejects directory traversal and outside paths."""
        runtime_dir_str = str(self.run_dir / "voice-stt")

        # Legitimate default report
        valid_report = f"{runtime_dir_str}/report.html"
        self.assertTrue(is_safe_report_path(runtime_dir_str, valid_report))

        # Traversal attempts
        traversal_attempts = [
            f"{runtime_dir_str}/../../etc/shadow",
            f"{runtime_dir_str}/../../report.html",
            f"{runtime_dir_str}/sub/../../report.html",
            "/etc/shadow",
            "/tmp/report.html",
            f"{runtime_dir_str}/report.html.bak",
            f"{runtime_dir_str}/report.html/evil",
            "http://127.0.0.1:8765/report.html",
            "file:///etc/passwd",
        ]
        for bad_path in traversal_attempts:
            with self.subTest(path=bad_path):
                self.assertFalse(
                    is_safe_report_path(runtime_dir_str, bad_path),
                    f"Path {bad_path} should have been rejected as unsafe"
                )

    def test_timer_formatting_contract(self):
        """Verify format_duration contract produces tabular-consistent mm:ss formats."""
        cases = [
            (0, "0:00"),
            (5, "0:05"),
            (59, "0:59"),
            (60, "1:00"),
            (65, "1:05"),
            (3599, "59:59"),
            (3600, "60:00"),
        ]
        for seconds, expected in cases:
            with self.subTest(sec=seconds):
                self.assertEqual(format_duration(seconds), expected)

        # Dual timer contract test
        dual = f"{format_duration(5)} | {format_duration(2)}"
        self.assertEqual(dual, "0:05 | 0:02")

        # 3-bar progress timer contract test
        triple = f"{format_duration(6)} | {format_duration(6)} | {format_duration(8)}"
        self.assertEqual(triple, "0:06 | 0:06 | 0:08")

    def test_qml_timer_intervals_and_parity(self):
        """Verify 5000ms intervals on wrapUpTimer and typingLingerTimer with zero dotfiles diff."""
        dotfiles_voice = Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml")
        dotfiles_pill = Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml")
        vendored_voice = Path("integrations/quickshell/Voice.qml")
        vendored_pill = Path("integrations/quickshell/VoicePill.qml")

        self.assertTrue(dotfiles_voice.exists(), "dotfiles Voice.qml must exist")
        self.assertTrue(dotfiles_pill.exists(), "dotfiles VoicePill.qml must exist")
        self.assertTrue(vendored_voice.exists(), "vendored Voice.qml must exist")
        self.assertTrue(vendored_pill.exists(), "vendored VoicePill.qml must exist")

        # Byte-identical parity (D-05)
        self.assertEqual(dotfiles_voice.read_bytes(), vendored_voice.read_bytes(), "Voice.qml divergence detected")
        self.assertEqual(dotfiles_pill.read_bytes(), vendored_pill.read_bytes(), "VoicePill.qml divergence detected")

        # 5000ms intervals (D-01)
        voice_text = vendored_voice.read_text(encoding="utf-8")
        pill_text = vendored_pill.read_text(encoding="utf-8")

        # typingLingerTimer in Voice.qml
        linger_match = re.search(r'id:\s*typingLingerTimer\s+interval:\s*(\d+)', voice_text)
        self.assertIsNotNone(linger_match, "typingLingerTimer not found in Voice.qml")
        self.assertEqual(int(linger_match.group(1)), 5000, "typingLingerTimer interval must be 5000ms")

        # wrapUpTimer in VoicePill.qml
        wrapup_match = re.search(r'id:\s*wrapUpTimer\s+interval:\s*(\d+)', pill_text)
        self.assertIsNotNone(wrapup_match, "wrapUpTimer not found in VoicePill.qml")
        self.assertEqual(int(wrapup_match.group(1)), 5000, "wrapUpTimer interval must be 5000ms")

    def test_total_duration_freezes_during_typing(self):
        """Simulate Voice.qml updateDuration: total elapsed freezes upon entering typing (D-02)."""
        class VoiceDurationSimulator:
            def __init__(self):
                self.overallState = "idle"
                self.startTime = 0.0
                self.totalElapsedSeconds = 0
                self.formattedTotalDuration = "0:00"
                self.typingDurationCaptured = False

            def updateDuration(self, now: float):
                if self.overallState in ("recording", "speaking"):
                    self.typingDurationCaptured = False
                    if self.startTime <= 0:
                        self.startTime = now
                    diff = max(0.0, now - self.startTime)
                    self.totalElapsedSeconds = int(diff)
                    self.formattedTotalDuration = format_duration(self.totalElapsedSeconds)
                elif self.overallState == "transcribing":
                    if self.startTime > 0:
                        diff = max(0.0, now - self.startTime)
                        self.totalElapsedSeconds = int(diff)
                        self.formattedTotalDuration = format_duration(self.totalElapsedSeconds)
                elif self.overallState == "typing":
                    if self.startTime > 0 and not self.typingDurationCaptured:
                        diff = max(0.0, now - self.startTime)
                        self.totalElapsedSeconds = int(diff)
                        self.formattedTotalDuration = format_duration(self.totalElapsedSeconds)
                        self.typingDurationCaptured = True

        sim = VoiceDurationSimulator()
        # Start recording at t = 1000.0
        sim.overallState = "recording"
        sim.updateDuration(1000.0)
        self.assertEqual(sim.totalElapsedSeconds, 0)
        self.assertEqual(sim.formattedTotalDuration, "0:00")

        # Still recording at t = 1005.0
        sim.updateDuration(1005.0)
        self.assertEqual(sim.totalElapsedSeconds, 5)
        self.assertEqual(sim.formattedTotalDuration, "0:05")

        # Transition to transcribing at t = 1005.1
        sim.overallState = "transcribing"
        sim.updateDuration(1007.2)
        self.assertEqual(sim.totalElapsedSeconds, 7)
        self.assertEqual(sim.formattedTotalDuration, "0:07")

        # Transition to typing at t = 1007.8
        sim.overallState = "typing"
        sim.updateDuration(1007.8)
        self.assertEqual(sim.totalElapsedSeconds, 7)
        self.assertEqual(sim.formattedTotalDuration, "0:07")
        self.assertTrue(sim.typingDurationCaptured)

        # During typing at t = 1010.5 (text insertion happening)
        sim.updateDuration(1010.5)
        self.assertEqual(sim.totalElapsedSeconds, 7, "Total duration must freeze during typing")
        self.assertEqual(sim.formattedTotalDuration, "0:07")

        # During 5s linger at t = 1012.8
        sim.updateDuration(1012.8)
        self.assertEqual(sim.totalElapsedSeconds, 7, "Total duration must remain frozen during linger")
        self.assertEqual(sim.formattedTotalDuration, "0:07")

    def test_toggle_recording_atomically_transitions_to_transcribing(self):
        """Verify toggle_background_recording atomically writes transcribing on SIGUSR1 stop (D-03)."""
        pid = 98765
        voice.write_pid_state(pid, "recording")
        read_pid, read_state = voice.read_pid_state()
        self.assertEqual(read_pid, pid)
        self.assertEqual(read_state, "recording")

        args = voice.parse_args(["--no-beep", "--no-notify"])
        with patch("voice.process_alive", return_value=True), \
             patch("os.kill") as mock_kill, \
             patch("voice.subprocess.Popen") as mock_popen:
            res = voice.toggle_background_recording(args)
            self.assertEqual(res, 0)
            mock_kill.assert_called_once_with(pid, signal.SIGUSR1)
            mock_popen.assert_not_called()

        # PID file must have transitioned to transcribing
        after_pid, after_state = voice.read_pid_state()
        self.assertEqual(after_pid, pid)
        self.assertEqual(after_state, "transcribing")

    def test_toggle_recording_rejects_during_transcribing_and_typing(self):
        """Verify toggle_background_recording rejects re-entry during transcribing or typing (D-04)."""
        pid = 98765
        args = voice.parse_args([])

        for busy_state in ("transcribing", "typing"):
            with self.subTest(state=busy_state):
                voice.write_pid_state(pid, busy_state)
                with patch("voice.process_alive", return_value=True), \
                     patch("voice.play_cue") as mock_cue, \
                     patch("voice.notify") as mock_notify, \
                     patch("voice.subprocess.Popen") as mock_popen:
                    res = voice.toggle_background_recording(args)
                    self.assertEqual(res, 0)
                    mock_popen.assert_not_called()
                    mock_cue.assert_called_once_with(args, "error")
                    mock_notify.assert_called_once()
                    self.assertIn("Cannot start recording: transcription/typing in progress.", mock_notify.call_args[0][1])

                # PID state unchanged
                cur_pid, cur_state = voice.read_pid_state()
                self.assertEqual(cur_pid, pid)
                self.assertEqual(cur_state, busy_state)

    def test_qml_contains_no_rm_commands(self):
        """Verify Voice QML files never execute rm or dangerous shell commands."""
        for path in (
            Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml"),
            Path("integrations/quickshell/Voice.qml"),
            Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml"),
            Path("integrations/quickshell/VoicePill.qml"),
            Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePopup.qml"),
            Path("integrations/quickshell/VoicePopup.qml"),
        ):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r'\brm\s+', text), f"{path} must not contain any rm commands")
            self.assertNotIn("sh -c", text, f"{path} must not contain raw shell invocations")
            self.assertNotIn("bash -c", text, f"{path} must not contain raw shell invocations")

    def test_total_duration_s_in_status_contract(self):
        """Verify total_duration_s is published and tracked in status.json."""
        self.assertIn("total_duration_s", voicemode_telemetry.STATUS_V1_KEYS)
        s = voicemode_telemetry.build_status(
            pid=123,
            run_id="run_tot_01",
            state="recording",
            phase="capture",
            started_at=1000.0,
            audio_s=4.5,
            total_duration_s=4.5,
        )
        self.assertEqual(s["total_duration_s"], 4.5)
        voicemode_telemetry.validate_status(s)

    def test_toggle_recovers_worker_when_pid_file_missing(self):
        """Verify toggle_background_recording recovers active worker from process table when recorder.pid is absent."""
        voice.remove_pid()
        args = voice.parse_args([])

        with patch("voice.find_active_recorder_pid", return_value=54321), \
             patch("voice.process_alive", return_value=True), \
             patch("os.kill") as mock_kill, \
             patch("voice.subprocess.Popen") as mock_popen:
            res = voice.toggle_background_recording(args)
            self.assertEqual(res, 0)
            mock_kill.assert_called_once_with(54321, signal.SIGUSR1)
            mock_popen.assert_not_called()

        pid, state = voice.read_pid_state()
        self.assertEqual(pid, 54321)
        self.assertEqual(state, "transcribing")

    def test_popup_components(self):
        """POP-01, POP-02: Validate VoicePopup.qml structure, controls, and safety."""
        popup_paths = [
            Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePopup.qml"),
            Path(__file__).parent.parent / "integrations/quickshell/VoicePopup.qml",
        ]

        expected_config_keys = [
            "model",
            "device",
            "compute_type",
            "language",
            "chunk_duration",
            "output_method",
            "beam_size",
            "vad_filter",
            "beep",
            "tts_voice",
            "tts_backend",
            "capture_corpus",
        ]

        for p in popup_paths:
            self.assertTrue(p.is_file(), f"VoicePopup.qml missing at {p}")
            content = p.read_text(encoding="utf-8")

            # Extends StyledPopup and has 350 width
            self.assertIn("StyledPopup {", content)
            self.assertIn("350", content)

            # Array-based Quickshell.execDetached for toggle and cancel with voiceBin
            self.assertIn('Quickshell.execDetached([root.voiceBin, "--toggle"])', content)
            self.assertIn('Quickshell.execDetached([root.voiceBin, "--cancel"])', content)

            # Action button colors
            self.assertIn("#4ade80", content)  # Start
            self.assertIn("#f43f5e", content)  # Cancel
            self.assertIn("colPrimary", content)  # Stop

            # All 12 config keys present in userConfig
            for key in expected_config_keys:
                self.assertIn(f"{key}:", content, f"Missing config key {key} in {p}")

            # StyledFlickable with clip: true for recent runs
            self.assertIn("StyledFlickable {", content)
            self.assertIn("clip: true", content)

            # Voice.openReport() for report button
            self.assertIn("Voice.openReport()", content)

            # Zero raw shell or rm invocations
            self.assertNotIn("sh -c", content)
            self.assertNotIn("bash -c", content)
            self.assertNotRegex(content, r"\brm\s+-")

    def test_hover_target_always_accessible(self):
        """POP-01: Verify hover target is bound directly to pillMouseArea across all states."""
        # Inspect VoicePill.qml files
        for p in (
            Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml"),
            Path("integrations/quickshell/VoicePill.qml"),
        ):
            content = p.read_text(encoding="utf-8")
            self.assertIn("VoicePopup {", content)
            self.assertIn("hoverTarget: pillMouseArea", content)
            self.assertNotIn("Voice.openReport()", content)

    def test_voice_popup_and_pill_dotfiles_parity(self):
        """POP-01, POP-02: Ensure 100% byte-for-byte parity between .dotfiles and integrations/quickshell/."""
        dotfiles_popup = Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePopup.qml")
        repo_popup = Path("integrations/quickshell/VoicePopup.qml")
        dotfiles_pill = Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml")
        repo_pill = Path("integrations/quickshell/VoicePill.qml")

        self.assertEqual(dotfiles_popup.read_text(encoding="utf-8"), repo_popup.read_text(encoding="utf-8"))
        self.assertEqual(dotfiles_pill.read_text(encoding="utf-8"), repo_pill.read_text(encoding="utf-8"))

    def test_voice_pill_binds_hover_target(self):
        """POP-01: Verify hover target regex matches pillMouseArea in both VoicePill.qml files."""
        pattern = re.compile(r'hoverTarget:\s*pillMouseArea')
        for p in (
            Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml"),
            Path("integrations/quickshell/VoicePill.qml"),
        ):
            text = p.read_text(encoding="utf-8")
            self.assertIsNotNone(pattern.search(text), f"Missing hover target binding in {p}")

    def test_recent_runs_reverse_jsonl_parsing_simulation(self):
        """D-08, POP-02: Validate reverse JSONL parsing with edge cases."""
        # 1. Empty string -> returns []
        self.assertEqual(parse_recent_runs_simulation(""), [])
        self.assertEqual(parse_recent_runs_simulation("   \n  \n"), [])

        # 2. Single record
        rec1 = {"run_id": "r1", "audio_s": 5.2, "characters": 42, "rtf": 0.35, "is_outlier": False}
        res1 = parse_recent_runs_simulation(json.dumps(rec1))
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["duration"], "5.2s")
        self.assertEqual(res1[0]["chars"], "42")
        self.assertEqual(res1[0]["rtf"], "0.35x")
        self.assertTrue(res1[0]["success"])
        self.assertFalse(res1[0]["outlier"])

        # 3. 25 records -> returns exactly 10 newest in reverse order
        lines = []
        for i in range(25):
            lines.append(json.dumps({"run_id": f"r{i}", "audio_s": float(i), "characters": i * 10, "rtf": 0.2}))
        res25 = parse_recent_runs_simulation("\n".join(lines), max_count=10)
        self.assertEqual(len(res25), 10)
        self.assertEqual(res25[0]["runId"], "r24")
        self.assertEqual(res25[9]["runId"], "r15")

        # 4. Equal timestamp / stable file-order tie-breaking
        tie_lines = [
            json.dumps({"run_id": "a", "audio_s": 1.0, "timestamp": "2026-11-03T00:00:00Z"}),
            json.dumps({"run_id": "b", "audio_s": 1.0, "timestamp": "2026-11-03T00:00:00Z"}),
        ]
        res_tie = parse_recent_runs_simulation("\n".join(tie_lines))
        self.assertEqual([r["runId"] for r in res_tie], ["b", "a"])

        # 5. Corrupted line embedded -> skipped gracefully
        mixed_lines = [
            json.dumps({"run_id": "valid1", "audio_s": 2.0}),
            "corrupted not json {[[",
            "{bad: json}",
            json.dumps({"run_id": "valid2", "audio_s": 3.0}),
        ]
        res_mixed = parse_recent_runs_simulation("\n".join(mixed_lines))
        self.assertEqual(len(res_mixed), 2)
        self.assertEqual(res_mixed[0]["runId"], "valid2")
        self.assertEqual(res_mixed[1]["runId"], "valid1")
