#!/usr/bin/env python3
"""Desktop-global voice command for STT and TTS.

Press Super+B to start recording, press Super+B again to stop and transcribe.
Press Super+T to speak selected text, press Super+T again to stop speaking.
Ctrl+C exits.
"""

from __future__ import annotations

import os

# Pre-seed PipeWire and PulseAudio node properties before PortAudio/sounddevice initializes (D-11)
os.environ.setdefault("PULSE_PROP_application.name", "voicemode")
os.environ.setdefault("PIPEWIRE_PROPS", '{ application.name = voicemode }')

import argparse
import ast
import asyncio
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import threading
import time
import tty
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


CTRL_B = "\x02"
APP_NAME = "Voice STT"
STATE_DIR = Path(os.getenv("XDG_RUNTIME_DIR", f"/tmp/voice-stt-{os.getuid()}")) / "voice-stt"
PID_FILE = STATE_DIR / "recorder.pid"
TTS_PID_FILE = STATE_DIR / "tts.pid"
LOG_FILE = STATE_DIR / "voice.log"
TTS_LOG_FILE = STATE_DIR / "tts.log"
GNOME_BINDING_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voice-stt/"
GNOME_TTS_BINDING_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voice-tts/"
GNOME_BINDING_SCHEMA = (
    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"
    f"{GNOME_BINDING_PATH}"
)
GNOME_TTS_BINDING_SCHEMA = (
    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"
    f"{GNOME_TTS_BINDING_PATH}"
)
HYPRLAND_CUSTOM_KEYBINDS_PATH = Path.home() / ".config" / "hypr" / "custom" / "keybinds.lua"
DEFAULT_TTS_VOICE = "en-GB-RyanNeural"
DEFAULT_TTS_SPEED = 1.2
DEFAULT_TTS_BACKEND = "kokoro"
DEFAULT_KOKORO_VOICE = "af_heart"
SECONDARY_KOKORO_VOICE = "bm_george"
DEFAULT_KOKORO_LANG = "en-us"
MAX_RECORDING_SECONDS = 300.0
DEFAULT_TTS_MAX_CHARS = int(os.getenv("VOICE_TTS_MAX_CHARS", "5000"))

KOKORO_ASSETS = [
    {
        "filename": "kokoro-v1.0.onnx",
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
        "min_size": 300_000_000,
        "label": "Kokoro v1.0 ONNX model",
    },
    {
        "filename": "voices-v1.0.bin",
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        "min_size": 20_000_000,
        "label": "Kokoro v1.0 voices",
    },
]


@dataclass
class ModelState:
    model: WhisperModel
    requested_device: str
    requested_compute_type: str


@dataclass
class TtsDefaults:
    voice: str
    speed: float


class TerminalKeys:
    def __enter__(self) -> "TerminalKeys":
        if not sys.stdin.isatty():
            raise RuntimeError("voice needs an interactive terminal for Ctrl+B")
        self._fd = sys.stdin.fileno()
        self._old_attrs = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)

    def read_key(self, timeout: float = 0.1) -> Optional[str]:
        readable, _, _ = select.select([sys.stdin], [], [], timeout)
        if not readable:
            return None
        return sys.stdin.read(1)


def resample_pcm(audio: np.ndarray, orig_sr: int, target_sr: int = 16000) -> np.ndarray:
    """Resample 1D or 2D audio array from orig_sr to target_sr using linear interpolation."""
    if orig_sr == target_sr:
        return audio
    num_samples = int(round(len(audio) * float(target_sr) / orig_sr))
    orig_idx = np.arange(len(audio))
    target_idx = np.linspace(0, len(audio) - 1, num_samples)
    if audio.ndim > 1:
        resampled = np.empty((num_samples, audio.shape[1]), dtype=audio.dtype)
        for ch in range(audio.shape[1]):
            resampled[:, ch] = np.interp(target_idx, orig_idx, audio[:, ch])
        return resampled
    return np.interp(target_idx, orig_idx, audio).astype(audio.dtype)


class Recorder:
    def __init__(self, sample_rate: int = 16000, input_device: Optional[int | str] = None) -> None:
        self.target_sample_rate = sample_rate
        self.actual_sample_rate = sample_rate
        self.input_device = input_device
        self.frames: list[np.ndarray] = []
        self.statuses: list[str] = []
        self.stream: Optional[sd.InputStream] = None
        self.started_at: Optional[float] = None

    @property
    def sample_rate(self) -> int:
        return self.target_sample_rate

    @property
    def recording(self) -> bool:
        return self.stream is not None

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.statuses.append(str(status))
        self.frames.append(indata.copy())

    def start(self) -> None:
        self.frames = []
        self.statuses = []
        try:
            self.stream = sd.InputStream(
                samplerate=self.target_sample_rate,
                channels=1,
                dtype="float32",
                device=self.input_device,
                callback=self._callback,
            )
            self.actual_sample_rate = self.target_sample_rate
        except sd.PortAudioError:
            try:
                info = (
                    sd.query_devices(self.input_device, "input")
                    if self.input_device is not None
                    else sd.query_devices(kind="input")
                )
                self.actual_sample_rate = int(info["default_samplerate"])
            except Exception:
                self.actual_sample_rate = 44100

            self.stream = sd.InputStream(
                samplerate=self.actual_sample_rate,
                channels=1,
                dtype="float32",
                device=self.input_device,
                callback=self._callback,
            )
        self.stream.start()
        self.started_at = time.monotonic()

    def stop_to_wav(self, save_dir: Optional[Path]) -> tuple[Path, float, bool]:
        if self.stream is None or self.started_at is None:
            raise RuntimeError("recording is not active")

        stream = self.stream
        self.stream = None
        stream.stop()
        stream.close()

        duration = time.monotonic() - self.started_at
        self.started_at = None

        if not self.frames:
            raise RuntimeError("no audio frames were captured")

        audio = np.concatenate(self.frames, axis=0)
        audio = np.clip(audio, -1.0, 1.0)

        # Resample to target 16 kHz if recorded at hardware fallback rate
        if self.actual_sample_rate != self.target_sample_rate:
            audio = resample_pcm(audio, self.actual_sample_rate, self.target_sample_rate)

        pcm = (audio * 32767.0).astype(np.int16)

        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
            wav_path = save_dir / time.strftime("voice-%Y%m%d-%H%M%S.wav")
            should_delete = False
        else:
            temp = tempfile.NamedTemporaryFile(prefix="voice-", suffix=".wav", delete=False)
            wav_path = Path(temp.name)
            temp.close()
            should_delete = True

        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.target_sample_rate)
            wav.writeframes(pcm.tobytes())

        return wav_path, duration, should_delete


def parse_device(value: Optional[str]) -> Optional[int | str]:
    if value is None or value == "":
        return None
    return int(value) if value.isdigit() else value


def resolve_sample_rate(input_device: Optional[int | str], override: Optional[int]) -> int:
    """Resolve audio input sample rate, defaulting to 16000 Hz for Faster-Whisper."""
    if override:
        return override
    return 16000


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def load_hermes_tts_defaults() -> TtsDefaults:
    defaults = TtsDefaults(voice=DEFAULT_TTS_VOICE, speed=DEFAULT_TTS_SPEED)
    config_path = Path(os.getenv("HERMES_CONFIG", "~/.hermes/config.yaml")).expanduser()
    if not config_path.exists():
        return defaults

    try:
        import yaml

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        tts_config = data.get("tts", {}) if isinstance(data, dict) else {}
        edge_config = tts_config.get("edge", {}) if isinstance(tts_config, dict) else {}
        voice = edge_config.get("voice") or defaults.voice
        speed = edge_config.get("speed", tts_config.get("speed", defaults.speed))
        return TtsDefaults(voice=str(voice), speed=float(speed))
    except Exception:
        return defaults


def edge_rate_from_speed(speed: float) -> Optional[str]:
    if speed == 1.0:
        return None
    pct = round((speed - 1.0) * 100)
    return f"{pct:+d}%"


def voice_root() -> Path:
    return Path(__file__).resolve().parent


def default_kokoro_model_path() -> Path:
    return voice_root() / "models" / "kokoro" / "kokoro-v1.0.onnx"


def default_kokoro_voices_path() -> Path:
    return voice_root() / "models" / "kokoro" / "voices-v1.0.bin"


def clamp_tts_speed(speed: float) -> float:
    try:
        val = float(speed)
    except (TypeError, ValueError):
        val = 1.2
    return max(0.5, min(2.0, val))


def download_file_with_progress(url: str, dest_path: Path, min_size: int, label: str) -> None:
    dest_path = Path(dest_path)
    if dest_path.is_file() and dest_path.stat().st_size >= min_size:
        print(f"{label} already present and verified ({dest_path.stat().st_size:,} bytes).")
        return

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".tmp")
    if temp_path.exists():
        temp_path.unlink()

    req = urllib.request.Request(url, headers={"User-Agent": "voicemode/0.1.0"})
    print(f"Downloading {label}...")
    start_time = time.time()
    downloaded = 0
    try:
        with urllib.request.urlopen(req) as resp, open(temp_path, "wb") as f:
            total_size_hdr = resp.headers.get("Content-Length")
            total_size = int(total_size_hdr) if total_size_hdr and total_size_hdr.isdigit() else None
            chunk_size = 128 * 1024  # 128 KiB
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                elapsed = time.time() - start_time
                speed_mb = (downloaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                if total_size:
                    percent = (downloaded / total_size) * 100
                    print(
                        f"\r  {downloaded / (1024 * 1024):.1f}/{total_size / (1024 * 1024):.1f} MB ({percent:.1f}%) at {speed_mb:.1f} MB/s",
                        end="",
                        flush=True,
                    )
                else:
                    print(f"\r  {downloaded / (1024 * 1024):.1f} MB at {speed_mb:.1f} MB/s", end="", flush=True)
        print()
        actual_size = temp_path.stat().st_size
        if actual_size < min_size:
            if temp_path.exists():
                temp_path.unlink()
            raise RuntimeError(
                f"Downloaded {label} is undersized ({actual_size:,} bytes < minimum {min_size:,} bytes)."
            )
        temp_path.replace(dest_path)
        print(f"Verified and saved {label} -> {dest_path} ({actual_size:,} bytes)")
    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


def download_tts_assets(args: argparse.Namespace) -> int:
    model_dir = voice_root() / "models" / "kokoro"
    model_dir.mkdir(parents=True, exist_ok=True)
    try:
        for asset in KOKORO_ASSETS:
            dest_path = model_dir / asset["filename"]
            download_file_with_progress(
                url=asset["url"],
                dest_path=dest_path,
                min_size=asset["min_size"],
                label=asset["label"],
            )
        print("All Kokoro TTS assets downloaded and verified successfully.")
        return 0
    except Exception as exc:
        print(f"Error downloading Kokoro TTS assets: {exc}", file=sys.stderr)
        return 1


def normalize_tts_text(text: str) -> str:
    if not text or not text.strip():
        return ""

    # Strip ANSI escape sequences
    text = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", text)

    # Markdown links: [anchor](url) -> anchor
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # URLs: domain summaries
    def _clean_url(match: re.Match) -> str:
        domain = match.group(1)
        full = match.group(0)
        trailing_punct = ""
        while full and full[-1] in ".,;:!?)]}":
            trailing_punct = full[-1] + trailing_punct
            full = full[:-1]
        return domain + trailing_punct

    text = re.sub(r"https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(?:/[^\s]*)?", _clean_url, text)

    # Code identifiers: snake_case to words
    text = re.sub(r"(?<=\w)_(?=\w)", " ", text)

    # Markdown cleanup
    text = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)

    # Path slashes to pauses
    text = re.sub(r"(?<=[a-zA-Z0-9])/(?=[a-zA-Z0-9])", ", ", text)
    text = re.sub(r"(^|\s)/+", r"\1", text)

    # Smart line pauses on unpunctuated line breaks
    text = re.sub(r"([a-zA-Z0-9])\s*\n+", r"\1. ", text)

    # Unicode punctuation normalization
    text = text.replace("—", ", ").replace("–", ", ")
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')

    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def bound_tts_text(text: str, args: argparse.Namespace) -> tuple[str, bool]:
    max_chars = getattr(args, "tts_max_chars", None)
    if max_chars is None:
        max_chars = DEFAULT_TTS_MAX_CHARS
    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        max_chars = 5000

    if len(text) > max_chars:
        truncated = text[:max_chars].strip()
        notify("Voice TTS Warning", f"Selection truncated to {max_chars:,} characters.", args)
        return truncated, True
    return text, False


def cleanup_stale_tts_files(max_age_seconds: int = 1800) -> int:
    if not STATE_DIR.is_dir():
        return 0
    now = time.time()
    removed = 0
    patterns = ("voice-tts-*.wav", "voice-tts-*.mp3", "voice-tts-*.txt")
    for pattern in patterns:
        for file_path in STATE_DIR.glob(pattern):
            try:
                if (now - file_path.stat().st_mtime) > max_age_seconds:
                    file_path.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def play_tone(args: argparse.Namespace, frequency: float, duration: float) -> None:
    if not args.beep or frequency <= 0 or duration <= 0:
        return

    sample_rate = 44100
    frames = max(1, int(sample_rate * duration))
    timeline = np.arange(frames, dtype=np.float32) / sample_rate
    samples = np.sin(2 * np.pi * frequency * timeline).astype(np.float32)

    fade_frames = min(frames // 2, int(sample_rate * 0.01))
    if fade_frames > 0:
        fade = np.linspace(0.0, 1.0, fade_frames, dtype=np.float32)
        samples[:fade_frames] *= fade
        samples[-fade_frames:] *= fade[::-1]

    volume = max(0.0, min(float(args.beep_volume), 1.0))
    audio = (samples * volume).reshape(-1, 1)
    output_device = parse_device(args.beep_output_device)

    try:
        with sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=output_device,
        ) as stream:
            stream.write(audio)
    except Exception as exc:
        print(f"Audio cue failed: {exc}", file=sys.stderr, flush=True)


def play_cue(args: argparse.Namespace, cue: str) -> None:
    if not args.beep:
        return

    patterns = {
        "start": ((880, 0.07),),
        "recording": ((1046, 0.055),),
        "stop": ((1175, 0.07), (0, 0.03), (660, 0.11)),
        "error": ((300, 0.08), (0, 0.03), (200, 0.10)),
    }
    for frequency, duration in patterns.get(cue, ()):
        if frequency <= 0:
            time.sleep(duration)
        else:
            play_tone(args, frequency, duration)


def play_cue_async(args: argparse.Namespace, cue: str) -> None:
    """Dispatch auditory cue asynchronously in a background daemon thread."""
    if not getattr(args, "beep", True):
        return
    threading.Thread(target=play_cue, args=(args, cue), daemon=True).start()


def actual_backend(model: WhisperModel) -> str:
    inner = getattr(model, "model", None)
    device = getattr(inner, "device", "unknown")
    device_index = getattr(inner, "device_index", "")
    compute_type = getattr(inner, "compute_type", "unknown")
    if device_index not in ("", None):
        return f"{device} {device_index}, {compute_type}"
    return f"{device}, {compute_type}"


def load_model(args: argparse.Namespace, *, force_cpu: bool = False) -> ModelState:
    device = "cpu" if force_cpu else args.device
    compute_type = "int8" if force_cpu and args.compute_type == "auto" else args.compute_type
    print(f"Loading faster-whisper {args.model!r} on {device} ({compute_type})...", flush=True)
    model = WhisperModel(
        args.model,
        device=device,
        compute_type=compute_type,
        local_files_only=not args.allow_download,
    )
    state = ModelState(model=model, requested_device=device, requested_compute_type=compute_type)
    print(f"Ready: {actual_backend(model)}", flush=True)
    return state


def transcribe(model_state: ModelState, wav_path: Path, args: argparse.Namespace) -> tuple[str, ModelState]:
    kwargs = {
        "beam_size": args.beam_size,
        "vad_filter": getattr(args, "vad_filter", True),
    }
    if args.language:
        kwargs["language"] = args.language

    try:
        segments, info = model_state.model.transcribe(str(wav_path), **kwargs)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, model_state
    except Exception as exc:
        if model_state.requested_device == "cpu":
            raise
        print(f"GPU/auto transcription failed ({exc}); retrying on CPU int8...", flush=True)
        cpu_state = load_model(args, force_cpu=True)
        segments, info = cpu_state.model.transcribe(str(wav_path), **kwargs)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, cpu_state


def notify(title: str, message: str, args: argparse.Namespace) -> None:
    if not getattr(args, "notify", True):
        return
    notify_send = shutil.which("notify-send")
    if not notify_send or (not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY")):
        return
    subprocess.run([notify_send, title, message], check=False, stdin=subprocess.DEVNULL)


def read_pid(path: Path = PID_FILE) -> Optional[int]:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return int(value) if value else None
    except (FileNotFoundError, ValueError, OSError):
        return None


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def remove_pid(pid: Optional[int] = None, path: Path = PID_FILE) -> None:
    current = read_pid(path)
    if pid is not None and current not in (None, pid):
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def write_pid(path: Path = PID_FILE) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")


def display_server() -> str:
    session_type = os.getenv("XDG_SESSION_TYPE", "").lower()
    if session_type in ("wayland", "x11"):
        return session_type
    if os.getenv("WAYLAND_DISPLAY"):
        return "wayland"
    if os.getenv("DISPLAY"):
        return "x11"
    return "unknown"


def copy_to_clipboard(text: str) -> bool:
    if display_server() == "wayland":
        wl_copy = shutil.which("wl-copy")
        if not os.getenv("WAYLAND_DISPLAY") or not wl_copy:
            return False
        subprocess.run([wl_copy], input=text, text=True, check=True)
        return True

    xclip = shutil.which("xclip")
    if not os.getenv("DISPLAY") or not xclip:
        return False
    subprocess.run(
        [xclip, "-selection", "clipboard"],
        input=text,
        text=True,
        check=True,
    )
    return True


def normalize_typed_text(text: str, keep_newlines: bool = False) -> str:
    """Trim transcript and collapse internal newlines to spaces unless keep_newlines is True."""
    if not text:
        return ""
    cleaned = text.strip()
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned
    if not keep_newlines:
        cleaned = re.sub(r"[\r\n]+", " ", cleaned)
    return cleaned


def resolve_wayland_backend(args: argparse.Namespace) -> Optional[str]:
    """Resolve Wayland typing backend: 'wtype', 'ydotool', or None."""
    pref = getattr(args, "wayland_backend", "auto")
    if pref == "wtype":
        return "wtype" if shutil.which("wtype") else None
    if pref == "ydotool":
        return "ydotool" if shutil.which("ydotool") else None
    # auto: prefer wtype, fallback to ydotool
    if shutil.which("wtype"):
        return "wtype"
    if shutil.which("ydotool"):
        return "ydotool"
    return None


def type_text(text: str, args: argparse.Namespace) -> bool:
    text = normalize_typed_text(text, keep_newlines=getattr(args, "keep_newlines", False))
    if not text:
        return False

    pre_delay = max(0, getattr(args, "pre_type_delay", 50))
    if pre_delay > 0:
        time.sleep(pre_delay / 1000.0)

    server = display_server()
    if server == "wayland":
        backend = resolve_wayland_backend(args)
        if backend == "wtype":
            type_delay = max(0, getattr(args, "type_delay", 2))
            cmd = ["wtype"]
            # Upstream wtype aborts with "Invalid sleep time" if -d <= 0.
            # Omitting -d defaults delay_ms to 0.
            if type_delay > 0:
                cmd.extend(["-d", str(type_delay)])
            cmd.append("-")
            try:
                subprocess.run(cmd, input=text, text=True, check=True, timeout=15.0)
                return True
            except Exception:
                # If 'auto' was requested, attempt fallback to ydotool before giving up
                if getattr(args, "wayland_backend", "auto") == "auto" and shutil.which("ydotool"):
                    try:
                        subprocess.run(
                            ["ydotool", "type", "--key-delay", str(type_delay), "--", text],
                            check=True,
                            timeout=15.0,
                        )
                        return True
                    except Exception:
                        pass
                return False

        if backend == "ydotool":
            type_delay = max(0, getattr(args, "type_delay", 2))
            try:
                subprocess.run(
                    ["ydotool", "type", "--key-delay", str(type_delay), "--", text],
                    check=True,
                    timeout=15.0,
                )
                return True
            except Exception:
                return False

        return False

    # X11 fallback
    xdotool = shutil.which("xdotool")
    if not os.getenv("DISPLAY") or not xdotool:
        return False
    try:
        subprocess.run(
            [
                xdotool,
                "type",
                "--clearmodifiers",
                "--delay",
                str(max(0, getattr(args, "type_delay", 2))),
                "--",
                text,
            ],
            check=True,
            timeout=15.0,
        )
        return True
    except Exception:
        return False


def paste_clipboard(text: str, args: argparse.Namespace, shortcut: str = "ctrl+v") -> bool:
    if not copy_to_clipboard(text):
        return False

    # Wayland clipboard readiness settling pause (D-08)
    time.sleep(0.15)

    server = display_server()
    if server == "wayland":
        backend = resolve_wayland_backend(args)
        if backend == "wtype":
            if shortcut == "ctrl+shift+v":
                cmd = ["wtype", "-M", "ctrl", "-M", "shift", "-s", "20", "-k", "v", "-s", "20", "-m", "shift", "-m", "ctrl"]
            else:
                cmd = ["wtype", "-M", "ctrl", "-s", "20", "-k", "v", "-s", "20", "-m", "ctrl"]
            try:
                subprocess.run(cmd, check=True, timeout=15.0)
                return True
            except Exception:
                if getattr(args, "wayland_backend", "auto") == "auto" and shutil.which("ydotool"):
                    try:
                        subprocess.run(["ydotool", "key", shortcut], check=True, timeout=15.0)
                        return True
                    except Exception:
                        pass
                return False

        if backend == "ydotool":
            try:
                subprocess.run(["ydotool", "key", shortcut], check=True, timeout=15.0)
                return True
            except Exception:
                return False

        return False

    # X11 fallback
    xdotool = shutil.which("xdotool")
    if not os.getenv("DISPLAY") or not xdotool:
        return False
    try:
        subprocess.run([xdotool, "key", "--clearmodifiers", shortcut], check=True, timeout=15.0)
        return True
    except Exception:
        return False


def insert_text(text: str, args: argparse.Namespace) -> bool:
    if not text or not text.strip():
        return False

    # Dual behavior (D-16): Unconditionally buffer transcript in clipboard first
    copy_to_clipboard(text)

    if not args.paste:
        return False

    try:
        if args.output_method == "type":
            success = type_text(text, args)
            if not success:
                notify(APP_NAME, "Typing failed; transcript preserved in clipboard.", args)
            return success
        if args.output_method == "paste":
            return paste_clipboard(text, args, "ctrl+v")
        if args.output_method == "terminal-paste":
            return paste_clipboard(text, args, "ctrl+shift+v")
        if args.output_method == "clipboard":
            return True
        raise ValueError(f"unknown output method: {args.output_method}")
    except Exception as exc:
        notify(APP_NAME, f"Could not insert transcript: {exc}", args)
        return False


def read_x_selection(selection: str) -> str:
    if display_server() == "wayland":
        wl_paste = shutil.which("wl-paste")
        if not os.getenv("WAYLAND_DISPLAY") or not wl_paste:
            return ""
        command = [wl_paste, "--no-newline"]
        if selection == "primary":
            command.append("--primary")
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=1.0)
        except subprocess.TimeoutExpired:
            return ""
        except Exception:
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    xclip = shutil.which("xclip")
    if not os.getenv("DISPLAY") or not xclip:
        return ""
    try:
        result = subprocess.run(
            [xclip, "-selection", selection, "-o"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.0,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def selected_or_clipboard_text() -> tuple[str, str]:
    primary = read_x_selection("primary")
    if primary:
        return primary, "selection"

    clipboard = read_x_selection("clipboard")
    if clipboard:
        return clipboard, "clipboard"

    return "", ""


async def synthesize_edge_tts(text: str, output_path: Path, args: argparse.Namespace) -> None:
    import edge_tts

    kwargs = {"voice": args.tts_voice}
    rate = edge_rate_from_speed(args.tts_speed)
    if rate:
        kwargs["rate"] = rate

    communicate = edge_tts.Communicate(text, **kwargs)
    await communicate.save(str(output_path))


def synthesize_kokoro_tts(text: str, output_path: Path, args: argparse.Namespace) -> None:
    import soundfile as sf
    from kokoro_onnx import Kokoro

    model_path = Path(args.kokoro_model).expanduser()
    voices_path = Path(args.kokoro_voices).expanduser()
    model_ok = model_path.is_file() and model_path.stat().st_size >= 300_000_000
    voices_ok = voices_path.is_file() and voices_path.stat().st_size >= 20_000_000
    if not model_ok or not voices_ok:
        print(
            "Kokoro TTS assets missing. Download them with: python voice.py --download-tts-assets",
            file=sys.stderr,
            flush=True,
        )
        notify("Voice TTS Error", "Kokoro assets missing. Run --download-tts-assets.", args)
        play_cue(args, "error")
        raise RuntimeError("Kokoro TTS assets missing. Download them with: python voice.py --download-tts-assets")

    kokoro = Kokoro(str(model_path), str(voices_path))
    text = normalize_tts_text(text)
    clamped_speed = clamp_tts_speed(args.tts_speed)
    audio, sample_rate = kokoro.create(
        text,
        voice=args.tts_voice,
        speed=clamped_speed,
        lang=args.kokoro_lang,
        trim=args.kokoro_trim,
    )
    sf.write(output_path, audio, sample_rate)


def synthesize_tts(text: str, output_path: Path, args: argparse.Namespace) -> None:
    if args.tts_backend == "edge":
        asyncio.run(synthesize_edge_tts(text, output_path, args))
        return
    if args.tts_backend == "kokoro":
        synthesize_kokoro_tts(text, output_path, args)
        return
    raise ValueError(f"unknown TTS backend: {args.tts_backend}")


def tts_audio_suffix(args: argparse.Namespace) -> str:
    return ".mp3" if args.tts_backend == "edge" else ".wav"


def play_tts_audio(audio_path: Path) -> None:
    ffplay = shutil.which("ffplay")
    if not ffplay:
        raise RuntimeError("ffplay is required to play TTS audio")
    pulse_env = os.environ.copy()
    pulse_env["PULSE_PROP_application.name"] = "voicemode"
    pulse_env["PULSE_PROP_media.name"] = "voicemode-tts"
    try:
        subprocess.run(
            [ffplay, "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "error", str(audio_path)],
            check=True,
            stdin=subprocess.DEVNULL,
            env=pulse_env,
        )
    except subprocess.CalledProcessError as exc:
        if exc.returncode in (-signal.SIGTERM, -signal.SIGINT, -15, -2, 255, 143, 130):
            raise KeyboardInterrupt from exc
        raise


def stop_tts(args: argparse.Namespace, *, quiet: bool = False) -> bool:
    pid = read_pid(TTS_PID_FILE)
    if pid and process_alive(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        remove_pid(pid, TTS_PID_FILE)
        cleanup_stale_tts_files()
        if not quiet:
            print("Stopped voice TTS.")
            notify("Voice TTS", "Speech stopped.", args)
        return True

    if pid:
        remove_pid(pid, TTS_PID_FILE)
    cleanup_stale_tts_files()
    if not quiet:
        print("Voice TTS is idle.")
    return False


def tts_background_argv(args: argparse.Namespace, text_file: Path) -> list[str]:
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--tts-background",
        "--tts-text-file",
        str(text_file),
        "--tts-backend",
        args.tts_backend,
        "--tts-voice",
        args.tts_voice,
        "--tts-speed",
        str(args.tts_speed),
        "--kokoro-model",
        str(args.kokoro_model),
        "--kokoro-voices",
        str(args.kokoro_voices),
        "--kokoro-lang",
        args.kokoro_lang,
    ]
    argv.append("--kokoro-trim" if args.kokoro_trim else "--kokoro-no-trim")
    if not args.notify:
        argv.append("--no-notify")
    return argv


def start_tts_background(text: str, args: argparse.Namespace, source: str = "text") -> int:
    cleanup_stale_tts_files()
    norm_text = normalize_tts_text(text)
    bounded_text, _ = bound_tts_text(norm_text, args)
    if not bounded_text:
        notify("Voice TTS", "No text to speak.", args)
        play_cue(args, "error")
        print("No text to speak.")
        return 1

    if args.tts_backend == "kokoro":
        model_path = Path(args.kokoro_model).expanduser()
        voices_path = Path(args.kokoro_voices).expanduser()
        model_ok = model_path.is_file() and model_path.stat().st_size >= 300_000_000
        voices_ok = voices_path.is_file() and voices_path.stat().st_size >= 20_000_000
        if not model_ok or not voices_ok:
            notify("Voice TTS Error", "Kokoro assets missing. Run --download-tts-assets.", args)
            play_cue(args, "error")
            print(
                "Kokoro TTS assets missing. Download them with: python voice.py --download-tts-assets",
                file=sys.stderr,
            )
            return 1

    stop_tts(args, quiet=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp = tempfile.NamedTemporaryFile(
        prefix="voice-tts-", suffix=".txt", dir=STATE_DIR, mode="w", encoding="utf-8", delete=False
    )
    text_file = Path(temp.name)
    with temp:
        temp.write(bounded_text)

    log = TTS_LOG_FILE.open("a", encoding="utf-8")
    log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} speak {source} ---\n")
    log.flush()
    subprocess.Popen(
        tts_background_argv(args, text_file),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    log.close()
    print(f"Speaking {source} with {args.tts_backend}/{args.tts_voice} at {args.tts_speed:g}x.")
    return 0


def speak_selection(args: argparse.Namespace) -> int:
    cleanup_stale_tts_files()
    pid = read_pid(TTS_PID_FILE)
    if pid and process_alive(pid):
        stop_tts(args)
        return 0
    if pid:
        remove_pid(pid, TTS_PID_FILE)

    raw_text, source = selected_or_clipboard_text()
    if not raw_text:
        notify("Voice TTS", "No selected text or clipboard text.", args)
        play_cue(args, "error")
        print("No selected text or clipboard text.")
        return 1

    norm_text = normalize_tts_text(raw_text)
    bounded_text, _ = bound_tts_text(norm_text, args)
    if not bounded_text:
        notify("Voice TTS", "No text to speak.", args)
        play_cue(args, "error")
        print("No text to speak.")
        return 1

    if args.tts_backend == "kokoro":
        model_path = Path(args.kokoro_model).expanduser()
        voices_path = Path(args.kokoro_voices).expanduser()
        model_ok = model_path.is_file() and model_path.stat().st_size >= 300_000_000
        voices_ok = voices_path.is_file() and voices_path.stat().st_size >= 20_000_000
        if not model_ok or not voices_ok:
            notify("Voice TTS Error", "Kokoro assets missing. Run --download-tts-assets.", args)
            play_cue(args, "error")
            print(
                "Kokoro TTS assets missing. Download them with: python voice.py --download-tts-assets",
                file=sys.stderr,
            )
            return 1

    preview = (bounded_text[:60] + "...") if len(bounded_text) > 60 else bounded_text
    if source == "selection":
        toast_msg = f'Speaking selection: "{preview}"'
    else:
        toast_msg = f'Speaking clipboard (fallback): "{preview}"'
    notify("Voice TTS", toast_msg, args)

    return start_tts_background(bounded_text, args, source)


def run_tts_background(args: argparse.Namespace) -> int:
    if args.tts_text_file is None:
        print("voice TTS background error: missing --tts-text-file", file=sys.stderr, flush=True)
        return 1

    pid = os.getpid()
    text_file = args.tts_text_file
    audio_path: Optional[Path] = None
    should_delete_audio = False

    def request_stop(signum, frame) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGUSR1, request_stop)
    write_pid(TTS_PID_FILE)

    try:
        text = text_file.read_text(encoding="utf-8").strip()
        if not text:
            raise RuntimeError("no text to speak")

        temp = tempfile.NamedTemporaryFile(prefix="voice-tts-", suffix=tts_audio_suffix(args), delete=False)
        audio_path = Path(temp.name)
        temp.close()
        should_delete_audio = True

        notify("Voice TTS", "Speaking selected text...", args)
        print(
            f"Synthesizing {len(text)} chars with {args.tts_backend}/{args.tts_voice} at {args.tts_speed:g}x...",
            flush=True,
        )
        synthesize_tts(text, audio_path, args)
        print(f"Playing {audio_path}...", flush=True)
        play_tts_audio(audio_path)
        notify("Voice TTS", "Speech finished.", args)
        return 0
    except KeyboardInterrupt:
        print("Voice TTS stopped.", flush=True)
        return 0
    except Exception as exc:
        notify("Voice TTS", str(exc), args)
        print(f"voice TTS background error: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        try:
            text_file.unlink()
        except OSError:
            pass
        if should_delete_audio and audio_path:
            try:
                audio_path.unlink()
            except OSError:
                pass
        remove_pid(pid, TTS_PID_FILE)


def kokoro_voice_names(args: argparse.Namespace) -> list[str]:
    voices_path = Path(args.kokoro_voices).expanduser()
    if not voices_path.exists():
        raise RuntimeError(f"Kokoro voices file not found: {voices_path}")
    voices = np.load(voices_path)
    return list(sorted(voices.keys()))


def print_tts_voices(args: argparse.Namespace) -> int:
    try:
        voices = kokoro_voice_names(args)
    except Exception as exc:
        print(f"Could not list Kokoro voices: {exc}", file=sys.stderr)
        return 1

    print(f"{len(voices)} Kokoro voices")
    print(f"default: {DEFAULT_KOKORO_VOICE}")
    print(f"secondary: {SECONDARY_KOKORO_VOICE}")
    print("")
    for voice in voices:
        marker = ""
        if voice == DEFAULT_KOKORO_VOICE:
            marker = "  default"
        elif voice == SECONDARY_KOKORO_VOICE:
            marker = "  secondary"
        print(f"{voice}{marker}")
    return 0


def print_tts_check(args: argparse.Namespace) -> int:
    import importlib.metadata as importlib_metadata

    def version(package: str) -> str:
        try:
            return importlib_metadata.version(package)
        except Exception:
            return "not installed"

    print(f"backend: {args.tts_backend}")
    print(f"voice: {args.tts_voice}")
    print(f"speed: {args.tts_speed:g}x")
    if args.tts_backend == "edge":
        print(f"edge rate: {edge_rate_from_speed(args.tts_speed) or '+0%'}")
    exit_code = 0
    if args.tts_backend == "kokoro":
        model_path = Path(args.kokoro_model).expanduser()
        voices_path = Path(args.kokoro_voices).expanduser()
        print(f"kokoro model: {model_path}")
        print(f"kokoro voices: {voices_path}")
        print(f"kokoro lang: {args.kokoro_lang}")
        print(f"kokoro trim: {args.kokoro_trim}")

        model_ok = model_path.is_file() and model_path.stat().st_size >= 300_000_000
        voices_ok = voices_path.is_file() and voices_path.stat().st_size >= 20_000_000
        if not model_ok or not voices_ok:
            print("kokoro status: missing or incomplete (run 'python voice.py --download-tts-assets')")
            exit_code = 1
        else:
            try:
                from kokoro_onnx import Kokoro

                kokoro = Kokoro(str(model_path), str(voices_path))
                voice_names = kokoro.get_voices()
                print(f"kokoro status: verified ({len(voice_names)} voices loaded)")
            except Exception as exc:
                print(f"kokoro status: error loading model ({exc})")
                exit_code = 1
        print(f"secondary voice: {SECONDARY_KOKORO_VOICE}")
    print(f"edge-tts: {version('edge-tts')}")
    print(f"kokoro-onnx: {version('kokoro-onnx')}")
    print(f"soundfile: {version('soundfile')}")
    print(f"ffplay: {shutil.which('ffplay') or 'missing'}")
    print(f"xclip: {shutil.which('xclip') or 'missing'}")
    return exit_code


def background_argv(args: argparse.Namespace) -> list[str]:
    argv = [sys.executable, str(Path(__file__).resolve()), "--record-background"]
    argv += ["--model", args.model]
    argv += ["--device", args.device]
    argv += ["--compute-type", args.compute_type]
    argv += ["--beam-size", str(args.beam_size)]
    if args.language:
        argv += ["--language", args.language]
    if args.input_device:
        argv += ["--input-device", args.input_device]
    if args.sample_rate:
        argv += ["--sample-rate", str(args.sample_rate)]
    if args.save_dir:
        argv += ["--save-dir", str(args.save_dir)]
    if args.allow_download:
        argv.append("--allow-download")
    argv += ["--output-method", args.output_method]
    argv += ["--type-delay", str(args.type_delay)]
    argv += ["--recording-beep-interval", str(args.recording_beep_interval)]
    argv += ["--beep-volume", str(args.beep_volume)]
    if args.beep_output_device:
        argv += ["--beep-output-device", args.beep_output_device]
    argv.append("--beep" if args.beep else "--no-beep")
    if not args.paste:
        argv.append("--no-paste")
    if not args.notify:
        argv.append("--no-notify")
    argv += ["--wayland-backend", args.wayland_backend]
    argv += ["--pre-type-delay", str(args.pre_type_delay)]
    if getattr(args, "keep_newlines", False):
        argv.append("--keep-newlines")
    else:
        argv.append("--no-keep-newlines")
    return argv


def toggle_background_recording(args: argparse.Namespace) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    pid = read_pid()
    if pid and process_alive(pid):
        os.kill(pid, signal.SIGUSR1)
        print("Stopping voice recording...")
        return 0
    if pid:
        remove_pid(pid)

    log = LOG_FILE.open("a", encoding="utf-8")
    log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} start ---\n")
    log.flush()
    subprocess.Popen(
        background_argv(args),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    log.close()
    print("Started voice recording. Run `voice --toggle` again to stop.")
    return 0


def run_background_recording(args: argparse.Namespace) -> int:
    input_device = parse_device(args.input_device)
    sample_rate = resolve_sample_rate(input_device, args.sample_rate)
    recorder = Recorder(sample_rate=sample_rate, input_device=input_device)
    stop_requested = False
    pid = os.getpid()

    def request_stop(signum, frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGUSR1, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    write_pid()

    wav_path: Optional[Path] = None
    should_delete = False
    try:
        play_cue(args, "start")
        recorder.start()
        notify(APP_NAME, "Recording...", args)
        print(f"Recording in background at {sample_rate} Hz. PID {pid}.", flush=True)
        if args.beep and args.recording_beep_interval > 0:
            print(f"Recording reminder cue every {args.recording_beep_interval:g}s.", flush=True)
        next_recording_cue = (
            time.monotonic() + args.recording_beep_interval
            if args.beep and args.recording_beep_interval > 0
            else None
        )

        while not stop_requested:
            if recorder.started_at and (time.monotonic() - recorder.started_at) >= MAX_RECORDING_SECONDS:
                print(
                    f"Safety ceiling: reached maximum duration ({int(MAX_RECORDING_SECONDS)}s). Stopping recording.",
                    flush=True,
                )
                notify(APP_NAME, f"Max recording duration ({int(MAX_RECORDING_SECONDS)}s) reached. Transcribing...", args)
                break
            if next_recording_cue is not None and time.monotonic() >= next_recording_cue:
                play_cue(args, "recording")
                next_recording_cue = time.monotonic() + args.recording_beep_interval
            time.sleep(0.05)

        wav_path, duration, should_delete = recorder.stop_to_wav(args.save_dir)
        play_cue_async(args, "stop")
        notify(APP_NAME, "Transcribing...", args)
        print(f"Stopped ({duration:.1f}s). Transcribing {wav_path}...", flush=True)

        model_state = load_model(args)
        text, _ = transcribe(model_state, wav_path, args)
        print(text or "[no speech detected]", flush=True)

        if text and args.paste:
            if insert_text(text, args):
                print("Transcript inserted.", flush=True)
                notify(APP_NAME, "Transcript inserted.", args)
            else:
                print("Transcript insert failed.", flush=True)
                notify(APP_NAME, "Transcript insert failed; see log.", args)
        elif text:
            notify(APP_NAME, "Transcript ready; see log.", args)
        else:
            notify(APP_NAME, "No speech detected.", args)
        return 0
    except Exception as exc:
        play_cue(args, "error")
        notify(APP_NAME, str(exc), args)
        print(f"voice background error: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        if recorder.recording:
            try:
                recorder.stop_to_wav(None)
            except Exception:
                pass
        if should_delete and wav_path:
            try:
                wav_path.unlink()
            except OSError:
                pass
        remove_pid(pid)


def parse_gsettings_list(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("@as "):
        raw = raw[4:]
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def set_gnome_custom_binding(schema: str, name: str, command: str, binding: str) -> None:
    subprocess.run(["gsettings", "set", schema, "name", name], check=True)
    subprocess.run(["gsettings", "set", schema, "command", command], check=True)
    subprocess.run(["gsettings", "set", schema, "binding", binding], check=True)


def install_gnome_hotkey() -> int:
    voice_cmd = str(Path.home() / ".local" / "bin" / "voice")
    stt_command = voice_cmd + " --toggle"
    tts_command = voice_cmd + " --speak-selection"
    media_schema = "org.gnome.settings-daemon.plugins.media-keys"

    result = subprocess.run(
        ["gsettings", "get", media_schema, "custom-keybindings"],
        capture_output=True,
        text=True,
        check=True,
    )
    bindings = parse_gsettings_list(result.stdout)
    changed = False
    for path in (GNOME_BINDING_PATH, GNOME_TTS_BINDING_PATH):
        if path not in bindings:
            bindings.append(path)
            changed = True
    if changed:
        subprocess.run(
            ["gsettings", "set", media_schema, "custom-keybindings", repr(bindings)],
            check=True,
        )

    set_gnome_custom_binding(GNOME_BINDING_SCHEMA, APP_NAME, stt_command, "<Super>b")
    set_gnome_custom_binding(GNOME_TTS_BINDING_SCHEMA, "Voice TTS", tts_command, "<Super>t")
    print(f"Installed GNOME shortcut Super+B -> {stt_command}")
    print(f"Installed GNOME shortcut Super+T -> {tts_command}")
    return 0


def generate_hyprland_block() -> str:
    return (
        "-- voicemode start\n"
        'hl.unbind("SUPER + T")\n'
        'hl.bind("SUPER + SHIFT + M", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --toggle"), { description = "Voice STT: Push-to-talk toggle" })\n'
        'hl.bind("SUPER + T", hl.dsp.exec_cmd(HOME .. "/.local/bin/voice --speak-selection"), { description = "Voice TTS: Speak selection" })\n'
        "-- voicemode end\n"
    )


def is_hyprland_session() -> bool:
    if os.getenv("HYPRLAND_INSTANCE_SIGNATURE"):
        return True
    if os.getenv("XDG_CURRENT_DESKTOP") == "Hyprland":
        return True
    if shutil.which("hyprctl") and os.getenv("WAYLAND_DISPLAY"):
        return True
    return False


def print_hyprland_keybinds() -> int:
    sys.stdout.write(generate_hyprland_block())
    sys.stdout.flush()
    return 0


def install_hyprland_keybinds(config_path: Optional[Path] = None) -> int:
    raw_path = config_path if config_path is not None else HYPRLAND_CUSTOM_KEYBINDS_PATH
    resolved_path = raw_path.resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    block = generate_hyprland_block()
    pattern = re.compile(r"-- voicemode start\n.*?-- voicemode end\n?", re.DOTALL)

    if resolved_path.exists():
        content = resolved_path.read_text(encoding="utf-8")
    else:
        content = ""

    if pattern.search(content):
        new_content = pattern.sub(block, content)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        if content and not content.endswith("\n\n"):
            content += "\n"
        new_content = content + block

    resolved_path.write_text(new_content, encoding="utf-8")
    print(f"Installed Hyprland keybinds to {resolved_path} (via {raw_path})")

    if shutil.which("hyprctl"):
        try:
            subprocess.run(["hyprctl", "reload"], check=True, stdout=subprocess.DEVNULL)
            print("Reloaded Hyprland configuration.")
        except subprocess.CalledProcessError as exc:
            print(f"Warning: hyprctl reload failed (exit code {exc.returncode})", file=sys.stderr)
        except Exception as exc:
            print(f"Warning: could not run hyprctl reload: {exc}", file=sys.stderr)

    return 0


def install_hotkeys_dispatch() -> int:
    if is_hyprland_session():
        return install_hyprland_keybinds()
    return install_gnome_hotkey()


def print_status() -> int:
    pid = read_pid()
    if pid and process_alive(pid):
        print(f"recording pid {pid}")
        return 0
    if pid:
        remove_pid(pid)
    print("idle")
    return 0


def watch_log(args: argparse.Namespace) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    watched_logs = ((LOG_FILE, "STT"), (TTS_LOG_FILE, "TTS"))
    offsets = {path: path.stat().st_size if path.exists() else 0 for path, _ in watched_logs}

    print("Voice monitor running.")
    print("Press Super+B anywhere to start recording; press Super+B again to stop and transcribe.")
    print("Press Super+T to speak selected text; press Super+T again to stop speaking.")
    print("New transcript activity will appear here. Ctrl+C exits the monitor.")
    pid = read_pid()
    if pid and process_alive(pid):
        print(f"Recording is already active: pid {pid}")
    tts_pid = read_pid(TTS_PID_FILE)
    if tts_pid and process_alive(tts_pid):
        print(f"TTS is already active: pid {tts_pid}")
    print("")
    sys.stdout.flush()

    try:
        while True:
            for log_path, label in watched_logs:
                if not log_path.exists():
                    continue
                size = log_path.stat().st_size
                if size < offsets[log_path]:
                    offsets[log_path] = 0
                if size > offsets[log_path]:
                    with log_path.open("r", encoding="utf-8", errors="replace") as log:
                        log.seek(offsets[log_path])
                        data = log.read()
                        offsets[log_path] = log.tell()
                    if data:
                        if label == "TTS":
                            sys.stdout.write("[TTS]\n")
                        sys.stdout.write(data)
                        sys.stdout.flush()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nVoice monitor stopped.")
        return 0


def run_terminal_mode(args: argparse.Namespace) -> int:
    input_device = parse_device(args.input_device)
    sample_rate = resolve_sample_rate(input_device, args.sample_rate)
    args.language = args.language.strip() or None

    model_state = load_model(args)
    if args.check:
        return 0

    recorder = Recorder(sample_rate=sample_rate, input_device=input_device)
    print("")
    print("Terminal mode: press Ctrl+B here to start recording, then Ctrl+B again to stop.")
    print(f"Audio: {sample_rate} Hz mono")

    try:
        next_recording_cue = None
        with TerminalKeys() as keys:
            while True:
                key = keys.read_key()
                if next_recording_cue is not None and time.monotonic() >= next_recording_cue:
                    play_cue(args, "recording")
                    next_recording_cue = time.monotonic() + args.recording_beep_interval
                if key != CTRL_B:
                    continue

                if not recorder.recording:
                    play_cue(args, "start")
                    recorder.start()
                    print("Recording...", flush=True)
                    if args.beep and args.recording_beep_interval > 0:
                        print(f"Recording reminder cue every {args.recording_beep_interval:g}s.", flush=True)
                    next_recording_cue = (
                        time.monotonic() + args.recording_beep_interval
                        if args.beep and args.recording_beep_interval > 0
                        else None
                    )
                    continue

                wav_path, duration, should_delete = recorder.stop_to_wav(args.save_dir)
                next_recording_cue = None
                play_cue_async(args, "stop")
                print(f"Stopped ({duration:.1f}s). Transcribing...", flush=True)
                try:
                    text, model_state = transcribe(model_state, wav_path, args)
                    print("")
                    print(text or "[no speech detected]")
                    print("")
                finally:
                    if should_delete:
                        try:
                            wav_path.unlink()
                        except OSError:
                            pass
                print("Press Ctrl+B to record again. Ctrl+C exits.")
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0


def parse_args() -> argparse.Namespace:
    tts_defaults = load_hermes_tts_defaults()
    parser = argparse.ArgumentParser(description="Desktop-global STT and TTS voice command.")
    parser.add_argument("--model", default=os.getenv("VOICE_STT_MODEL", "small.en"))
    parser.add_argument("--device", default=os.getenv("VOICE_STT_DEVICE", "cpu"))
    parser.add_argument("--compute-type", default=os.getenv("VOICE_STT_COMPUTE_TYPE", "int8"))
    parser.add_argument("--language", default=os.getenv("VOICE_STT_LANGUAGE", "en"))
    parser.add_argument("--beam-size", type=int, default=int(os.getenv("VOICE_STT_BEAM_SIZE", "1")))
    parser.add_argument(
        "--vad-filter",
        dest="vad_filter",
        action="store_true",
        default=env_bool("VOICE_VAD_FILTER", True),
        help="Enable Silero VAD filter to trim silence (default: True).",
    )
    parser.add_argument(
        "--no-vad-filter",
        dest="vad_filter",
        action="store_false",
        help="Disable Silero VAD filter.",
    )
    parser.add_argument("--input-device", default=os.getenv("VOICE_INPUT_DEVICE"))
    parser.add_argument("--sample-rate", type=int, default=None)
    parser.add_argument("--save-dir", type=Path, default=None, help="Keep recorded wav files in this directory.")
    parser.add_argument("--allow-download", action="store_true", help="Allow faster-whisper to download a missing model.")
    parser.add_argument("--list-devices", action="store_true", help="Print sounddevice devices and exit.")
    parser.add_argument("--check", action="store_true", help="Load the model and print the selected backend, then exit.")
    parser.add_argument("--toggle", action="store_true", help="Toggle background recording; stop transcribes and inserts text.")
    parser.add_argument("--watch", action="store_true", help="Watch global hotkey activity in this terminal.")
    parser.add_argument("--terminal", action="store_true", help="Use terminal-only Ctrl+B recording mode.")
    parser.add_argument("--status", action="store_true", help="Print whether background recording is active.")
    parser.add_argument(
        "--install-hotkey",
        action="store_true",
        help="Install desktop shortcuts (auto-detects Hyprland and GNOME).",
    )
    parser.add_argument(
        "--install-hotkeys",
        action="store_true",
        help="Install desktop shortcuts (auto-detects Hyprland and GNOME).",
    )
    parser.add_argument(
        "--print-hyprland",
        action="store_true",
        help="Print Hyprland keybind configuration block and exit.",
    )
    parser.add_argument(
        "--install-hyprland",
        action="store_true",
        help="Install Hyprland keybinds to ~/.config/hypr/custom/keybinds.lua and reload.",
    )
    parser.add_argument("--record-background", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--speak-selection", action="store_true", help="Speak selected text, falling back to clipboard text.")
    parser.add_argument("--speak", metavar="TEXT", help="Speak the provided text using TTS.")
    parser.add_argument("--stop-tts", action="store_true", help="Stop active TTS playback.")
    parser.add_argument("--tts-check", action="store_true", help="Print TTS voice, speed, and dependency status.")
    parser.add_argument("--list-tts-voices", action="store_true", help="List available Kokoro voice IDs.")
    parser.add_argument(
        "--tts-backend",
        choices=("kokoro", "edge"),
        default=os.getenv("VOICE_TTS_BACKEND", DEFAULT_TTS_BACKEND),
        help="TTS backend. Default: kokoro.",
    )
    parser.add_argument(
        "--tts-voice",
        default=os.getenv("VOICE_TTS_VOICE"),
        help=f"TTS voice ID. Kokoro default: {DEFAULT_KOKORO_VOICE}; secondary: {SECONDARY_KOKORO_VOICE}.",
    )
    parser.add_argument(
        "--download-tts-assets",
        action="store_true",
        help="Download and verify Kokoro ONNX model and voice weights into models/kokoro/.",
    )
    parser.add_argument(
        "--tts-speed",
        type=float,
        default=float(os.getenv("VOICE_TTS_SPEED", str(tts_defaults.speed))),
        help="TTS speed multiplier. Default: 1.2.",
    )
    parser.add_argument("--tts-background", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--tts-text-file", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--kokoro-model",
        type=Path,
        default=Path(os.getenv("VOICE_KOKORO_MODEL", str(default_kokoro_model_path()))),
        help="Kokoro ONNX model path.",
    )
    parser.add_argument(
        "--kokoro-voices",
        type=Path,
        default=Path(os.getenv("VOICE_KOKORO_VOICES", str(default_kokoro_voices_path()))),
        help="Kokoro voices file path.",
    )
    parser.add_argument("--kokoro-lang", default=os.getenv("VOICE_KOKORO_LANG", DEFAULT_KOKORO_LANG), help="Kokoro language code.")
    parser.add_argument(
        "--kokoro-trim",
        dest="kokoro_trim",
        action="store_true",
        default=env_bool("VOICE_KOKORO_TRIM", False),
        help="Trim leading/trailing silence in Kokoro chunks.",
    )
    parser.add_argument(
        "--kokoro-no-trim",
        dest="kokoro_trim",
        action="store_false",
        help="Keep Kokoro chunk boundaries untrimmed. Default.",
    )
    parser.add_argument(
        "--output-method",
        choices=("type", "paste", "terminal-paste", "clipboard"),
        default=os.getenv("VOICE_OUTPUT_METHOD", "type"),
        help="How background mode inserts the transcript. Default: type.",
    )
    parser.add_argument(
        "--type-delay",
        type=int,
        default=int(os.getenv("VOICE_TYPE_DELAY", "2")),
        help="Milliseconds between synthetic keystrokes for --output-method type.",
    )
    parser.add_argument(
        "--wayland-backend",
        choices=("auto", "wtype", "ydotool"),
        default=os.getenv("VOICE_WAYLAND_BACKEND", "auto"),
        help="Wayland typing backend: auto, wtype, or ydotool. Default: auto.",
    )
    parser.add_argument(
        "--pre-type-delay",
        type=int,
        default=int(os.getenv("VOICE_PRE_TYPE_DELAY", "50")),
        help="Milliseconds to wait before keystroke injection starts. Default: 50.",
    )
    parser.add_argument(
        "--keep-newlines",
        dest="keep_newlines",
        action="store_true",
        default=env_bool("VOICE_KEEP_NEWLINES", False),
        help="Preserve literal newlines in typed transcripts.",
    )
    parser.add_argument(
        "--no-keep-newlines",
        dest="keep_newlines",
        action="store_false",
        help="Replace internal newlines with spaces before typing. Default.",
    )
    parser.add_argument("--paste", dest="paste", action="store_true", default=True, help="Insert transcript into the focused app.")
    parser.add_argument("--no-paste", dest="paste", action="store_false", help="Do not insert after background transcription.")
    parser.add_argument("--notify", dest="notify", action="store_true", default=True, help="Show desktop notifications.")
    parser.add_argument("--no-notify", dest="notify", action="store_false", help="Disable desktop notifications.")
    parser.add_argument("--beep", dest="beep", action="store_true", default=env_bool("VOICE_BEEP", True), help="Play audible recording cues.")
    parser.add_argument("--no-beep", dest="beep", action="store_false", help="Disable audible recording cues.")
    parser.add_argument(
        "--recording-beep-interval",
        type=float,
        default=float(os.getenv("VOICE_RECORDING_BEEP_INTERVAL", "5")),
        help="Seconds between reminder cues while recording; 0 disables reminders.",
    )
    parser.add_argument(
        "--beep-volume",
        type=float,
        default=float(os.getenv("VOICEMODE_CUE_VOLUME", os.getenv("VOICE_BEEP_VOLUME", "0.08"))),
        help="Cue volume from 0.0 to 1.0.",
    )
    parser.add_argument("--beep-output-device", default=os.getenv("VOICE_BEEP_OUTPUT_DEVICE"), help="Output device for cues.")
    parser.add_argument("--test-beep", action="store_true", help="Play start, reminder, and stop cues, then exit.")
    args = parser.parse_args()
    args.type_delay = max(0, args.type_delay)
    args.pre_type_delay = max(0, args.pre_type_delay)
    if not args.tts_voice:
        args.tts_voice = DEFAULT_KOKORO_VOICE if args.tts_backend == "kokoro" else tts_defaults.voice
    return args


def main() -> int:
    args = parse_args()

    if args.download_tts_assets:
        return download_tts_assets(args)
    if args.list_tts_voices:
        return print_tts_voices(args)
    if args.tts_check:
        return print_tts_check(args)
    if args.tts_background:
        return run_tts_background(args)
    if args.stop_tts:
        return 0 if stop_tts(args) else 1
    if args.speak_selection:
        return speak_selection(args)
    if args.speak is not None:
        speak_text = sys.stdin.read() if args.speak == "-" else args.speak
        return start_tts_background(speak_text, args, source="stdin" if args.speak == "-" else "text")
    if args.test_beep:
        play_cue(args, "start")
        time.sleep(0.4)
        play_cue(args, "recording")
        time.sleep(0.4)
        play_cue(args, "stop")
        return 0
    if args.list_devices:
        print(sd.query_devices())
        return 0
    if args.print_hyprland:
        return print_hyprland_keybinds()
    if args.install_hyprland:
        return install_hyprland_keybinds()
    if args.install_hotkey or args.install_hotkeys:
        return install_hotkeys_dispatch()
    if args.status:
        return print_status()
    if args.toggle:
        return toggle_background_recording(args)

    args.language = args.language.strip() or None

    if args.record_background:
        return run_background_recording(args)

    if args.check:
        load_model(args)
        return 0
    if args.terminal:
        return run_terminal_mode(args)
    return watch_log(args)


if __name__ == "__main__":
    raise SystemExit(main())
