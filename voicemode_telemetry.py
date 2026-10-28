from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple


LEDGER_SCHEMA_VERSION = 1
STATUS_SCHEMA_VERSION = 1
LEDGER_FILENAME = "metrics.jsonl"
STATUS_FILENAME = "status.json"


def get_state_dir() -> Path:
    xdg_runtime_dir = os.getenv("XDG_RUNTIME_DIR", f"/tmp/voice-stt-{os.getuid()}")
    state_dir = Path(xdg_runtime_dir) / "voice-stt"
    state_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    return state_dir


def get_metrics_dir() -> Path:
    xdg_state_home = os.getenv("XDG_STATE_HOME", "~/.local/state")
    metrics_dir = Path(xdg_state_home).expanduser() / "voicemode"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(metrics_dir, 0o700)
    return metrics_dir


def get_ledger_path() -> Path:
    return get_metrics_dir() / LEDGER_FILENAME


def get_metrics_enabled() -> bool:
    value = os.getenv("VOICE_METRICS")
    if value is None:
        value = os.getenv("VOICE_TELEMETRY")
    if value is None:
        return True
    normalized = value.strip().lower()
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return True


def atomic_write_text(path: Path, content: str, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent)
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def atomic_write_json(path: Path, obj: Any, mode: int = 0o600) -> None:
    content = json.dumps(obj, separators=(",", ":"), ensure_ascii=True, sort_keys=True)
    atomic_write_text(path, content, mode)


def append_ledger_row(record: dict) -> bool:
    if not get_metrics_enabled():
        return False
    path = get_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=True, sort_keys=True) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def publish_status(status: dict) -> bool:
    if not get_metrics_enabled():
        return False
    status_to_write = dict(status)
    status_to_write.setdefault("schema", STATUS_SCHEMA_VERSION)
    status_to_write["updated_at"] = time.time()
    atomic_write_json(get_state_dir() / STATUS_FILENAME, status_to_write, 0o600)
    return True


def read_status() -> Optional[dict]:
    try:
        path = get_state_dir() / STATUS_FILENAME
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("schema") == 1:
            return data
        return None
    except Exception:
        return None


def remove_status() -> None:
    try:
        (get_state_dir() / STATUS_FILENAME).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def read_pid_state(path: Optional[Path] = None) -> Tuple[Optional[int], str]:
    if path is None:
        path = get_state_dir() / "pid"
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8")
        content = content.strip()
        if not content:
            return (None, "idle")
        # Format: "pid state\n" or just parts
        parts = content.split()
        if not parts:
            return (None, "idle")
        try:
            pid = int(parts[0])
        except ValueError:
            return (None, "idle")
        if len(parts) > 1:
            state = parts[1]
        else:
            state = "recording"
        return (pid, state)
    except FileNotFoundError:
        return (None, "idle")
    except Exception:
        return (None, "idle")


def read_pid(path: Optional[Path] = None) -> Optional[int]:
    pid, _ = read_pid_state(path)
    return pid


def write_pid_state(pid: int, state: str, path: Optional[Path] = None) -> None:
    if path is None:
        path = get_state_dir() / "pid"
    path = Path(path)
    content = f"{pid} {state}\n"
    atomic_write_text(path, content, 0o600)


def write_pid(pid: int, path: Optional[Path] = None) -> None:
    write_pid_state(pid, "running", path)


def remove_pid(pid: Optional[int] = None, path: Optional[Path] = None) -> None:
    if path is None:
        path = get_state_dir() / "pid"
    path = Path(path)
    try:
        if pid is not None:
            current_pid, _ = read_pid_state(path)
            if current_pid == pid:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            else:
                # Only remove if it matches our pid
                pass
        else:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    except Exception:
        pass


@contextmanager
def with_pid_lock(lock_path: Optional[Path] = None) -> Iterator[None]:
    if lock_path is None:
        lock_path = get_state_dir() / ".toggle.lock"
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        os.close(fd)
