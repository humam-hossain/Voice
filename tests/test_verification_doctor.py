"""Unit tests for system diagnostics (doctor), 3-tier verification, and daemon recovery."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import voice


class TestCLIDispatch(unittest.TestCase):
    """Test suite covering CLI flag parsing and dispatch for doctor, verify, and kill."""

    def test_parse_args_defaults(self) -> None:
        args = voice.parse_args([])
        self.assertFalse(args.doctor)
        self.assertFalse(args.verify)
        self.assertEqual(args.tier, "all")
        self.assertFalse(args.json)
        self.assertIsNone(args.export_markdown)
        self.assertFalse(args.kill)

    def test_parse_args_doctor_flag(self) -> None:
        args = voice.parse_args(["--doctor"])
        self.assertTrue(args.doctor)

    def test_parse_args_verify_and_tier_flags(self) -> None:
        args = voice.parse_args(["--verify", "--tier", "2", "--json", "--export-markdown", "report.md"])
        self.assertTrue(args.verify)
        self.assertEqual(args.tier, "2")
        self.assertTrue(args.json)
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


if __name__ == "__main__":
    unittest.main()
