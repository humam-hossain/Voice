from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from tests._hermetic import TempXdgTestCase
import voice


class TestUserConfig(TempXdgTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config_home = self.xdg_root / "config"
        self.config_home.mkdir(parents=True, exist_ok=True)
        self._cfg_env_patch = patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.config_home),
        })
        self._cfg_env_patch.start()
        self.addCleanup(self._cfg_env_patch.stop)

    def test_config_dir_and_path_resolution(self) -> None:
        cfg_dir = voice.get_config_dir()
        self.assertEqual(cfg_dir, self.config_home / "voicemode")
        self.assertTrue(cfg_dir.is_dir())
        self.assertEqual(cfg_dir.stat().st_mode & 0o777, 0o700)

        cfg_path = voice.get_config_path()
        self.assertEqual(cfg_path, cfg_dir / "config.json")

    def test_save_and_load_user_config_roundtrip_and_permissions(self) -> None:
        test_data = {
            "model": "small.en",
            "beam_size": 2,
            "vad_filter": False,
            "beep": False,
        }
        voice.save_user_config(test_data)

        cfg_path = voice.get_config_path()
        self.assertTrue(cfg_path.is_file())
        self.assertEqual(cfg_path.stat().st_mode & 0o777, 0o600)

        loaded = voice.load_user_config()
        self.assertEqual(loaded, test_data)

    def test_corrupted_empty_or_non_dict_config_falls_back_cleanly(self) -> None:
        cfg_path = voice.get_config_path()

        # Non-existent config
        self.assertEqual(voice.load_user_config(), {})

        # Empty file
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text("", encoding="utf-8")
        self.assertEqual(voice.load_user_config(), {})

        # Unparseable corrupted JSON
        cfg_path.write_text("{invalid json", encoding="utf-8")
        self.assertEqual(voice.load_user_config(), {})

        # Non-dict JSON (e.g. array or primitive)
        cfg_path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(voice.load_user_config(), {})
        cfg_path.write_text('"a string"', encoding="utf-8")
        self.assertEqual(voice.load_user_config(), {})

    def test_config_precedence_model(self) -> None:
        # Default
        args = voice.parse_args([])
        self.assertEqual(args.model, "medium.en")

        # Config overrides default
        voice.save_user_config({"model": "small.en"})
        args = voice.parse_args([])
        self.assertEqual(args.model, "small.en")

        # Env overrides config
        with patch.dict(os.environ, {"VOICE_STT_MODEL": "base.en"}):
            args = voice.parse_args([])
            self.assertEqual(args.model, "base.en")

            # CLI overrides env
            args = voice.parse_args(["--model", "tiny.en"])
            self.assertEqual(args.model, "tiny.en")

    def test_config_precedence_device_and_compute_type(self) -> None:
        voice.save_user_config({"device": "cuda", "compute_type": "float16"})
        args = voice.parse_args([])
        self.assertEqual(args.device, "cuda")
        self.assertEqual(args.compute_type, "float16")

        with patch.dict(os.environ, {"VOICE_STT_DEVICE": "cpu", "VOICE_STT_COMPUTE_TYPE": "int8"}):
            args = voice.parse_args([])
            self.assertEqual(args.device, "cpu")
            self.assertEqual(args.compute_type, "int8")

            args = voice.parse_args(["--device", "cuda", "--compute-type", "float32"])
            self.assertEqual(args.device, "cuda")
            self.assertEqual(args.compute_type, "float32")

    def test_config_precedence_language(self) -> None:
        # Default
        args = voice.parse_args([])
        self.assertEqual(args.language, "en")

        # Config language "auto" maps to None
        voice.save_user_config({"language": "auto"})
        args = voice.parse_args([])
        self.assertIsNone(args.language)

        # Config language explicit
        voice.save_user_config({"language": "es"})
        args = voice.parse_args([])
        self.assertEqual(args.language, "es")

        # Env overrides config
        with patch.dict(os.environ, {"VOICE_STT_LANGUAGE": "fr"}):
            args = voice.parse_args([])
            self.assertEqual(args.language, "fr")

            # CLI overrides env
            args = voice.parse_args(["--language", "de"])
            self.assertEqual(args.language, "de")

    def test_config_precedence_chunk_duration(self) -> None:
        # Default
        args = voice.parse_args([])
        self.assertIsNone(args.chunk_seconds)
        self.assertEqual(voice.chunk_seconds(args), voice.DEFAULT_CHUNK_SECONDS)

        # Config chunk_duration
        voice.save_user_config({"chunk_duration": 5.0})
        args = voice.parse_args([])
        self.assertEqual(args.chunk_seconds, 5.0)
        self.assertEqual(voice.chunk_seconds(args), 5.0)

        # Env overrides config
        with patch.dict(os.environ, {"VOICE_CHUNK_SECONDS": "10.0"}):
            args = voice.parse_args([])
            self.assertEqual(args.chunk_seconds, 10.0)

            # CLI overrides env
            args = voice.parse_args(["--chunk-seconds", "20.0"])
            self.assertEqual(args.chunk_seconds, 20.0)

    def test_config_precedence_output_method_and_beam_size(self) -> None:
        voice.save_user_config({"output_method": "paste", "beam_size": 3})
        args = voice.parse_args([])
        self.assertEqual(args.output_method, "paste")
        self.assertEqual(args.beam_size, 3)

        with patch.dict(os.environ, {"VOICE_OUTPUT_METHOD": "clipboard", "VOICE_STT_BEAM_SIZE": "4"}):
            args = voice.parse_args([])
            self.assertEqual(args.output_method, "clipboard")
            self.assertEqual(args.beam_size, 4)

            args = voice.parse_args(["--output-method", "type", "--beam-size", "5"])
            self.assertEqual(args.output_method, "type")
            self.assertEqual(args.beam_size, 5)

    def test_config_precedence_vad_filter_and_beep(self) -> None:
        # Default is True
        args = voice.parse_args([])
        self.assertTrue(args.vad_filter)
        self.assertTrue(args.beep)

        # Config sets False
        voice.save_user_config({"vad_filter": False, "beep": False})
        args = voice.parse_args([])
        self.assertFalse(args.vad_filter)
        self.assertFalse(args.beep)

        # Env overrides config to True
        with patch.dict(os.environ, {"VOICE_VAD_FILTER": "1", "VOICE_BEEP": "1"}):
            args = voice.parse_args([])
            self.assertTrue(args.vad_filter)
            self.assertTrue(args.beep)

            # CLI overrides env to False
            args = voice.parse_args(["--no-vad-filter", "--no-beep"])
            self.assertFalse(args.vad_filter)
            self.assertFalse(args.beep)

            # CLI can re-enable with flag
            args = voice.parse_args(["--vad-filter", "--beep"])
            self.assertTrue(args.vad_filter)
            self.assertTrue(args.beep)

    def test_config_precedence_tts_voice_and_backend(self) -> None:
        voice.save_user_config({"tts_backend": "edge", "tts_voice": "en-US-JennyNeural"})
        args = voice.parse_args([])
        self.assertEqual(args.tts_backend, "edge")
        self.assertEqual(args.tts_voice, "en-US-JennyNeural")

        with patch.dict(os.environ, {"VOICE_TTS_BACKEND": "kokoro", "VOICE_TTS_VOICE": "af_bella"}):
            args = voice.parse_args([])
            self.assertEqual(args.tts_backend, "kokoro")
            self.assertEqual(args.tts_voice, "af_bella")

            args = voice.parse_args(["--tts-backend", "edge", "--tts-voice", "en-US-GuyNeural"])
            self.assertEqual(args.tts_backend, "edge")
            self.assertEqual(args.tts_voice, "en-US-GuyNeural")

    def test_config_precedence_capture_corpus(self) -> None:
        # Default is None
        args = voice.parse_args([])
        self.assertIsNone(args.capture_corpus)

        # Config sets "outliers"
        voice.save_user_config({"capture_corpus": "outliers"})
        args = voice.parse_args([])
        self.assertEqual(args.capture_corpus, "outliers")

        # Env overrides config to "all"
        with patch.dict(os.environ, {"VOICEMODE_CORPUS_CAPTURE": "all"}):
            args = voice.parse_args([])
            self.assertEqual(args.capture_corpus, "all")

            # CLI overrides env
            args = voice.parse_args(["--capture-corpus", "none"])
            self.assertEqual(args.capture_corpus, "none")

    def test_background_argv_forwarding(self) -> None:
        # Test forwarding with vad_filter=True, chunk_seconds=5.0, capture_corpus="outliers"
        args = voice.parse_args([
            "--vad-filter",
            "--chunk-seconds", "5.0",
            "--capture-corpus", "outliers"
        ])
        argv = voice.background_argv(args)
        self.assertIn("--vad-filter", argv)
        self.assertIn("--chunk-seconds", argv)
        self.assertIn("5.0", argv)
        self.assertIn("--capture-corpus", argv)
        self.assertIn("outliers", argv)

        # Test forwarding with no-vad-filter, no chunk_seconds, capture_corpus="none"
        args2 = voice.parse_args([
            "--no-vad-filter",
            "--capture-corpus", "none"
        ])
        argv2 = voice.background_argv(args2)
        self.assertIn("--no-vad-filter", argv2)
        self.assertNotIn("--chunk-seconds", argv2)
        self.assertNotIn("--capture-corpus", argv2)
