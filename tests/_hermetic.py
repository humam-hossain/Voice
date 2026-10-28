from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def advancing_monotonic(start=1000.0, step=0.01):
    value = {"v": start}
    
    def _monotonic():
        value["v"] += step
        return value["v"]
    return _monotonic


class TempXdgTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.xdg_root = Path(self._temp_dir.name)
        self.run_dir = self.xdg_root / "run"
        self.state_dir = self.xdg_root / "state"
        self.run_dir.mkdir(parents=True)
        self.state_dir.mkdir(parents=True)
        (self.run_dir / "voice-stt").mkdir(parents=True)
        
        import voice
        
        self._env_patch = patch.dict(os.environ, {
            "XDG_RUNTIME_DIR": str(self.run_dir),
            "XDG_STATE_HOME": str(self.state_dir),
        })
        self._env_patch.start()
        
        self._const_patches = [
            patch.object(voice, "STATE_DIR", Path(self.run_dir / "voice-stt")),
            patch.object(voice, "PID_FILE", Path(self.run_dir / "voice-stt" / "pid")),
            patch.object(voice, "TTS_PID_FILE", Path(self.run_dir / "voice-stt" / "tts.pid")),
            patch.object(voice, "LOG_FILE", Path(self.run_dir / "voice-stt" / "voice.log")),
            patch.object(voice, "TTS_LOG_FILE", Path(self.run_dir / "voice-stt" / "tts.log")),
        ]
        for p in self._const_patches:
            p.start()
        
        self.addCleanup(self._cleanup)
    
    def _cleanup(self) -> None:
        for p in reversed(self._const_patches):
            p.stop()
        self._env_patch.stop()
        self._temp_dir.cleanup()
