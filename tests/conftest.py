from __future__ import annotations

import tempfile
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolate_xdg_config(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg_dir))
    yield cfg_dir
