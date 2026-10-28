from __future__ import annotations

import fcntl
import hashlib
import itertools
import json
import os
import re
import statistics
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

LEDGER_ROTATE_BYTES = 5_000_000
_archive_seq = itertools.count(1)

SCHEMA_V1_KEYS = {
    "schema", "source", "run_id", "install_id", "ts_start", "ts_end",
    "outcome", "error_stage", "actual", "predicted", "audio_s",
    "chars_out", "chars_typed", "fallback_used", "insert_ok",
    "segments", "config", "backend", "calibration_key", "tts"
}

NESTED_KEYS = {
    "actual": {"total_ms", "finalize_ms", "load_ms", "decode_ms", "insert_ms"},
    "predicted": {"shown_s", "shown_at_epoch", "source", "key_level", "n", "confidence", "revisions", "actual_s"},
    "segments": {"idx", "audio_s", "decode_ms", "chars", "ok", "fallback", "avg_logprob", "compression_ratio", "no_speech_prob", "temperature", "vad_audio_s", "error_type"},
    "config": {"model", "device", "compute_type", "beam_size", "vad_filter", "language", "chunk_s"},
    "tts": {"predicted_ms", "actual_ms", "chars", "voice", "backend", "synth_ms", "play_ms"},
}


def _empty_actual() -> dict:
    return {"total_ms": None, "finalize_ms": None, "load_ms": None, "decode_ms": None, "insert_ms": None}


def _empty_predicted() -> dict:
    return {"shown_s": None, "shown_at_epoch": None, "source": None, "key_level": None, "n": None, "confidence": None, "revisions": None, "actual_s": None}


def _empty_config() -> dict:
    return {"model": None, "device": None, "compute_type": None, "beam_size": None, "vad_filter": None, "language": None, "chunk_s": None}


def tts_reserved() -> dict:
    return {"predicted_ms": None, "actual_ms": None, "chars": None, "voice": None, "backend": None, "synth_ms": None, "play_ms": None}


def validate_record(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")
    for key in record:
        if key not in SCHEMA_V1_KEYS:
            raise ValueError(f"unknown key: {key}")
    if record.get("schema") != 1:
        raise ValueError("schema must be 1")
    if record.get("source") not in {"stt", "tts"}:
        raise ValueError("invalid source")
    if record.get("outcome") not in {"success", "cancelled", "error", "watchdog_timeout", "abandoned"}:
        raise ValueError("invalid outcome")
    
    actual = record.get("actual")
    if isinstance(actual, dict):
        for k in actual:
            if k not in NESTED_KEYS["actual"]:
                raise ValueError(f"unknown key: actual.{k}")
    predicted = record.get("predicted")
    if isinstance(predicted, dict):
        for k in predicted:
            if k not in NESTED_KEYS["predicted"]:
                raise ValueError(f"unknown key: predicted.{k}")
    config = record.get("config")
    if isinstance(config, dict):
        for k in config:
            if k not in NESTED_KEYS["config"]:
                raise ValueError(f"unknown key: config.{k}")
    tts = record.get("tts")
    if isinstance(tts, dict):
        for k in tts:
            if k not in NESTED_KEYS["tts"]:
                raise ValueError(f"unknown key: tts.{k}")
    
    segments = record.get("segments")
    if segments is not None:
        if not isinstance(segments, list):
            raise ValueError("segments must be a list")
        for seg in segments:
            if not isinstance(seg, dict):
                raise ValueError("segment must be a dict")
            for k in seg:
                if k not in NESTED_KEYS["segments"]:
                    raise ValueError(f"unknown key: segments.{k}")
    
    # Ensure JSON serializable
    json.dumps(record)
    return record


def get_install_id() -> str:
    state_dir = get_state_dir()
    install_id_path = state_dir / "install_id"
    install_salt_path = state_dir / "install_salt"
    try:
        if install_id_path.exists():
            content = install_id_path.read_text().strip()
            if len(content) == 32 and all(c in "0123456789abcdef" for c in content):
                return content
    except Exception:
        pass
    
    # Generate new install_id
    try:
        if install_salt_path.exists():
            salt = install_salt_path.read_bytes()
        else:
            salt = os.urandom(32)
            atomic_write_text(install_salt_path, salt.hex(), 0o600)  # store hex
            # Better to store raw bytes as hex string properly
            install_salt_path.write_bytes(salt)
            try:
                os.chmod(install_salt_path, 0o600)
            except Exception:
                pass
    except Exception:
        salt = os.urandom(32)
    
    # Get machine_id
    machine_id = None
    try:
        machine_id_bytes = Path("/etc/machine-id").read_bytes().strip()
        machine_id = machine_id_bytes
    except Exception:
        machine_id = os.urandom(16)
    
    install_id = hashlib.sha256(salt + b":" + machine_id).hexdigest()[:32]
    try:
        atomic_write_text(install_id_path, install_id, 0o600)
    except Exception:
        try:
            install_id_path.write_text(install_id)
            os.chmod(install_id_path, 0o600)
        except Exception:
            pass
    return install_id


def extract_hierarchy_keys(config: Optional[dict], backend: Optional[str]) -> dict[str, str]:
    """Extracts 4-tier hierarchy keys: L0 (8 fields) -> L1 (6 fields) -> L2 (4 fields) -> L3 (prior model)."""
    cfg = config or {}
    model = cfg.get("model") or "medium"
    device = cfg.get("device") or "cpu"
    compute_type = cfg.get("compute_type") or "int8"
    b = backend or f"{device}, {compute_type}"
    beam = cfg.get("beam_size") if cfg.get("beam_size") is not None else 1
    if "vad_filter" in cfg and cfg.get("vad_filter") is not None:
        vad = int(bool(cfg.get("vad_filter")))
    else:
        vad = 1
    lang = cfg.get("language") or "auto"
    chunk = cfg.get("chunk_s") if cfg.get("chunk_s") is not None else 180.0
    prefix = str(model).lower().split(".")[0].split("-")[0]

    return {
        "L0": f"{model}|{device}|{compute_type}|{b}|beam={beam}|vad={vad}|lang={lang}|chunk={chunk}",
        "L1": f"{model}|{device}|{compute_type}|{b}|beam={beam}|lang={lang}",
        "L2": f"{model}|{device}|{compute_type}|{b}",
        "L3": f"prior:{prefix}",
    }


def calibration_key(backend, config) -> str:
    """Portability key used by Phase 7 for calibration grouping."""
    try:
        return extract_hierarchy_keys(config, backend)["L0"]
    except Exception:
        return str(backend)


def build_record(*, run_id, install_id, ts_start, ts_end, outcome, error_stage=None,
                  actual=None, predicted=None, audio_s=0.0, chars_out=0, chars_typed=0,
                  fallback_used=False, insert_ok=False, segments=None, config=None,
                  backend=None, tts=None, source="stt", calibration_key_val=None) -> dict:
    record = {}
    record["schema"] = 1
    record["source"] = source  # no TTS code path may call with source="tts" in this phase
    record["run_id"] = run_id
    record["install_id"] = install_id
    record["ts_start"] = ts_start
    record["ts_end"] = ts_end
    record["outcome"] = outcome
    record["error_stage"] = error_stage
    
    actual_filled = _empty_actual()
    if actual and isinstance(actual, dict):
        for k in actual_filled:
            if k in actual:
                actual_filled[k] = actual[k]
    # coerce
    for k in ["total_ms", "finalize_ms", "load_ms", "decode_ms", "insert_ms"]:
        if actual_filled[k] is not None:
            try:
                actual_filled[k] = float(actual_filled[k])
            except Exception:
                pass
    record["actual"] = actual_filled
    
    predicted_filled = _empty_predicted()
    if predicted and isinstance(predicted, dict):
        for k in predicted_filled:
            if k in predicted:
                predicted_filled[k] = predicted[k]
    record["predicted"] = predicted_filled
    
    try:
        record["audio_s"] = float(audio_s)
    except Exception:
        record["audio_s"] = 0.0
    try:
        record["chars_out"] = int(chars_out)
    except Exception:
        record["chars_out"] = 0
    try:
        record["chars_typed"] = int(chars_typed)
    except Exception:
        record["chars_typed"] = 0
    record["fallback_used"] = bool(fallback_used)
    record["insert_ok"] = bool(insert_ok)
    
    record["segments"] = segments if segments is not None else []
    
    config_filled = _empty_config()
    if config and isinstance(config, dict):
        for k in config_filled:
            if k in config:
                config_filled[k] = config[k]
    record["config"] = config_filled
    
    record["backend"] = backend
    if calibration_key_val is None and backend is not None and config_filled:
        try:
            calibration_key_val = calibration_key(backend, config_filled)
        except Exception:
            calibration_key_val = None
    record["calibration_key"] = calibration_key_val
    
    record["tts"] = tts if tts is not None else tts_reserved()
    
    return validate_record(record)


def _archive_path(path: Path) -> Path:
    ts = time.strftime('%Y%m%dT%H%M%S', time.gmtime())
    pid = os.getpid()
    seq = next(_archive_seq)
    candidate = path.with_name(f"metrics-{ts}-{pid}-{seq:06d}.jsonl")
    # Ensure unique
    counter = 0
    while candidate.exists() and counter < 1000:
        counter += 1
        candidate = path.with_name(f"metrics-{ts}-{pid}-{seq:06d}-{counter}.jsonl")
    return candidate


def read_ledger_rows(paths=None):
    metrics_dir = get_metrics_dir()
    all_paths = []
    if paths is not None:
        all_paths = list(paths)
    else:
        main = get_ledger_path()
        if main.exists():
            all_paths.append(main)
        # archives
        try:
            for p in sorted(metrics_dir.glob("metrics-*.jsonl")):
                all_paths.append(p)
        except Exception:
            pass
    for p in all_paths:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict) and obj.get("schema") == 1:
                            yield obj
                    except Exception:
                        continue
        except Exception:
            continue


def ledger_health():
    metrics_dir = get_metrics_dir()
    main = get_ledger_path()
    try:
        archives = len(list(metrics_dir.glob("metrics-*.jsonl")))
    except Exception:
        archives = 0
    exists = main.exists()
    size = main.stat().st_size if exists else 0
    try:
        rows = len(list(read_ledger_rows()))
    except Exception:
        rows = 0
    return {
        "path": str(main),
        "exists": exists,
        "bytes": size,
        "rows": rows,
        "archives": archives,
        "enabled": get_metrics_enabled(),
    }





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
    try:
        validate_record(record)
    except Exception:
        raise
    path = get_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.exists():
            try:
                if path.stat().st_size >= LEDGER_ROTATE_BYTES:
                    try:
                        archived = _archive_path(path)
                        os.replace(path, archived)
                    except OSError as e:
                        print(f"telemetry rotation failed: {e}", file=__import__('sys').stderr)
            except Exception:
                pass
    except Exception:
        pass
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
    try:
        status_to_write = dict(status)
        status_to_write.setdefault("schema", STATUS_SCHEMA_VERSION)
        status_to_write["updated_at"] = time.time()
        validate_status(status_to_write)
        atomic_write_json(get_state_dir() / STATUS_FILENAME, status_to_write, 0o600)
        return True
    except Exception:
        raise


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


# Status contract v1
STATUS_V1_KEYS = [
    "schema", "pid", "run_id", "state", "phase", "started_at", "updated_at",
    "expires_at", "audio_s", "segments", "segments_done", "eta_epoch",
    "eta_remaining_s", "eta_confidence", "eta_source", "overrun", "report_path",
    "revision_count", "last_revised_at", "key_level", "key_n"
]
PID_STATES = ("starting", "recording", "transcribing", "typing", "speaking")
STATUS_PHASES = ("init", "capture", "finalize", "load", "decode", "insert", "wrap-up")
STATUS_HEARTBEAT_S = 5.0
STATUS_TTL_S = 30.0
STATUS_MAX_BYTES = 1024

PRIOR_RTF = {"tiny": 0.25, "base": 0.35, "small": 0.55, "medium": 0.95, "large": 1.6, "turbo": 1.0}
PRIOR_FINALIZE_S = 0.4
PRIOR_LOAD_S = 1.2
PRIOR_INSERT_S = 0.2


def prior_eta_seconds(audio_s, model=None):
    try:
        model_str = str(model).lower() if model is not None else "medium"
        prefix = model_str.split(".")[0].split("-")[0]
        rtf = PRIOR_RTF.get(prefix, PRIOR_RTF["medium"])
        return round(PRIOR_FINALIZE_S + PRIOR_LOAD_S + rtf * max(0.0, float(audio_s)) + PRIOR_INSERT_S, 2)
    except Exception:
        return round(PRIOR_FINALIZE_S + PRIOR_LOAD_S + PRIOR_RTF["medium"] * max(0.0, float(audio_s)) + PRIOR_INSERT_S, 2)


def build_status(*, pid, run_id, state, phase, started_at, updated_at=None, expires_at=None,
                  audio_s=0.0, segments=0, segments_done=0, eta_epoch=None, eta_remaining_s=None,
                  eta_confidence=None, eta_source=None, overrun=False, report_path=None,
                  revision_count: int = 0, last_revised_at: Optional[float] = None,
                  key_level: Optional[str] = None, key_n: Optional[int] = None):
    now = time.time()
    if updated_at is None:
        updated_at = now
    # Clamp negative ETA
    if eta_remaining_s is not None:
        try:
            if float(eta_remaining_s) < 0:
                eta_remaining_s = 0.0
        except Exception:
            pass
    try:
        audio_s_r = round(float(audio_s), 3)
    except Exception:
        audio_s_r = 0.0
    try:
        segments_i = int(segments)
    except Exception:
        segments_i = 0
    try:
        segments_done_i = int(segments_done)
    except Exception:
        segments_done_i = 0
    if segments_i > 0 and segments_done_i > segments_i:
        segments_done_i = segments_i
    if eta_remaining_s is not None:
        try:
            eta_remaining_s_r = round(float(eta_remaining_s), 2)
        except Exception:
            eta_remaining_s_r = eta_remaining_s
    else:
        eta_remaining_s_r = None
    if eta_epoch is None and eta_remaining_s_r is not None:
        try:
            eta_epoch = round(float(updated_at) + float(eta_remaining_s_r), 3)
        except Exception:
            eta_epoch = None
    elif eta_epoch is not None:
        try:
            eta_epoch = eta_epoch
        except Exception:
            pass
    if expires_at is None:
        expires_at = round(float(updated_at) + STATUS_TTL_S, 3)
    else:
        try:
            expires_at = round(float(expires_at), 3)
        except Exception:
            expires_at = round(float(updated_at) + STATUS_TTL_S, 3)
    
    status = {}
    status["schema"] = 1
    status["pid"] = int(pid)
    status["run_id"] = run_id
    status["state"] = state
    status["phase"] = phase
    status["started_at"] = started_at
    status["updated_at"] = updated_at
    status["expires_at"] = expires_at
    status["audio_s"] = audio_s_r
    status["segments"] = segments_i
    status["segments_done"] = segments_done_i
    status["eta_epoch"] = eta_epoch
    status["eta_remaining_s"] = eta_remaining_s_r
    status["eta_confidence"] = eta_confidence
    status["eta_source"] = eta_source
    status["overrun"] = bool(overrun)
    status["report_path"] = report_path
    status["revision_count"] = max(0, int(revision_count)) if revision_count is not None else 0
    status["last_revised_at"] = float(last_revised_at) if last_revised_at is not None else None
    status["key_level"] = str(key_level) if key_level is not None else None
    status["key_n"] = max(0, int(key_n)) if key_n is not None else None
    return validate_status(status)


def validate_status(status):
    if not isinstance(status, dict):
        raise ValueError("status must be dict")
    for k in status:
        if k not in STATUS_V1_KEYS:
            raise ValueError(f"unknown key: {k}")
    if status.get("schema") != 1:
        raise ValueError("schema must be 1")
    if status.get("state") not in PID_STATES:
        raise ValueError("invalid state")
    if status.get("phase") not in STATUS_PHASES:
        raise ValueError("invalid phase")
    try:
        pid = status.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            raise ValueError("invalid pid")
    except Exception:
        raise ValueError("invalid pid")
    run_id = status.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("invalid run_id")
    rev_cnt = status.get("revision_count")
    if rev_cnt is not None:
        if not isinstance(rev_cnt, int) or rev_cnt < 0:
            raise ValueError("revision_count must be a non-negative integer")
    kn = status.get("key_n")
    if kn is not None:
        if not isinstance(kn, int) or kn < 0:
            raise ValueError("key_n must be a non-negative integer")
    eta_remain = status.get("eta_remaining_s")
    if eta_remain is not None:
        try:
            if float(eta_remain) < 0:
                raise ValueError("negative eta")
        except ValueError:
            raise
        except Exception:
            pass
    segments = status.get("segments", 0)
    segments_done = status.get("segments_done", 0)
    try:
        if int(segments) > 0 and int(segments_done) > int(segments):
            raise ValueError("segments_done > segments")
    except ValueError:
        raise
    except Exception:
        pass
    try:
        s = json.dumps(status, separators=(",", ":"), ensure_ascii=True)
        if len(s.encode("utf-8")) > STATUS_MAX_BYTES:
            raise ValueError("status too large")
    except ValueError:
        raise
    except Exception:
        pass
    return status


def status_expired(status, now=None):
    if not isinstance(status, dict):
        return True
    try:
        expires_at = status.get("expires_at")
        if expires_at is None:
            return True
        if now is None:
            now = time.time()
        return float(now) >= float(expires_at)
    except Exception:
        return True




# ETA/Calibration (Phase 7)
CALIBRATION_FILENAME = "calibration.json"
CALIBRATION_RESET_FILENAME = ".calibration_reset"


def get_calibration_path() -> Path:
    return get_metrics_dir() / CALIBRATION_FILENAME


def get_calibration_reset_path() -> Path:
    return get_metrics_dir() / CALIBRATION_RESET_FILENAME


def get_calibration_reset_timestamp() -> Optional[float]:
    p = get_calibration_reset_path()
    try:
        if p.exists():
            return float(p.read_text().strip())
    except Exception:
        pass
    return None


def reset_calibration() -> bool:
    try:
        p = get_calibration_path()
        if p.exists():
            p.unlink()
        reset_p = get_calibration_reset_path()
        atomic_write_text(reset_p, str(time.time()), 0o600)
        return True
    except Exception:
        return False


def load_calibration() -> dict:
    try:
        p = get_calibration_path()
        if not p.exists():
            return {}
        content = p.read_text(encoding="utf-8")
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_calibration(data: dict) -> bool:
    try:
        p = get_calibration_path()
        atomic_write_json(p, data, 0o600)
        return True
    except Exception:
        return False


def check_and_mark_boot_session(state_dir: Optional[Path] = None) -> bool:
    """Returns True if this is the first run after system boot (cold run)."""
    if state_dir is None:
        state_dir = get_state_dir()
    marker = Path(state_dir) / ".boot_session"
    if marker.exists():
        return False
    try:
        marker.touch(mode=0o600)
    except OSError:
        pass
    return True


def compute_mad_confidence(residuals: list[float]) -> float:
    """Computes confidence score: 1.0 - MAD / median_residual clamped [0.0, 1.0]."""
    if not residuals or len(residuals) < 3:
        return 0.0
    try:
        med = statistics.median(residuals)
        if med <= 0.0:
            return 1.0
        deviations = [abs(r - med) for r in residuals]
        mad = statistics.median(deviations)
        ratio = mad / med
        return round(max(0.0, min(1.0, 1.0 - ratio)), 3)
    except Exception:
        return 0.0


def _is_calibration_excluded(record: dict) -> bool:
    try:
        if record.get("outcome") != "success":
            return True
        if record.get("fallback_used"):
            return True
        actual = record.get("actual") or {}
        load_ms = actual.get("load_ms")
        # Contention proxy: load_ms > 3x calibrated/prior load (1.2s prior * 3 = 3600ms)
        if load_ms is not None and float(load_ms) > 3600.0:
            return True
        pred = record.get("predicted") or {}
        if pred.get("source") == "cold":
            return True
        audio_s = float(record.get("audio_s") or 0.0)
        decode_ms = actual.get("decode_ms")
        if decode_ms is None or audio_s <= 0.0:
            return True
        decode_s = float(decode_ms) / 1000.0
        rate = decode_s / audio_s
        if rate < 0.01 or rate > 10.0:
            return True
    except Exception:
        pass
    return False


def _get_acc(accumulators: dict, tier: str, key: Optional[str]) -> dict:
    if not isinstance(accumulators, dict) or not key:
        return {}
    tier_map = accumulators.get(tier)
    if isinstance(tier_map, dict) and key in tier_map:
        return tier_map[key]
    if key in accumulators and isinstance(accumulators[key], dict):
        return accumulators[key]
    return {}


def resolve_calibrated_rate(keys: dict[str, str], accumulators: dict, prior_rtf: float) -> tuple[float, str, int]:
    """Resolves rate using hierarchy fallback with James-Stein shrinkage blending."""
    # L2 rate resolution
    l2_key = keys.get("L2")
    l2_acc = _get_acc(accumulators, "L2", l2_key)
    l2_n = l2_acc.get("n", 0)
    l2_audio = l2_acc.get("sum_audio_s", 0.0)
    l2_decode = l2_acc.get("sum_decode_s", 0.0)
    if l2_n >= 3 and l2_audio > 0:
        raw_l2 = l2_decode / l2_audio
        if 0.01 <= raw_l2 <= 10.0:
            w2 = min(1.0, l2_n / 10.0)
            rate_l2 = w2 * raw_l2 + (1.0 - w2) * prior_rtf
            valid_l2 = True
        else:
            rate_l2 = prior_rtf
            valid_l2 = False
    else:
        rate_l2 = prior_rtf
        valid_l2 = False

    # L1 rate resolution
    l1_key = keys.get("L1")
    l1_acc = _get_acc(accumulators, "L1", l1_key)
    l1_n = l1_acc.get("n", 0)
    l1_audio = l1_acc.get("sum_audio_s", 0.0)
    l1_decode = l1_acc.get("sum_decode_s", 0.0)
    if l1_n >= 3 and l1_audio > 0:
        raw_l1 = l1_decode / l1_audio
        if 0.01 <= raw_l1 <= 10.0:
            w1 = min(1.0, l1_n / 10.0)
            rate_l1 = w1 * raw_l1 + (1.0 - w1) * rate_l2
            valid_l1 = True
        else:
            rate_l1 = rate_l2
            valid_l1 = False
    else:
        rate_l1 = rate_l2
        valid_l1 = False

    # L0 rate resolution
    l0_key = keys.get("L0")
    l0_acc = _get_acc(accumulators, "L0", l0_key)
    l0_n = l0_acc.get("n", 0)
    l0_audio = l0_acc.get("sum_audio_s", 0.0)
    l0_decode = l0_acc.get("sum_decode_s", 0.0)
    if l0_n >= 3 and l0_audio > 0:
        raw_l0 = l0_decode / l0_audio
        if 0.01 <= raw_l0 <= 10.0:
            w0 = min(1.0, l0_n / 10.0)
            rate_l0 = w0 * raw_l0 + (1.0 - w0) * rate_l1
            valid_l0 = True
        else:
            rate_l0 = rate_l1
            valid_l0 = False
    else:
        rate_l0 = rate_l1
        valid_l0 = False

    if valid_l0:
        return rate_l0, "L0", l0_n
    elif valid_l1:
        return rate_l1, "L1", l1_n
    elif valid_l2:
        return rate_l2, "L2", l2_n
    else:
        return prior_rtf, "L3", 0


def update_calibration_from_run(record: dict, cal_data: Optional[dict] = None) -> bool:
    """Updates calibration cache accumulators from a completed run record."""
    if not isinstance(record, dict):
        return False
    if _is_calibration_excluded(record):
        return False

    save_needed = False
    if cal_data is None:
        cal = load_calibration()
        save_needed = True
    else:
        cal = cal_data

    cal.setdefault("accumulators", {"L0": {}, "L1": {}, "L2": {}})
    accs = cal["accumulators"]
    if not isinstance(accs, dict):
        accs = {"L0": {}, "L1": {}, "L2": {}}
        cal["accumulators"] = accs
    for tier in ("L0", "L1", "L2"):
        accs.setdefault(tier, {})

    actual = record.get("actual") or {}
    decode_ms = actual.get("decode_ms")
    audio_s = record.get("audio_s")
    if decode_ms is None or audio_s is None:
        return False
    try:
        audio_s = float(audio_s)
        decode_s = float(decode_ms) / 1000.0
        if audio_s <= 0 or decode_s <= 0:
            return False
    except Exception:
        return False

    config = record.get("config") or {}
    backend = record.get("backend") or "cpu, int8"
    keys = extract_hierarchy_keys(config, backend)

    load_ms = actual.get("load_ms")
    load_s = float(load_ms) / 1000.0 if load_ms is not None else PRIOR_LOAD_S

    for tier in ("L0", "L1", "L2"):
        tier_key = keys.get(tier)
        if not tier_key:
            continue
        tier_dict = accs[tier]
        entry = tier_dict.setdefault(tier_key, {
            "sum_decode_s": 0.0,
            "sum_audio_s": 0.0,
            "n": 0,
            "load_s": PRIOR_LOAD_S
        })
        entry["sum_decode_s"] += decode_s
        entry["sum_audio_s"] += audio_s
        entry["n"] += 1
        entry["load_s"] = round((entry.get("load_s", PRIOR_LOAD_S) * (entry["n"] - 1) + load_s) / entry["n"], 4)

    # Residuals tracking
    predicted = record.get("predicted") or {}
    actual_total_ms = actual.get("total_ms")
    shown_s = predicted.get("shown_s")
    if actual_total_ms is not None and shown_s is not None:
        try:
            res = abs(float(shown_s) - (float(actual_total_ms) / 1000.0))
            residuals = cal.setdefault("residuals", [])
            residuals.append(round(res, 4))
            if len(residuals) > 30:
                cal["residuals"] = residuals[-30:]
            cal["confidence"] = compute_mad_confidence(cal["residuals"])
        except Exception:
            pass

    cal["updated_at"] = time.time()

    if save_needed:
        save_calibration(cal)
    return True


def rebuild_calibration_from_ledger() -> dict:
    """Rebuilds calibration.json from metrics.jsonl, respecting reset epoch."""
    cal = {"accumulators": {"L0": {}, "L1": {}, "L2": {}}, "residuals": []}
    reset_epoch = get_calibration_reset_timestamp()
    try:
        for rec in read_ledger_rows():
            if not isinstance(rec, dict):
                continue
            ts = rec.get("ts_end") or rec.get("ts_start")
            if reset_epoch is not None and ts is not None:
                try:
                    if float(ts) < reset_epoch:
                        continue
                except Exception:
                    pass
            update_calibration_from_run(rec, cal_data=cal)
    except Exception:
        pass
    save_calibration(cal)
    return cal


def fit_calibration_from_ledger(max_runs: int = 1000):
    return rebuild_calibration_from_ledger()


def calibrated_eta_seconds(audio_s, model=None, backend=None, config=None, calibration_key_val=None, elapsed_record_s=0.0, is_cold=False):
    """Compute ETA with calibration. Returns (eta_seconds, source, key_level, n, confidence)."""
    voice_eta_env = os.getenv("VOICE_ETA")
    if voice_eta_env is not None and voice_eta_env.strip().lower() in {"0", "false", "no", "off", ""}:
        return None, None, None, None, None

    cfg = dict(config) if config else {}
    if model is not None and not cfg.get("model"):
        cfg["model"] = model
    if backend is None:
        backend = f"{cfg.get('device', 'cpu')}, {cfg.get('compute_type', 'int8')}"

    keys = extract_hierarchy_keys(cfg, backend)
    model_str = str(cfg.get("model", model or "medium")).lower()
    prefix = model_str.split(".")[0].split("-")[0]
    prior_rtf = PRIOR_RTF.get(prefix, PRIOR_RTF["medium"])

    cal = load_calibration()
    accumulators = cal.get("accumulators", {})

    rate, chosen_level, n = resolve_calibrated_rate(keys, accumulators, prior_rtf)

    if is_cold:
        source = "cold"
        load_s = PRIOR_LOAD_S
        confidence = "low"
    elif chosen_level in {"L0", "L1", "L2"}:
        source = "calibrated"
        acc_entry = _get_acc(accumulators, chosen_level, keys.get(chosen_level))
        load_s = acc_entry.get("load_s", PRIOR_LOAD_S)
        mad_conf = cal.get("confidence")
        if isinstance(mad_conf, (int, float)):
            if mad_conf >= 0.75 and n >= 10:
                confidence = "high"
            elif mad_conf >= 0.4 or n >= 5:
                confidence = "medium"
            else:
                confidence = "low"
        else:
            confidence = "medium" if n >= 10 else "low"
    else:
        source = "prior"
        load_s = PRIOR_LOAD_S
        confidence = "low"

    remaining_load = max(0.0, float(load_s) - max(0.0, float(elapsed_record_s)))
    finalize_s = PRIOR_FINALIZE_S
    insert_s = PRIOR_INSERT_S
    eta = finalize_s + remaining_load + float(rate) * max(0.0, float(audio_s)) + insert_s
    eta = round(max(0.0, float(eta)), 2)
    return eta, source, chosen_level, n, confidence
