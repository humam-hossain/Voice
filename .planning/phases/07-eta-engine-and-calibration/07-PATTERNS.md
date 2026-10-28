# Phase 07: ETA Engine & Calibration - Pattern Map

**Mapped:** 2026-10-29  
**Files analyzed:** 5 (2 modified, 3 created)  
**Analogs found:** 5 / 5 (100% exact analog coverage)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `voicemode_telemetry.py` | service / model / utility | file-I/O / transform / batch | `voicemode_telemetry.py` | exact (in-file extension of Phase 7 calibration stubs) |
| `voice.py` | controller / middleware | streaming / event-driven / request-response | `voice.py` | exact (in-file integration into worker lifecycle & generator) |
| `tests/test_eta_engine.py` | test | transform / batch / file-I/O | `tests/test_telemetry.py` | exact (hermetic ledger & accumulator estimation tests) |
| `tests/test_midrun_eta.py` | test | streaming / event-driven | `tests/test_timing.py` | exact (generator-driven segment yields & status contract) |
| `tests/test_eta_cli.py` | test | request-response / file-I/O | `tests/test_status_contract.py` | exact (CLI stdout capture, JSON assertions, kill switches) |

---

## Pattern Assignments

### `voicemode_telemetry.py` (service / model / utility, file-I/O / transform / batch)

**Analog:** `voicemode_telemetry.py`  
**Purpose:** Pure latency estimation math, multi-tier hierarchy resolution (L0 $\to$ L3), ratio-of-sums accumulator maintenance, MAD confidence calculation, outlier exclusion filtering, and atomic `calibration.json` caching.

#### Imports Pattern
From [voicemode_telemetry.py:1-14](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L1-L14):
```python
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
```
*Note: Phase 7 adds `import statistics` for `statistics.median` in MAD calculations.*

#### Core Pattern: Atomic Persistence & Accumulator Storage
From [voicemode_telemetry.py:337-362](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L337-L362) and [voicemode_telemetry.py:703-722](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L703-L722):
```python
def load_calibration() -> dict:
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
```

#### Core Pattern: Calibration Key Extraction & Multi-Level Hierarchy
From [voicemode_telemetry.py:186-192](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L186-L192) extended to 4 tiers (D7-24):
```python
def extract_hierarchy_keys(config: dict, backend: str) -> dict[str, str]:
    """Extracts 4-tier hierarchy keys: L0 (8 fields) -> L1 (6 fields) -> L2 (4 fields) -> L3 (prior model)."""
    cfg = config or {}
    model = cfg.get("model") or "medium"
    device = cfg.get("device") or "cpu"
    compute_type = cfg.get("compute_type") or "int8"
    beam = cfg.get("beam_size", 1)
    vad = int(bool(cfg.get("vad_filter", True)))
    lang = cfg.get("language") or "auto"
    chunk = cfg.get("chunk_s", 180.0)
    prefix = str(model).lower().split(".")[0].split("-")[0]

    return {
        "L0": f"{model}|{device}|{compute_type}|{backend}|beam={beam}|vad={vad}|lang={lang}|chunk={chunk}",
        "L1": f"{model}|{device}|{compute_type}|{backend}|beam={beam}|lang={lang}",
        "L2": f"{model}|{device}|{compute_type}|{backend}",
        "L3": f"prior:{prefix}",
    }
```

#### Core Pattern: Shrinkage Blending & Ratio of Sums (D7-25, D7-26, D7-27)
From [voicemode_telemetry.py:778-803](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L778-L803):
```python
def resolve_calibrated_rate(keys: dict[str, str], accumulators: dict, prior_rtf: float) -> tuple[float, str, int]:
    """Resolves rate using hierarchy fallback with James-Stein shrinkage blending."""
    # L2 level
    l2_key = keys["L2"]
    l2_acc = accumulators.get(l2_key, {})
    l2_n = l2_acc.get("n", 0)
    if l2_n >= 3:
        raw_l2 = l2_acc["sum_decode_s"] / l2_acc["sum_audio_s"]
        w2 = min(1.0, l2_n / 10.0)
        rate_l2 = w2 * raw_l2 + (1.0 - w2) * prior_rtf
    else:
        rate_l2 = prior_rtf

    # L1 level
    l1_key = keys["L1"]
    l1_acc = accumulators.get(l1_key, {})
    l1_n = l1_acc.get("n", 0)
    if l1_n >= 3:
        raw_l1 = l1_acc["sum_decode_s"] / l1_acc["sum_audio_s"]
        w1 = min(1.0, l1_n / 10.0)
        rate_l1 = w1 * raw_l1 + (1.0 - w1) * rate_l2
    else:
        rate_l1 = rate_l2

    # L0 level
    l0_key = keys["L0"]
    l0_acc = accumulators.get(l0_key, {})
    l0_n = l0_acc.get("n", 0)
    if l0_n >= 3:
        raw_l0 = l0_acc["sum_decode_s"] / l0_acc["sum_audio_s"]
        w0 = min(1.0, l0_n / 10.0)
        rate_l0 = w0 * raw_l0 + (1.0 - w0) * rate_l1
        return rate_l0, "L0", l0_n
    elif l1_n >= 3:
        return rate_l1, "L1", l1_n
    elif l2_n >= 3:
        return rate_l2, "L2", l2_n
    else:
        return prior_rtf, "L3", 0
```

#### Core Pattern: MAD Confidence Calculation (D7-28)
```python
def compute_mad_confidence(residuals: list[float]) -> float:
    """Computes confidence score: 1.0 - MAD / median_residual clamped [0.0, 1.0]."""
    if len(residuals) < 3:
        return 0.0
    med = statistics.median(residuals)
    if med <= 0.0:
        return 1.0
    deviations = [abs(r - med) for r in residuals]
    mad = statistics.median(deviations)
    ratio = mad / med
    return round(max(0.0, min(1.0, 1.0 - ratio)), 3)
```

#### Error Handling & Exclusion Pattern (D7-08, D7-31)
From [voicemode_telemetry.py:724-738](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L724-L738) and [voicemode_telemetry.py:856-879](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L856-L879):
```python
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
        decode_ms = actual.get("decode_ms")
        audio_s = record.get("audio_s")
        if decode_ms is not None and audio_s and float(audio_s) > 0:
            rate = (float(decode_ms) / 1000.0) / float(audio_s)
            if rate < 0.01 or rate > 10.0:
                return True
    except Exception:
        pass
    return False
```

#### Validation & Status Contract Pattern
From [voicemode_telemetry.py:519-523](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L519-L523) and [voicemode_telemetry.py:619-648](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L619-L648):
```python
# Extended with Phase 7 keys: revision_count, last_revised_at, key_level, key_n
STATUS_V1_KEYS = [
    "schema", "pid", "run_id", "state", "phase", "started_at", "updated_at",
    "expires_at", "audio_s", "segments", "segments_done", "eta_epoch",
    "eta_remaining_s", "eta_confidence", "eta_source", "overrun", "report_path",
    "revision_count", "last_revised_at", "key_level", "key_n"
]
```

---

### `voice.py` (controller / middleware, streaming / event-driven / request-response)

**Analog:** `voice.py`  
**Purpose:** Worker lifecycle coordination, initial ETA publication (<100 ms), Whisper generator segment consumption with mid-run rate blending, hysteresis filtering, countdown overrun pacing (`1s` dwell $\to$ `Finishing…`), post-paste calibration cache updating, and CLI flag dispatch (`--reset-calibration`, `--status --json`).

#### Imports Pattern
From [voice.py:9-42](file:///home/pera/github_repo/Voice/voice.py#L9-L42):
```python
from __future__ import annotations

import argparse
import ast
import json
import math
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import voicemode_telemetry
```

#### Core Pattern: Segment Yield Loop & Mid-Run Revision Hysteresis
From [voice.py:722-728](file:///home/pera/github_repo/Voice/voice.py#L722-L728) and [voice.py:2248-2299](file:///home/pera/github_repo/Voice/voice.py#L2248-L2299):
```python
# Consuming Whisper generator with mid-run recalculation
decoded_audio_s = 0.0
raw_segments, info = model_state.model.transcribe(str(wav_path), **kwargs)
for seg in raw_segments:
    segments.append(seg)
    seg_dur = max(0.0, float(getattr(seg, "end", 0.0) - getattr(seg, "start", 0.0)))
    decoded_audio_s += seg_dur
    
    # Recalculate remaining ETA if audio progress is observed (D7-13, D7-14)
    if on_segment_yield:
        on_segment_yield(decoded_audio_s, total_audio_s)
```

Hysteresis logic (D7-09, D7-10, D7-11):
```python
def update_midrun_eta(new_raw_eta: float, current_eta: float, last_revised_at: float, now: float) -> tuple[float, bool]:
    new_int = int(math.ceil(new_raw_eta))
    curr_int = int(math.ceil(current_eta)) if current_eta is not None else new_int
    
    # Downward revision: strictly monotone non-increasing, step immediately
    if new_int < curr_int:
        return float(new_int), True
        
    # Upward revision: requires jump >= 1.0s AND elapsed >= 2.0s
    if (new_raw_eta - current_eta) >= 1.0 and (now - last_revised_at) >= 2.0:
        return float(new_int), True
        
    # Suppress upward jitter; continue existing countdown
    return current_eta, False
```

#### Core Pattern: Overrun Dwell & Pacing (D7-12, D7-16)
```python
# Pacing: 2s -> 1s -> dwell 1 full second -> Finishing...
if remaining_s <= 1.0:
    if dwell_start is None:
        dwell_start = time.monotonic()
        remaining_s = 1.0
        overrun = False
    elif (time.monotonic() - dwell_start) < 1.0:
        remaining_s = 1.0
        overrun = False
    else:
        remaining_s = 0.0
        overrun = True
```

#### Core Pattern: Worker Finalization Post-Paste Cache Update (D7-04)
From [voice.py:1215-1218](file:///home/pera/github_repo/Voice/voice.py#L1215-L1218):
```python
# Append ledger record first
voicemode_telemetry.append_ledger_row(record)
row_written = True

# Update calibration cache incrementally in background finalization (post-paste)
try:
    voicemode_telemetry.update_calibration_from_run(record)
except Exception as cal_exc:
    print(f"Error updating calibration cache: {cal_exc}", file=sys.stderr, flush=True)
```

#### CLI Dispatch Pattern (`--reset-calibration` & `--status --json`)
From [voice.py:2615-2640](file:///home/pera/github_repo/Voice/voice.py#L2615-L2640) and [voice.py:3829-3837](file:///home/pera/github_repo/Voice/voice.py#L3829-L3837):
```python
# In main() dispatch
if getattr(args, "reset_calibration", False):
    ok = voicemode_telemetry.reset_calibration()
    print("Calibration reset to priors." if ok else "Failed to reset calibration.")
    return 0 if ok else 1

if args.status:
    return print_status(args)
```
In `print_status()` JSON payload:
```python
out = {
    "state": st.get("state"),
    "phase": st.get("phase"),
    "eta_remaining_s": st.get("eta_remaining_s"),
    "eta_epoch": st.get("eta_epoch"),
    "eta_source": st.get("eta_source"),
    "eta_confidence": st.get("eta_confidence"),
    "audio_s": st.get("audio_s"),
    "segments": st.get("segments"),
    "segments_done": st.get("segments_done"),
    "pid": st.get("pid") or pid,
    "run_id": st.get("run_id"),
    "overrun": st.get("overrun"),
    "revision_count": st.get("revision_count", 0),
    "last_revised_at": st.get("last_revised_at"),
    "key_level": st.get("key_level"),
    "key_n": st.get("key_n"),
}
```

---

### `tests/test_eta_engine.py` (test, transform / batch / file-I/O)

**Analog:** `tests/test_telemetry.py`  
**Purpose:** Unit tests for ETA-01, ETA-02, ETA-03, ETA-08 (ratio of sums, 4-tier hierarchy, shrinkage blending, MAD confidence calculation, dynamic load subtraction, outlier and cold exclusion gating).

#### Imports Pattern
From [tests/test_telemetry.py:1-12](file:///home/pera/github_repo/Voice/tests/test_telemetry.py#L1-L12):
```python
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase, advancing_monotonic
```

#### Core Pattern: Synthetic Ledger & Ratio-of-Sums Test
From [tests/test_telemetry.py:14-33](file:///home/pera/github_repo/Voice/tests/test_telemetry.py#L14-L33):
```python
class TestETAEngine(TempXdgTestCase):
    def test_ratio_of_sums_formula(self) -> None:
        """ETA-01: Verify rate is sum(decode_s) / sum(audio_s), NOT mean of ratios."""
        cal = {}
        # Run 1: Short audio (0.8s), decode=1.2s -> RTF=1.5
        rec1 = {"audio_s": 0.8, "actual": {"decode_ms": 1200.0, "load_ms": 1200.0}, "outcome": "success"}
        # Run 2: Long audio (20.0s), decode=10.0s -> RTF=0.5
        rec2 = {"audio_s": 20.0, "actual": {"decode_ms": 10000.0, "load_ms": 1200.0}, "outcome": "success"}
        
        voicemode_telemetry.update_calibration_from_run(rec1, cal_data=cal)
        voicemode_telemetry.update_calibration_from_run(rec2, cal_data=cal)
        
        # Mean of ratios would be (1.5 + 0.5) / 2 = 1.0
        # Ratio of sums is (1.2 + 10.0) / (0.8 + 20.0) = 11.2 / 20.8 = 0.5385
        key = voicemode_telemetry.calibration_key("cpu, int8", {})
        entry = cal["accumulators"]["L2"][key]
        expected_rate = (1.2 + 10.0) / (0.8 + 20.0)
        actual_rate = entry["sum_decode_s"] / entry["sum_audio_s"]
        self.assertAlmostEqual(actual_rate, expected_rate, places=4)
```

#### Core Pattern: 4-Tier Hierarchy Fallback & Shrinkage Test (ETA-02)
```python
class TestKeyHierarchy(TempXdgTestCase):
    def test_hierarchy_levels_and_shrinkage(self) -> None:
        """ETA-02: Test L0 -> L1 -> L2 -> L3 resolution with n >= 3 floor and James-Stein shrinkage."""
        # Unseen config falls back to L3 prior
        config = {"model": "turbo", "device": "cuda", "compute_type": "float16", "beam_size": 1, "language": "en"}
        eta, src, level, n, conf = voicemode_telemetry.calibrated_eta_seconds(10.0, config=config, backend="cuda, float16")
        self.assertEqual(level, "L3")
        self.assertEqual(src, "prior")
        self.assertEqual(n, 0)
```

#### Core Pattern: Exclusion Gating & MAD Confidence Test (ETA-03)
```python
class TestCalibrationExclusions(TempXdgTestCase):
    def test_outlier_cold_and_failure_exclusion(self) -> None:
        """ETA-03: Failures, cold boots, and pathological outliers excluded from calibration accumulators."""
        cal = {}
        # Cold run
        cold_rec = {"audio_s": 5.0, "actual": {"decode_ms": 2500.0}, "outcome": "success", "predicted": {"source": "cold"}}
        self.assertTrue(voicemode_telemetry._is_calibration_excluded(cold_rec))
        
        # Failed run
        err_rec = {"audio_s": 5.0, "actual": {"decode_ms": 2500.0}, "outcome": "error"}
        self.assertTrue(voicemode_telemetry._is_calibration_excluded(err_rec))
        
        # Outlier rate (>10.0)
        outlier_rec = {"audio_s": 1.0, "actual": {"decode_ms": 15000.0}, "outcome": "success"}
        self.assertTrue(voicemode_telemetry._is_calibration_excluded(outlier_rec))
```

---

### `tests/test_midrun_eta.py` (test, streaming / event-driven)

**Analog:** `tests/test_timing.py` (and `tests/test_incremental_transcription.py`)  
**Purpose:** Integration tests for ETA-04, ETA-05, ETA-06, ETA-07 (generator segment yields, downward step monotonicity, upward revision debounce, 1s dwell overrun to `Finishing…`, ETA visibility lifecycle, and `~` prefix rules).

#### Imports Pattern
From [tests/test_timing.py:1-11](file:///home/pera/github_repo/Voice/tests/test_timing.py#L1-L11):
```python
from __future__ import annotations

import argparse
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase, advancing_monotonic
```

#### Core Pattern: Whisper Segment Generator Mocking
From [tests/test_timing.py:13-43](file:///home/pera/github_repo/Voice/tests/test_timing.py#L13-L43):
```python
class DummySegment:
    def __init__(self, start: float, end: float, text: str = "test"):
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = -0.2
        self.compression_ratio = 1.0
        self.no_speech_prob = 0.01
        self.temperature = 0.0


class DummyInfo:
    def __init__(self, duration: float, duration_after_vad: float):
        self.duration = duration
        self.duration_after_vad = duration_after_vad
```

#### Core Pattern: Mid-Run Hysteresis Verification (ETA-04)
```python
class TestMidRunRevisions(TempXdgTestCase):
    def test_downward_immediate_upward_damped(self) -> None:
        """ETA-04: Downward steps step down immediately; upward jumps require >= 1.0s and >= 2.0s elapsed."""
        now = 1000.0
        last_revised = 1000.0
        curr_eta = 8.0
        
        # Downward: 8.0 -> 5.2 steps immediately to 6.0 (or 5.0)
        new_eta, revised = voice.update_midrun_eta(5.2, curr_eta, last_revised, now + 0.5)
        self.assertTrue(revised)
        self.assertEqual(new_eta, 6.0)
        
        # Upward jitter under 2.0s: 6.0 -> 7.5 within 0.8s -> suppressed
        curr_eta = 6.0
        new_eta, revised = voice.update_midrun_eta(7.5, curr_eta, last_revised, now + 0.8)
        self.assertFalse(revised)
        self.assertEqual(new_eta, curr_eta)
        
        # Upward jump after >= 2.0s with delta >= 1.0s -> permitted
        new_eta, revised = voice.update_midrun_eta(7.5, curr_eta, last_revised, now + 2.5)
        self.assertTrue(revised)
        self.assertEqual(new_eta, 8.0)
```

#### Core Pattern: Overrun Dwell at 1s & Transition to `Finishing…` (ETA-05)
```python
class TestOverrunBehavior(TempXdgTestCase):
    def test_1s_dwell_and_finishing_transition(self) -> None:
        """ETA-05: Countdown holds at 1s for 1 full second before emitting overrun: true."""
        t0 = time.monotonic()
        # Simulated tick loop
        state = voice.calculate_countdown_display(remaining_raw=0.8, dwell_t0=t0, now=t0 + 0.4)
        self.assertEqual(state["display_s"], 1)
        self.assertFalse(state["overrun"])
        
        # After 1.2s elapsed
        state_overrun = voice.calculate_countdown_display(remaining_raw=0.2, dwell_t0=t0, now=t0 + 1.2)
        self.assertEqual(state_overrun["display_s"], 0)
        self.assertTrue(state_overrun["overrun"])
        self.assertEqual(state_overrun["label"], "Finishing…")
```

---

### `tests/test_eta_cli.py` (test, request-response / file-I/O)

**Analog:** `tests/test_status_contract.py`  
**Purpose:** Testing CLI `--status --json` output schema, `--reset-calibration` reset epoch, `VOICE_ETA=off` kill switch, and `.boot_session` tmpfs cold detection.

#### Imports Pattern
From [tests/test_status_contract.py:1-12](file:///home/pera/github_repo/Voice/tests/test_status_contract.py#L1-L12):
```python
from __future__ import annotations

import json
import os
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import voice
import voicemode_telemetry
from _hermetic import TempXdgTestCase
```

#### Core Pattern: CLI Stdout Capture & JSON Inspection (ETA-09)
From [tests/test_status_contract.py:318-327](file:///home/pera/github_repo/Voice/tests/test_status_contract.py#L318-L327):
```python
class TestETACLI(TempXdgTestCase):
    def test_status_json_eta_fields(self) -> None:
        """ETA-09: --status --json exposes revision_count, last_revised_at, key_level, key_n."""
        voicemode_telemetry.publish_status(voicemode_telemetry.build_status(
            pid=123, run_id="r1", state="transcribing", phase="decode",
            started_at=100.0, eta_remaining_s=4.0, eta_source="calibrated",
            eta_confidence="high", overrun=False
        ))
        
        args = voice.parse_args(["--status", "--json"])
        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            with patch("voice.process_alive", return_value=True), \
                 patch("voice.read_pid", return_value=123):
                voice.print_status(args)
        finally:
            sys.stdout = old
            
        payload = json.loads(f.getvalue().strip())
        self.assertEqual(payload["state"], "transcribing")
        self.assertEqual(payload["eta_remaining_s"], 4.0)
        self.assertEqual(payload["eta_source"], "calibrated")
        self.assertIn("revision_count", payload)
        self.assertIn("key_level", payload)
```

#### Core Pattern: `--reset-calibration` & Ledger Rebuild Guard (D7-03)
```python
    def test_reset_calibration_creates_epoch(self) -> None:
        """D7-03: --reset-calibration deletes cache and establishes a reset epoch."""
        cal_path = voicemode_telemetry.get_calibration_path()
        voicemode_telemetry.save_calibration({"accumulators": {}})
        self.assertTrue(cal_path.exists())
        
        args = voice.parse_args(["--reset-calibration"])
        with patch("sys.stdout", new=StringIO()) as fake_out:
            code = voice.main(["--reset-calibration"])
            self.assertEqual(code, 0)
            self.assertIn("Calibration reset", fake_out.getvalue())
            
        # Verify reset timestamp persists so old ledger rows are ignored
        self.assertFalse(cal_path.exists())
        reset_epoch = voicemode_telemetry.get_calibration_reset_timestamp()
        self.assertIsNotNone(reset_epoch)
```

#### Core Pattern: Environment Kill Switch `VOICE_ETA=off` (ETA-09)
From [tests/test_status_contract.py:339-345](file:///home/pera/github_repo/Voice/tests/test_status_contract.py#L339-L345):
```python
    def test_voice_eta_kill_switch(self) -> None:
        """ETA-09: VOICE_ETA=off cleanly suppresses ETA calculation."""
        with patch.dict(os.environ, {"VOICE_ETA": "off"}):
            eta, src, lvl, n, conf = voicemode_telemetry.calibrated_eta_seconds(10.0)
            self.assertIsNone(eta)
            self.assertIsNone(src)
```

---

## Shared Patterns

### 1. Atomic JSON Persistence
**Source:** [voicemode_telemetry.py:337-362](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L337-L362)  
**Apply to:** All writes to `calibration.json`, `status.json`, and `.calibration_reset`.  
**Mechanism:** `tempfile.mkstemp(dir=target.parent)` $\to$ `os.write` $\to$ `os.fsync` $\to$ `os.chmod(0o600)` $\to$ `os.replace`. Never write directly to destination; ensures zero corrupted/partial reads by concurrent processes.

### 2. Hermetic Test Environment
**Source:** [tests/_hermetic.py:19-54](file:///home/pera/github_repo/Voice/tests/_hermetic.py#L19-L54)  
**Apply to:** Every new test class in `test_eta_engine.py`, `test_midrun_eta.py`, and `test_eta_cli.py`.  
**Mechanism:** Inherit from `TempXdgTestCase`. Re-routes `XDG_RUNTIME_DIR` and `XDG_STATE_HOME` to ephemeral temporary directories. Never touches real user state in `~/.local/state/voicemode/` or `/run/user/1000/voice-stt/`.

### 3. Fail-Open Error Suppression & Defensive Fallback
**Source:** [voicemode_telemetry.py:536-544](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L536-L544), [voice.py:2154-2168](file:///home/pera/github_repo/Voice/voice.py#L2154-L2168)  
**Apply to:** All status reporting, calibration cache lookups, and mid-run corrections.  
**Mechanism:** Every telemetry read/write and estimation step is wrapped in `try/except Exception`. On any file corruption, permission error, or invalid payload, instantly fall back to shipped priors (`PRIOR_RTF`) without crashing worker processes or blocking audio recording.

### 4. Zero-Overhead Lifecycle Markers
**Source:** [07-RESEARCH.md:367-379](file:///home/pera/github_repo/Voice/.planning/phases/07-eta-engine-and-calibration/07-RESEARCH.md#L367-L379)  
**Apply to:** Boot session cold detection (`$XDG_RUNTIME_DIR/voice-stt/.boot_session`).  
**Mechanism:** `Path.touch(mode=0o600)`. Relies on Linux `tmpfs` clearing automatically across reboots; zero subprocess spawns, zero external queries.

---

## No Analog Found

None. All 5 files have exact in-repo analogs. Every core architectural component (atomic file I/O, status schema, CLI dispatch, hermetic test fixtures, generator consumption) directly mirrors existing patterns in `voicemode_telemetry.py`, `voice.py`, and the `tests/` directory.

---

## Metadata

**Analog search scope:**
- `voicemode_telemetry.py` (telemetry schemas, status contract, calibration stubs)
- `voice.py` (worker process lifecycle, Whisper decode loop, status publishing, CLI)
- `tests/test_telemetry.py` (ledger row serialization, validation, atomic writes)
- `tests/test_status_contract.py` (status fields, expiry, CLI status formatting, kill switch)
- `tests/test_timing.py` (generator timing, DummySegment, decode metrics)
- `tests/test_incremental_transcription.py` (incremental decode queue, stage transitions)
- `tests/_hermetic.py` (hermetic test harness, advancing monotonic clock)

**Files scanned:** 7  
**Pattern extraction date:** 2026-10-29
