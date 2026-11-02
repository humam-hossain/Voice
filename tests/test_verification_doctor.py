"""Unit tests for system diagnostics (doctor), 3-tier verification, and daemon recovery."""

from __future__ import annotations

import argparse
import io
import json
import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice


class TestCLIDispatch(unittest.TestCase):
    """Test suite covering CLI flag parsing and dispatch for doctor, verify, and kill."""

    def test_parse_args_defaults(self) -> None:
        args = voice.parse_args([])
        self.assertFalse(args.doctor)
        self.assertFalse(args.verify)
        self.assertEqual(args.tier, "all")
        self.assertFalse(getattr(args, "json_verify", False) or getattr(args, "json", False))
        self.assertIsNone(args.export_markdown)
        self.assertFalse(args.kill)

    def test_parse_args_doctor_flag(self) -> None:
        args = voice.parse_args(["--doctor"])
        self.assertTrue(args.doctor)

    def test_parse_args_verify_and_tier_flags(self) -> None:
        args = voice.parse_args(["--verify", "--tier", "2", "--json", "--export-markdown", "report.md"])
        self.assertTrue(args.verify)
        self.assertEqual(args.tier, "2")
        self.assertTrue(getattr(args, "json_verify", False) or getattr(args, "json", False))
        self.assertEqual(args.export_markdown, Path("report.md"))

    def test_parse_args_kill_flag(self) -> None:
        args = voice.parse_args(["--kill"])
        self.assertTrue(args.kill)

    def test_main_dispatches_kill(self) -> None:
        with patch("sys.argv", ["voice", "--kill"]), patch("voice.kill_all_daemons", return_value=0) as mock_kill:
            ret = voice.main()
            self.assertEqual(ret, 0)
            mock_kill.assert_called_once()

    def test_main_dispatches_doctor(self) -> None:
        with patch("sys.argv", ["voice", "--doctor"]), patch("voice.run_doctor", return_value=0) as mock_doc:
            ret = voice.main()
            self.assertEqual(ret, 0)
            mock_doc.assert_called_once()

    def test_main_dispatches_verify(self) -> None:
        with patch("sys.argv", ["voice", "--verify"]), patch("voice.run_verification", return_value=0) as mock_ver:
            ret = voice.main()
            self.assertEqual(ret, 0)
            mock_ver.assert_called_once()

    def test_verify_e2e_script_exists_and_runs_help(self) -> None:
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "verify-e2e.sh"
        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))
        res = subprocess.run([str(script_path), "--help"], capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 0)
        self.assertIn("--verify", res.stdout)
        self.assertIn("--doctor", res.stdout)


class TestDoctorDiagnostics(unittest.TestCase):
    """Test suite covering system diagnostics checks (binaries, audio, models, keybinds, PIDs)."""

    def test_check_binary_found_and_missing(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/wtype"):
            ok, details, rem = voice.check_binary("wtype", "sudo pacman -S wtype")
            self.assertTrue(ok)
            self.assertEqual(details, "/usr/bin/wtype")
            self.assertEqual(rem, "")

        with patch("shutil.which", return_value=None):
            ok, details, rem = voice.check_binary("wtype", "sudo pacman -S wtype")
            self.assertFalse(ok)
            self.assertEqual(details, "missing")
            self.assertEqual(rem, "sudo pacman -S wtype")

    def test_check_audio_source_status_active(self) -> None:
        proc = MagicMock(returncode=0, stdout="Volume: 0.85\n")
        with patch("shutil.which", return_value="/usr/bin/wpctl"), patch("subprocess.run", return_value=proc):
            ok, details, rem = voice.check_audio_source_status()
            self.assertTrue(ok)
            self.assertIn("Active", details)
            self.assertEqual(rem, "")

    def test_check_audio_source_status_muted(self) -> None:
        proc = MagicMock(returncode=0, stdout="Volume: 0.70 [MUTED]\n")
        with patch("shutil.which", return_value="/usr/bin/wpctl"), patch("subprocess.run", return_value=proc):
            ok, details, rem = voice.check_audio_source_status()
            self.assertFalse(ok)
            self.assertIn("[MUTED]", details)
            self.assertIn("wpctl set-mute", rem)

    def test_check_audio_source_status_missing_wpctl(self) -> None:
        with patch("shutil.which", return_value=None):
            ok, details, rem = voice.check_audio_source_status()
            self.assertFalse(ok)
            self.assertIn("unavailable", details)
            self.assertIn("wireplumber", rem)

    def test_check_models_status_all_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            onnx_path = tmp_path / "kokoro.onnx"
            voices_path = tmp_path / "voices.bin"
            # Fast sparse file creation
            with open(onnx_path, "wb") as f:
                f.truncate(310_000_000)
            with open(voices_path, "wb") as f:
                f.truncate(25_000_000)

            # Mock HF cache dir
            hf_cache = tmp_path / "hf_hub"
            hf_cache.mkdir()
            (hf_cache / "models--Systran--faster-whisper-small.en").mkdir()

            with patch("pathlib.Path.home", return_value=tmp_path):
                # Ensure ~/.cache/huggingface/hub points to our tmp structure
                hub_dir = tmp_path / ".cache" / "huggingface" / "hub"
                hub_dir.parent.mkdir(parents=True, exist_ok=True)
                hub_dir.symlink_to(hf_cache)

                results = voice.check_models_status(
                    stt_model="small.en",
                    kokoro_model=onnx_path,
                    kokoro_voices=voices_path,
                )
                self.assertEqual(len(results), 3)
                for name, ok, details, rem in results:
                    self.assertTrue(ok, f"Model {name} should be valid")

    def test_check_models_status_undersized_or_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            onnx_path = tmp_path / "kokoro.onnx"
            voices_path = tmp_path / "voices.bin"
            with open(onnx_path, "wb") as f:
                f.truncate(1000)  # undersized

            results = voice.check_models_status(
                stt_model="nonexistent-model",
                kokoro_model=onnx_path,
                kokoro_voices=voices_path,  # missing
            )
            whisper = next(r for r in results if "Faster-Whisper" in r[0])
            kokoro = next(r for r in results if "Kokoro ONNX" in r[0])
            voices = next(r for r in results if "Kokoro Voices" in r[0])

            self.assertFalse(whisper[1])
            self.assertFalse(kokoro[1])
            self.assertIn("Undersized", kokoro[2])
            self.assertFalse(voices[1])
            self.assertIn("Missing", voices[2])

    def test_check_hyprland_keybinds_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            kb_path = tmp_path / "keybinds.lua"

            # Missing file
            ok, details, rem = voice.check_hyprland_keybinds_status(config_path=kb_path)
            self.assertFalse(ok)
            self.assertIn("Not found", details)

            # Incomplete content
            kb_path.write_text("hl.bind('SUPER + A', 'test')", encoding="utf-8")
            ok, details, rem = voice.check_hyprland_keybinds_status(config_path=kb_path)
            self.assertFalse(ok)
            self.assertIn("Incomplete", details)

            # Valid block
            valid_content = (
                "-- voicemode start\n"
                'hl.unbind("SUPER + T")\n'
                'hl.bind("SUPER + SHIFT + M", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --toggle"))\n'
                'hl.bind("SUPER + T", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --speak-selection"))\n'
                "-- voicemode end\n"
            )
            kb_path.write_text(valid_content, encoding="utf-8")
            ok, details, rem = voice.check_hyprland_keybinds_status(config_path=kb_path)
            self.assertTrue(ok)
            self.assertIn("Verified", details)

            # Symlink preservation info
            symlink_path = tmp_path / "symlink_keybinds.lua"
            symlink_path.symlink_to(kb_path)
            ok, details, rem = voice.check_hyprland_keybinds_status(config_path=symlink_path)
            self.assertTrue(ok)
            self.assertIn("symlink", details)

    def test_check_daemon_pid_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            rec_pid = tmp_path / "recorder.pid"
            tts_pid = tmp_path / "tts.pid"

            with patch("voice.PID_FILE", rec_pid), patch("voice.TTS_PID_FILE", tts_pid):
                # Both idle
                results = voice.check_daemon_pid_health()
                self.assertEqual(len(results), 2)
                self.assertTrue(all(r[1] for r in results))
                self.assertTrue(all("Idle" in r[2] for r in results))

                # Active PID
                rec_pid.write_text("12345 recording\n", encoding="utf-8")
                with patch("voice.process_alive", return_value=True):
                    results = voice.check_daemon_pid_health()
                    rec = next(r for r in results if r[0] == "STT Recorder")
                    self.assertTrue(rec[1])
                    self.assertIn("Running", rec[2])

                # Stale dead PID
                with patch("voice.process_alive", return_value=False):
                    results = voice.check_daemon_pid_health()
                    rec = next(r for r in results if r[0] == "STT Recorder")
                    self.assertFalse(rec[1])
                    self.assertIn("Stale lock", rec[2])
                    self.assertIn("voice --kill", rec[3])

    def test_run_doctor_terminal_and_json(self) -> None:
        args_text = argparse.Namespace(json=False, model="small.en", kokoro_model=None, kokoro_voices=None)
        with patch("voice.check_binary", return_value=(True, "/usr/bin/test", "")), \
             patch("voice.check_audio_source_status", return_value=(True, "Volume: 1.0 (Active)", "")), \
             patch("voice.check_models_status", return_value=[("Model", True, "ok", "")]), \
             patch("voice.check_hyprland_keybinds_status", return_value=(True, "Verified", "")), \
             patch("voice.check_daemon_pid_health", return_value=[("STT", True, "Idle", "")]), \
             patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            ret = voice.run_doctor(args_text)
            self.assertEqual(ret, 0)
            output = fake_stdout.getvalue()
            self.assertIn("VOICEMODE SYSTEM PRE-FLIGHT DIAGNOSTICS", output)
            self.assertIn("[PASS]", output)

        args_json = argparse.Namespace(json=True, model="small.en", kokoro_model=None, kokoro_voices=None)
        with patch("voice.check_binary", return_value=(True, "/usr/bin/test", "")), \
             patch("voice.check_audio_source_status", return_value=(True, "Volume: 1.0 (Active)", "")), \
             patch("voice.check_models_status", return_value=[("Model", True, "ok", "")]), \
             patch("voice.check_hyprland_keybinds_status", return_value=(True, "Verified", "")), \
             patch("voice.check_daemon_pid_health", return_value=[("STT", True, "Idle", "")]), \
             patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            ret = voice.run_doctor(args_json)
            self.assertEqual(ret, 0)
            payload = json.loads(fake_stdout.getvalue())
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["critical_failures"], 0)


class TestDaemonRecovery(unittest.TestCase):
    """Test suite covering daemon recovery and stale lock cleanup via voice --kill."""

    def test_kill_all_daemons_idle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch("voice.PID_FILE", tmp_path / "rec.pid"), patch("voice.TTS_PID_FILE", tmp_path / "tts.pid"), \
                 patch("sys.stdout", new=io.StringIO()) as fake_stdout:
                ret = voice.kill_all_daemons(argparse.Namespace())
                self.assertEqual(ret, 0)
                self.assertIn("No active daemons", fake_stdout.getvalue())

    def test_kill_all_daemons_active_and_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            rec_pid = tmp_path / "rec.pid"
            tts_pid = tmp_path / "tts.pid"
            rec_pid.write_text("11111 recording\n", encoding="utf-8")
            tts_pid.write_text("22222 speaking\n", encoding="utf-8")

            # rec is alive, tts is dead stale lock
            def fake_alive(pid: int) -> bool:
                return pid == 11111

            with patch("voice.PID_FILE", rec_pid), patch("voice.TTS_PID_FILE", tts_pid), \
                 patch("voice.process_alive", side_effect=fake_alive), \
                 patch("os.kill") as mock_kill, \
                 patch("sys.stdout", new=io.StringIO()) as fake_stdout:
                ret = voice.kill_all_daemons(argparse.Namespace())
                self.assertEqual(ret, 0)
                mock_kill.assert_called_once_with(11111, signal.SIGTERM)
                self.assertFalse(rec_pid.exists())
                self.assertFalse(tts_pid.exists())
                output = fake_stdout.getvalue()
                self.assertIn("Terminated active STT Recorder (PID 11111)", output)
                self.assertIn("Removed stale lock for TTS Player (PID 22222", output)
                self.assertIn("Daemon recovery complete", output)


class TestCompositorInterrogation(unittest.TestCase):
    """Test suite covering dynamic Hyprland compositor window interrogation."""

    def test_hyprctl_active_window_success(self) -> None:
        raw_json = json.dumps({
            "class": "kitty",
            "title": "terminal",
            "pid": 12345,
            "workspace": {"id": 1, "name": "1"},
            "xwayland": False,
        })
        proc = MagicMock(returncode=0, stdout=raw_json)
        with patch("shutil.which", return_value="/usr/bin/hyprctl"), \
             patch("subprocess.run", return_value=proc):
            data = voice.hyprctl_active_window(countdown_seconds=0)
            self.assertIsNotNone(data)
            assert data is not None
            self.assertEqual(data["class"], "kitty")
            self.assertEqual(data["title"], "terminal")
            self.assertEqual(data["pid"], 12345)
            self.assertEqual(data["workspace"], "1")
            self.assertFalse(data["xwayland"])

    def test_hyprctl_active_window_empty_or_no_client(self) -> None:
        proc = MagicMock(returncode=0, stdout="{}")
        with patch("shutil.which", return_value="/usr/bin/hyprctl"), \
             patch("subprocess.run", return_value=proc):
            data = voice.hyprctl_active_window(countdown_seconds=0)
            self.assertIsNone(data)

    def test_hyprctl_active_window_missing_hyprctl(self) -> None:
        with patch("shutil.which", return_value=None):
            data = voice.hyprctl_active_window(countdown_seconds=0)
            self.assertIsNone(data)

    def test_hyprctl_active_window_invalid_json(self) -> None:
        proc = MagicMock(returncode=0, stdout="not valid json")
        with patch("shutil.which", return_value="/usr/bin/hyprctl"), \
             patch("subprocess.run", return_value=proc):
            data = voice.hyprctl_active_window(countdown_seconds=0)
            self.assertIsNone(data)


class TestVerificationTiers(unittest.TestCase):
    """Test suite covering 3-tier verification runner, payloads, and report exports."""

    def test_payloads_matrix(self) -> None:
        self.assertEqual(len(voice.TEST_PAYLOADS), 4)
        names = [p[0] for p in voice.TEST_PAYLOADS]
        self.assertIn("Conversational prose", names)
        self.assertIn("Punctuation & capitalization", names)
        self.assertIn("Programming code & symbols", names)
        self.assertIn("Multi-line text (newlines)", names)

        # Verify newline payload preservation
        multiline = next(p[1] for p in voice.TEST_PAYLOADS if "newlines" in p[0])
        self.assertIn("\n", multiline)
        self.assertEqual(len(multiline.splitlines()), 3)

    def test_check_primary_selection_roundtrip_success(self) -> None:
        def fake_run(cmd, **kwargs):
            if "--primary" in cmd and kwargs.get("input"):
                token = kwargs["input"]
                fake_run.saved_token = token
                return MagicMock(returncode=0)
            elif "--primary" in cmd and kwargs.get("capture_output"):
                return MagicMock(returncode=0, stdout=fake_run.saved_token)
            return MagicMock(returncode=1)

        with patch("shutil.which", return_value="/usr/bin/wl-tool"), \
             patch("subprocess.run", side_effect=fake_run):
            ok, details, rem = voice.check_primary_selection_roundtrip()
            self.assertTrue(ok)
            self.assertIn("Verified round-trip", details)

    def test_check_primary_selection_roundtrip_missing_tools(self) -> None:
        with patch("shutil.which", return_value=None):
            ok, details, rem = voice.check_primary_selection_roundtrip()
            self.assertFalse(ok)
            self.assertIn("missing", details)

    def test_run_tier1_diagnostics(self) -> None:
        args = argparse.Namespace(model="small.en", kokoro_model=None, kokoro_voices=None)
        with patch("voice.check_binary", return_value=(True, "/usr/bin/x", "")), \
             patch("voice.check_audio_source_status", return_value=(True, "Volume: 1.0 (Active)", "")), \
             patch("voice.check_models_status", return_value=[("Model", True, "ok", "")]), \
             patch("voice.check_hyprland_keybinds_status", return_value=(True, "Verified", "")), \
             patch("voice.check_daemon_pid_health", return_value=[("STT", True, "Idle", "")]):
            ok, results = voice.run_tier1_diagnostics(args)
            self.assertTrue(ok)
            self.assertEqual(len(results), 5)
            self.assertTrue(all(r["tier"] == "T1" for r in results))

    def test_run_tier2_pipeline_test(self) -> None:
        args = argparse.Namespace(beep=False)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_wav = Path(tmp_dir) / "test.wav"
            tmp_wav.write_bytes(b"RIFF" + b"\x00" * 2000)

            def fake_synth(text, out_path, a):
                out_path.write_bytes(b"RIFF" + b"\x00" * 2000)

            with patch("voice.play_tone"), \
                 patch("voice.synthesize_kokoro_tts", side_effect=fake_synth), \
                 patch("voice.load_model", return_value=MagicMock()), \
                 patch("voice.transcribe", return_value=("The quick brown fox jumps over the lazy dog.", MagicMock())), \
                 patch("voice.check_primary_selection_roundtrip", return_value=(True, "Verified", "")):
                ok, results = voice.run_tier2_pipeline_test(args)
                self.assertTrue(ok)
                self.assertEqual(len(results), 4)
                self.assertTrue(all(r["tier"] == "T2" for r in results))
                subsystems = [r["subsystem"] for r in results]
                self.assertIn("Audio Synthesizer", subsystems)
                self.assertIn("Neural TTS Engine", subsystems)
                self.assertIn("Speech Recognition Engine", subsystems)
                self.assertIn("Wayland Clipboard", subsystems)

    def test_run_tier3_interactive_test_headless(self) -> None:
        args = argparse.Namespace()
        with patch("sys.stdin.isatty", return_value=False):
            ok, results = voice.run_tier3_interactive_test(args)
            self.assertTrue(ok)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["tier"], "T3")
            self.assertIn("Skipped", results[0]["details"])

    def test_run_verification_and_markdown_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            export_path = Path(tmp_dir) / "sub" / "report.md"
            args = argparse.Namespace(
                tier="1",
                export_markdown=export_path,
                json=False,
                model="small.en",
                kokoro_model=None,
                kokoro_voices=None,
            )
            with patch("voice.run_tier1_diagnostics", return_value=(True, [
                {"tier": "T1", "subsystem": "Binaries", "test": "Arch binaries", "ok": True, "details": "6/6", "duration_s": 0.01}
            ])), patch("sys.stdout", new=io.StringIO()) as fake_stdout:
                ret = voice.run_verification(args)
                self.assertEqual(ret, 0)
                self.assertTrue(export_path.exists())
                content = export_path.read_text(encoding="utf-8")
                self.assertIn("# Voicemode 3-Tier Verification Report", content)
                self.assertIn("Arch Linux", content)
                self.assertIn("| T1 | Binaries | Arch binaries | PASS |", content)
                self.assertIn("OVERALL STATUS: PASS", fake_stdout.getvalue())


class TestHardwareBackendProbe(unittest.TestCase):
    """Test suite covering guarded hardware backend probing."""

    def test_probe_hardware_backend_cpu_and_cuda_mocked(self) -> None:
        with patch("ctranslate2.get_cuda_device_count", return_value=1), \
             patch("shutil.which", return_value="/usr/bin/nvidia-smi"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="NVIDIA GeForce RTX 3060\n")
            hw = voice.probe_hardware_backend()
            self.assertEqual(hw["cuda_devices"], 1)
            self.assertEqual(hw["cuda_name"], "NVIDIA GeForce RTX 3060")
            self.assertEqual(hw["default_backend"], "cpu, int8")

    def test_probe_hardware_backend_nvidia_smi_timeout(self) -> None:
        with patch("ctranslate2.get_cuda_device_count", return_value=1), \
             patch("shutil.which", return_value="/usr/bin/nvidia-smi"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["nvidia-smi"], timeout=1.0)):
            hw = voice.probe_hardware_backend()
            self.assertEqual(hw["cuda_devices"], 1)
            self.assertIn("timed out", hw["cuda_name"])
            self.assertEqual(hw["default_backend"], "cpu, int8")

    def test_probe_hardware_backend_cpu_flags_mocked(self) -> None:
        fake_cpuinfo = "processor\t: 0\nflags\t\t: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault epb ssbd ibrs ibpb stibp tpr_shadow flexpriority ept vpid ept_ad fsgsbase tsc_adjust bmi1 avx2 smep bmi2 erms invpcid rdseed adx smap clflushopt intel_pt avx512f avx512dq\n"
        with patch("builtins.open", unittest.mock.mock_open(read_data=fake_cpuinfo)):
            hw = voice.probe_hardware_backend()
            self.assertTrue(hw["avx2"])
            self.assertTrue(hw["avx512"])

    def test_probe_hardware_backend_no_model_loading(self) -> None:
        with patch("faster_whisper.WhisperModel") as mock_model:
            hw = voice.probe_hardware_backend()
            mock_model.assert_not_called()
            self.assertEqual(hw["default_backend"], "cpu, int8")


class TestDoctorTelemetryAndPaths(unittest.TestCase):
    """Test suite covering doctor telemetry card, path permissions, and JSON contracts."""

    def test_run_doctor_json_contains_telemetry_and_hardware(self) -> None:
        args = voice.parse_args(["--doctor", "--json"])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            ret = voice.run_doctor(args)
            self.assertEqual(ret, 0)
            data = json.loads(mock_out.getvalue())
            self.assertIn("telemetry", data)
            self.assertIn("hardware", data)
            self.assertIn("paths", data)
            self.assertEqual(data["hardware"]["default_backend"], "cpu, int8")
            self.assertIn("runtime_dir", data["paths"])
            self.assertIn("state_dir", data["paths"])
            self.assertIn("corpus_dir", data["paths"])
            self.assertIn("metrics_ledger", data["paths"])

    def test_check_paths_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_p = Path(tmp_dir)
            rt_dir = tmp_p / "runtime"
            st_dir = tmp_p / "state"
            cp_dir = tmp_p / "corpus"
            ledger = st_dir / "metrics.jsonl"
            rt_dir.mkdir(mode=0o700)
            st_dir.mkdir(mode=0o700)
            cp_dir.mkdir(mode=0o700)
            ledger.write_text("{}\n", encoding="utf-8")
            os.chmod(ledger, 0o600)

            with patch("voicemode_telemetry.get_runtime_dir", return_value=rt_dir), \
                 patch("voicemode_telemetry.get_metrics_dir", return_value=st_dir), \
                 patch("voicemode_telemetry.get_corpus_dir", return_value=cp_dir), \
                 patch("voicemode_telemetry.get_ledger_path", return_value=ledger), \
                 patch("shutil.disk_usage", return_value=MagicMock(free=10 * 1024**3)):
                ok, paths_data = voice.check_paths_and_permissions()
                self.assertTrue(ok)
                self.assertTrue(paths_data["runtime_dir"]["ok"])
                self.assertTrue(paths_data["state_dir"]["ok"])
                self.assertTrue(paths_data["corpus_dir"]["ok"])
                self.assertTrue(paths_data["metrics_ledger"]["ok"])
                self.assertTrue(paths_data["disk_space"]["ok"])

    def test_doctor_exit_codes_advisory_vs_fatal(self) -> None:
        # Fatal break (missing wtype) -> exit code 1
        args = voice.parse_args(["--doctor"])
        with patch("voice.check_binary", side_effect=lambda name, hint: (False, "missing", hint) if name == "wtype" else (True, f"/bin/{name}", "")), \
             patch("voice.check_audio_source_status", return_value=(True, "Active", "")), \
             patch("voice.check_models_status", return_value=[]), \
             patch("voice.check_hyprland_keybinds_status", return_value=(True, "Verified", "")), \
             patch("voice.check_daemon_pid_health", return_value=[]), \
             patch("sys.stdout", new_callable=io.StringIO):
            ret = voice.run_doctor(args)
            self.assertEqual(ret, 1)

        # Advisory warning (muted mic + invalid permissions) -> exit code 0
        with patch("voice.check_binary", return_value=(True, "/bin/ok", "")), \
             patch("voice.check_audio_source_status", return_value=(False, "Volume: 0.50 [MUTED]", "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0")), \
             patch("voice.check_models_status", return_value=[]), \
             patch("voice.check_hyprland_keybinds_status", return_value=(True, "Verified", "")), \
             patch("voice.check_daemon_pid_health", return_value=[]), \
             patch("voice.check_paths_and_permissions", return_value=(False, {"runtime_dir": {"ok": False, "mode": "0o777"}})), \
             patch("sys.stdout", new_callable=io.StringIO):
            ret = voice.run_doctor(args)
            self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
