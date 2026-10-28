from __future__ import annotations

import fcntl
import hashlib
import itertools
import json
import os
import re
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


def calibration_key(backend, config) -> str:
    """Portability key used by Phase 7 for calibration grouping."""
    try:
        return f"{config.get('model')}|{config.get('device')}|{config.get('compute_type')}|{backend}|beam={config.get('beam_size')}|vad={int(bool(config.get('vad_filter')))}|lang={config.get('language')}|chunk={config.get('chunk_s')}"
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
    "eta_remaining_s", "eta_confidence", "eta_source", "overrun", "report_path"
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
                  eta_confidence=None, eta_source=None, overrun=False, report_path=None):
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


def get_calibration_path() -> Path:
    return get_metrics_dir() / CALIBRATION_FILENAME


def reset_calibration() -> bool:
    try:
        p = get_calibration_path()
        if p.exists():
            p.unlink()
        return True
    except Exception:
        return False


def load_calibration():
    try:
        p = get_calibration_path()
        if not p.exists():
            return {}
        content = p.read_text()
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


def _is_calibration_excluded(record: dict) -> bool:
    try:
        outcome = record.get("outcome")
        if outcome in {"error", "cancelled", "watchdog_timeout", "abandoned"}:
            return True
        if record.get("fallback_used"):
            return True
        config = record.get("config") or {}
        if config.get("device") == "cuda" and record.get("outcome") != "success":
            # exclude if fallback/failed in some cases - be conservative
            pass
    except Exception:
        pass
    return False


def fit_calibration_from_ledger(max_runs: int = 1000):
    """Fit calibration from ledger. Excludes failures/fallbacks/outliers/cold/high-load from fitting but keeps records."""
    cal = load_calibration()
    # Build buckets by calibration_key
    buckets = {}
    try:
        for rec in read_ledger_rows():
            if not isinstance(rec, dict):
                continue
            if rec.get("source") != "stt":
                continue
            if _is_calibration_excluded(rec):
                continue
            key = rec.get("calibration_key") or calibration_key(rec.get("backend"), rec.get("config") or {})
            if not key:
                continue
            actual = rec.get("actual") or {}
            total_ms = actual.get("total_ms")
            audio_s = rec.get("audio_s")
            if total_ms is None or audio_s is None:
                continue
            try:
                if float(audio_s) <= 0:
                    continue
            except Exception:
                continue
            buckets.setdefault(key, []).append({
                "total_ms": float(total_ms),
                "audio_s": float(audio_s),
                "predicted": rec.get("predicted") or {}
            })
    except Exception:
        pass
    
    # Fit ratio-of-sums style rates per component
    for key, samples in buckets.items():
        if len(samples) < 3:  # min n=3
            continue
        # Compute ratio of sums for rate component: (sum total - sum fixed)/sum audio
        sum_audio = sum(s["audio_s"] for s in samples)
        sum_total_ms = sum(s["total_ms"] for s in samples)
        # Use priors as baseline fixed components, compute effective rate
        rtf_eff = (sum_total_ms / 1000.0 - (PRIOR_FINALIZE_S + PRIOR_LOAD_S + PRIOR_INSERT_S)) / sum_audio if sum_audio > 0 else PRIOR_RTF.get("medium", 0.95)
        if rtf_eff < 0.01 or rtf_eff > 10.0:
            continue  # outlier
        # median-based smoothing
        try:
            rtf_vals = [(s["total_ms"] / 1000.0 - (PRIOR_FINALIZE_S + PRIOR_LOAD_S + PRIOR_INSERT_S)) / s["audio_s"] if s["audio_s"] > 0 else None for s in samples]
            rtf_vals = [v for v in rtf_vals if v is not None and 0.01 < v < 10.0]
            if len(rtf_vals) >= 3:
                import statistics
                med = statistics.median(rtf_vals)
                # shrinkage toward prior
                rtf_eff = 0.7 * med + 0.3 * PRIOR_RTF.get("medium", 0.95)
        except Exception:
            pass
        cal[key] = {
            "rtf": round(float(rtf_eff), 4),
            "n": len(samples),
            "finalize_s": PRIOR_FINALIZE_S,
            "load_s": PRIOR_LOAD_S,
            "insert_s": PRIOR_INSERT_S,
            "updated_at": time.time()
        }
    save_calibration(cal)
    return cal


def calibrated_eta_seconds(audio_s, model=None, backend=None, config=None, calibration_key_val=None):
    """Compute ETA with calibration. Returns (eta_seconds, source, key_level, n, confidence)."""
    if os.getenv("VOICE_ETA", "").strip().lower() in {"0", "false", "no", "off", ""} and os.getenv("VOICE_ETA") is not None:
        # If explicitly off
        pass
    cal = load_calibration()
    if config is None:
        config = {}
    if calibration_key_val is None and backend is not None:
        try:
            calibration_key_val = calibration_key(backend, config)
        except Exception:
            calibration_key_val = None
    
    # Try full key first, then fallback hierarchy
    key_level = None
    n = 0
    rtf = None
    source = "prior"
    confidence = "low"
    
    if calibration_key_val and calibration_key_val in cal:
        entry = cal[calibration_key_val]
        if entry.get("n", 0) >= 3:
            rtf = entry.get("rtf")
            n = entry.get("n")
            key_level = calibration_key_val
            source = "calibrated"
            confidence = "medium" if n >= 10 else "low"
    else:
        # Try fallbacks by prefix
        if calibration_key_val:
            try:
                parts = calibration_key_val.split("|")
                # Try without some parts
                for drop in range(1, len(parts)):
                    k2 = "|".join(parts[:len(parts)-drop]) if drop > 0 else parts[0]
                    if k2 in cal and cal[k2].get("n", 0) >= 3:
                        entry = cal[k2]
                        rtf = entry.get("rtf")
                        n = entry.get("n")
                        key_level = k2
                        source = "calibrated"
                        confidence = "low"
                        break
            except Exception:
                pass
    
    if rtf is None:
        # Use prior
        try:
            model_str = str(model).lower() if model is not None else "medium"
            prefix = model_str.split(".")[0].split("-")[0]
            rtf = PRIOR_RTF.get(prefix, PRIOR_RTF["medium"])
        except Exception:
            rtf = PRIOR_RTF.get("medium", 0.95)
        source = "prior"
        key_level = f"prior:{prefix if 'prefix' in locals() else 'medium'}"
        n = 0
        confidence = "low"
    
    try:
        finalize_s = PRIOR_FINALIZE_S
        load_s = PRIOR_LOAD_S
        insert_s = PRIOR_INSERT_S
        eta = finalize_s + load_s + float(rtf) * max(0.0, float(audio_s)) + insert_s
        eta = round(max(0.0, float(eta)), 2)
        return eta, source, key_level, n, confidence
    except Exception:
        eta = prior_eta_seconds(audio_s, model)
        return eta, "prior", f"prior:{model}", 0, "low"
