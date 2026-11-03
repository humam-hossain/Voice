"""Tests for STT and TTS model parameter/size specifications and Whisper download/update CLI."""
from __future__ import annotations

import argparse
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import voice


class TestModelSpecs(unittest.TestCase):
    def test_whisper_models_metadata_completeness(self) -> None:
        expected_models = [
            "tiny",
            "tiny.en",
            "base",
            "base.en",
            "small",
            "small.en",
            "medium",
            "medium.en",
            "large-v2",
            "large-v3",
            "large-v3-turbo",
        ]
        for m in expected_models:
            self.assertIn(m, voice.WHISPER_MODELS_METADATA)
            meta = voice.WHISPER_MODELS_METADATA[m]
            self.assertIn("params", meta)
            self.assertIn("disk", meta)
            self.assertIn("ram", meta)
            self.assertIn("description", meta)
            self.assertTrue(len(meta["params"]) > 0)
            self.assertTrue(len(meta["disk"]) > 0)
            self.assertTrue(len(meta["ram"]) > 0)

    def test_tts_backends_metadata_completeness(self) -> None:
        for b in ["kokoro", "edge"]:
            self.assertIn(b, voice.TTS_BACKENDS_METADATA)
            meta = voice.TTS_BACKENDS_METADATA[b]
            self.assertIn("name", meta)
            self.assertIn("params", meta)
            self.assertIn("disk", meta)
            self.assertIn("ram", meta)
            self.assertIn("description", meta)

    def test_is_whisper_model_cached(self) -> None:
        # small.en and medium.en are cached in user's home dir
        self.assertTrue(voice.is_whisper_model_cached("medium.en"))
        self.assertTrue(voice.is_whisper_model_cached("small.en"))
        # Nonexistent dummy model should return False
        self.assertFalse(voice.is_whisper_model_cached("nonexistent_test_model_xyz"))

    def test_get_models_metadata_structure(self) -> None:
        data = voice.get_models_metadata()
        self.assertIn("stt_models", data)
        self.assertIn("tts_backends", data)

        stt_ids = [m["id"] for m in data["stt_models"]]
        self.assertIn("tiny", stt_ids)
        self.assertIn("medium.en", stt_ids)
        self.assertIn("large-v3-turbo", stt_ids)

        for m in data["stt_models"]:
            self.assertIsInstance(m["cached"], bool)
            self.assertIn("params", m)
            self.assertIn("disk", m)
            self.assertIn("ram", m)

        tts_ids = [b["id"] for b in data["tts_backends"]]
        self.assertIn("kokoro", tts_ids)
        self.assertIn("edge", tts_ids)

    def test_print_models_info_text(self) -> None:
        args = argparse.Namespace(json_status=False, json_verify=False, json=False, format=None)
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            exit_code = voice.print_models_info(args)
            self.assertEqual(exit_code, 0)
            output = fake_stdout.getvalue()
            self.assertIn("Faster-Whisper", output)
            self.assertIn("medium.en", output)
            self.assertIn("large-v3-turbo", output)
            self.assertIn("kokoro", output)
            self.assertIn("edge", output)

    def test_print_models_info_json(self) -> None:
        args = argparse.Namespace(json_status=True, json_verify=False, json=False, format="json")
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            exit_code = voice.print_models_info(args)
            self.assertEqual(exit_code, 0)
            parsed = json.loads(fake_stdout.getvalue())
            self.assertIn("stt_models", parsed)
            self.assertIn("tts_backends", parsed)
            self.assertTrue(len(parsed["stt_models"]) >= 10)

    def test_download_whisper_model_mock(self) -> None:
        args = argparse.Namespace(model="medium.en")
        with patch("faster_whisper.download_model", return_value="/mock/path/to/model") as mock_dl:
            exit_code = voice.download_whisper_model("small.en", args)
            self.assertEqual(exit_code, 0)
            mock_dl.assert_called_once_with("small.en", local_files_only=False)

    def test_download_whisper_model_failure(self) -> None:
        args = argparse.Namespace(model="medium.en")
        with (
            patch("faster_whisper.download_model", side_effect=RuntimeError("Network error")),
            patch("sys.stderr", new=io.StringIO()),
        ):
            exit_code = voice.download_whisper_model("broken-model", args)
            self.assertEqual(exit_code, 1)

    def test_quickshell_dotfiles_parity(self) -> None:
        repo_qml = Path("integrations/quickshell/VoicePopup.qml").read_text()
        dotfiles_qml = Path(
            "/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePopup.qml"
        ).read_text()
        self.assertEqual(repo_qml, dotfiles_qml, "VoicePopup.qml must maintain 100% dotfiles parity")

    def test_quickshell_popup_contains_model_specs_and_controls(self) -> None:
        qml = Path("integrations/quickshell/VoicePopup.qml").read_text()
        self.assertIn("modelSpecs:", qml)
        self.assertIn("large-v3-turbo", qml)
        self.assertIn("ModelOptionChip", qml)
        self.assertIn("modelsCard", qml)
        self.assertIn("updateModelBtn", qml)
        self.assertIn("downloadModelProc", qml)
        self.assertIn("checkModelsProc", qml)


if __name__ == "__main__":
    unittest.main()
