# Phase 08: Accuracy Report & Click-Through - Pattern Map

**Mapped:** 2026-10-30  
**Files analyzed:** 3 (1 modified, 2 created)  
**Analogs found:** 3 / 3 (100% exact analog coverage)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `voicemode_report.py` | service / reporter / renderer / utility | file-I/O / transform / batch / formatting | `voicemode_telemetry.py` | exact (stdlib-only architecture, atomic file I/O, metrics aggregation) |
| `voice.py` | controller / CLI dispatcher / worker lifecycle | request-response / lifecycle hook | `voice.py` | exact (in-file CLI dispatch & worker finalization lifecycle) |
| `tests/test_report.py` | test | unit / integration / CLI / file-I/O | `tests/test_eta_cli.py`, `tests/test_telemetry.py` | exact (hermetic test harness, synthetic records, CLI capture) |

---

## Pattern Assignments

### `voicemode_report.py` (service / reporter / renderer / utility, file-I/O / transform / batch / formatting)

**Analog:** `voicemode_telemetry.py` (for data structures, stdlib-only constraints, file operations, error suppression) + inline string formatters.  
**Purpose:** Pure reporting logic, ledger ingestion with corrupt line tracking, multi-criteria filtering (`--since`, `--last`, `--model`, `--device`), statistical aggregation (median error %, p90 latency, residuals, stage breakdowns), 4 fluid responsive inline SVG charts (`viewBox`), zero-JavaScript dark HTML dashboard with visual onboarding empty state and 4-subpanel privacy footer, canonical 17-column CSV export, converged JSON contract, atomic worker pre-rendering hook (`report.html`), and secure `xdg-open` browser launching.

#### Imports Pattern (Strict Stdlib + Telemetry Only, FND-01 / RPT-01 Compliance)
Modeled on [voicemode_telemetry.py:1-14](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L1-L14):
```python
from __future__ import annotations

import argparse
import csv
import datetime
import html
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any, Optional

import voicemode_telemetry
```
*Note: Under no circumstances may `faster_whisper`, `numpy`, or `sounddevice` be imported at module or function level in `voicemode_report.py`.*

#### Core Pattern: Atomic Pre-Render Persistence
From [voicemode_telemetry.py:362-386](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L362-L386):
```python
def generate_prerendered_report(dest_path: Optional[Path] = None) -> Path:
    """Pre-renders report.html for the last 200 runs and atomically writes to disk (D-18, D-19)."""
    if dest_path is None:
        dest_path = voicemode_telemetry.get_state_dir() / "report.html"

    # Always unfiltered last 200 runs for the cache (D-17)
    records, skipped_count = load_ledger_records(max_records=200)
    metrics = compute_report_metrics(records)
    html_content = render_html_report(
        records=records,
        metrics=metrics,
        skipped_count=skipped_count,
        metrics_path=voicemode_telemetry.get_ledger_path(),
    )

    voicemode_telemetry.atomic_write_text(dest_path, html_content, mode=0o600)
    return dest_path
```

#### Core Pattern: Corrupt Line Tracking & Tolerant Ledger Ingestion (D-21)
Adapted from [voicemode_telemetry.py:320-333](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L320-L333):
```python
def load_ledger_records(paths: Optional[list[Path]] = None, max_records: Optional[int] = None) -> tuple[list[dict], int]:
    """Loads ledger records, resilient to torn/corrupt lines, tracking skip count (D-21)."""
    metrics_dir = voicemode_telemetry.get_metrics_dir()
    all_paths: list[Path] = []
    if paths is not None:
        all_paths = list(paths)
    else:
        main = voicemode_telemetry.get_ledger_path()
        if main.exists():
            all_paths.append(main)
        try:
            for p in sorted(metrics_dir.glob("metrics-*.jsonl")):
                all_paths.append(p)
        except Exception:
            pass

    records: list[dict] = []
    skipped_count = 0

    for p in all_paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict) and obj.get("schema") == 1:
                            records.append(obj)
                        else:
                            skipped_count += 1
                    except Exception:
                        skipped_count += 1
        except Exception:
            continue

    if max_records is not None and len(records) > max_records:
        records = records[-max_records:]

    return records, skipped_count
```

#### Core Pattern: Multi-Criteria Filtering (D-14, D-16)
```python
def filter_records(
    records: list[dict],
    since: Optional[str] = None,
    last: Optional[int | str] = 200,
    model: Optional[str] = None,
    device: Optional[str] = None,
) -> list[dict]:
    """Filters records by time window, limit count, and model/device attributes (D-14, D-16)."""
    filtered = list(records)

    # Filter by model
    if model:
        m_lower = model.lower()
        filtered = [r for r in filtered if str(r.get("config", {}).get("model", "")).lower() == m_lower]

    # Filter by device
    if device:
        d_lower = device.lower()
        filtered = [r for r in filtered if str(r.get("config", {}).get("device", "")).lower() == d_lower]

    # Filter by since (ISO date or relative interval like 24h, 7d, 30d)
    if since:
        since_ts = parse_since_argument(since)
        if since_ts is not None:
            filtered = [r for r in filtered if (r.get("ts_start") or r.get("ts_end") or 0.0) >= since_ts]

    # Filter by last count (integer or "all")
    if last is not None and str(last).lower() != "all":
        try:
            limit = int(last)
            if limit > 0:
                filtered = filtered[-limit:]
        except ValueError:
            pass

    return filtered
```

#### Core Pattern: Canonical 17-Column CSV Export (D-11, RPT-05)
```python
CSV_HEADERS = [
    "run_id", "timestamp", "model", "device", "audio_s", "predicted_s",
    "actual_s", "error_s", "error_pct", "load_s", "record_s", "decode_s",
    "finalize_s", "insert_s", "outcome", "eta_source", "confidence",
]

def render_csv(records: list[dict]) -> str:
    """Exports records to CSV with exact 17 canonical headers (D-11, RPT-05)."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, lineterminator="\n")
    writer.writeheader()
    for rec in records:
        writer.writerow(record_to_csv_row(rec))
    return output.getvalue()
```

#### Core Pattern: Converged JSON Schema (D-12, RPT-05)
```python
def render_json(metrics: dict, ledger_info: dict) -> str:
    """Converged JSON schema contract for --metrics --json and --report --format json (D-12, RPT-05)."""
    payload = {
        "summary": {
            "total_runs": metrics.get("total_runs", 0),
            "median_error_pct": metrics.get("median_error_pct"),
            "p90_latency_s": metrics.get("p90_latency_s"),
            "calibration_tier": metrics.get("calibration_tier", "prior"),
            "last_run_timestamp": metrics.get("last_run_timestamp"),
        },
        "ledger": {
            "path": ledger_info.get("path", ""),
            "size_bytes": ledger_info.get("bytes", 0),
            "schema_version": 1,
            "rows": ledger_info.get("rows", 0),
            "archives": ledger_info.get("archives", 0),
        },
    }
    return json.dumps(payload, indent=2)
```

#### Core Pattern: Fluid Responsive SVG with Native Tooltips (D-02, D-03, D-04, D-05)
```python
def render_scatter_svg(records: list[dict], metrics: dict) -> str:
    """Renders Predicted vs Actual scatter plot with 45° diagonal and 3-tier colors (D-02, D-03, D-04, D-05)."""
    w, h = 500, 320
    pad_left, pad_bottom, pad_top, pad_right = 50, 40, 20, 20
    plot_w = w - pad_left - pad_right
    plot_h = h - pad_top - pad_bottom

    # Scaling math and axis generation...
    # Color coding: Green (<15%), Amber (15-30%), Crimson (>30%)
    dots = []
    for r in records:
        pred_s, act_s, err_pct = extract_run_points(r)
        if pred_s is None or act_s is None:
            continue
        cx = pad_left + (act_s / max_val) * plot_w
        cy = pad_top + plot_h - (pred_s / max_val) * plot_h
        color = "#22c55e" if err_pct < 15.0 else ("#f59e0b" if err_pct <= 30.0 else "#ef4444")
        dots.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{color}" opacity="0.85">'
            f'<title>Run {html.escape(str(r.get("run_id")))}: Pred {pred_s:.2f}s, Actual {act_s:.2f}s ({err_pct:.1f}% error)</title>'
            f'</circle>'
        )

    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" '
        f'style="width: 100%; height: auto; max-width: 100%; display: block;">'
        f'{gridlines}'
        f'<line x1="{pad_left}" y1="{pad_top + plot_h}" x2="{pad_left + plot_w}" y2="{pad_top}" '
        f'stroke="#475569" stroke-dasharray="4,4" stroke-width="1.5" />'
        f'{"".join(dots)}'
        f'</svg>'
    )
```

#### Core Pattern: Secure Browser Launch (`xdg-open`, D-24, RPT-06)
```python
def open_report_file(path: Path, args: Optional[argparse.Namespace] = None) -> bool:
    """Strictly validates target path before executing xdg-open with notification fallback (D-24, RPT-06)."""
    target = Path(path).resolve()
    allowed_dirs = [
        voicemode_telemetry.get_state_dir().resolve(),
        voicemode_telemetry.get_metrics_dir().resolve(),
    ]
    is_safe = False
    for allowed in allowed_dirs:
        try:
            if os.path.commonpath([str(target), str(allowed)]) == str(allowed):
                is_safe = True
                break
        except ValueError:
            continue

    if not is_safe:
        msg = f"Report open rejected: {target} is not in state directory"
        print(msg, file=sys.stderr, flush=True)
        try:
            from voice import notify
            notify("Voice Report Security", f"Open rejected: {target} outside state dir", args)
        except Exception:
            pass
        return False

    xdg_bin = shutil.which("xdg-open")
    if not xdg_bin:
        msg = f"xdg-open not found. Report saved at: {target}"
        print(msg, file=sys.stderr, flush=True)
        try:
            from voice import notify
            notify("Voice Report", f"Report saved at: {target}", args)
        except Exception:
            pass
        return False

    try:
        subprocess.Popen([xdg_bin, str(target)], start_new_session=True)
        return True
    except Exception as exc:
        msg = f"Failed to execute xdg-open: {exc}. Report saved at: {target}"
        print(msg, file=sys.stderr, flush=True)
        try:
            from voice import notify
            notify("Voice Report", f"Report saved at: {target}", args)
        except Exception:
            pass
        return False
```

---

### `voice.py` (controller / CLI dispatcher / worker lifecycle, request-response / lifecycle hook)

**Analog:** `voice.py`  
**Purpose:** CLI arguments registration for `--report`, `--metrics`, `--format`, `--output`, `--open`, `--since`, `--last`; lazy CLI dispatch in `main()` preserving the strict zero-heavy-imports constraint; atomic report pre-rendering hook inside `finalize_background_run()`; and advertising the pre-rendered `report_path` in `status.json`.

#### Core Pattern: CLI Argument Registration
From [voice.py:3890-3895](file:///home/pera/github_repo/Voice/voice.py#L3890-L3895):
```python
    parser.add_argument("--metrics", action="store_true", help="Show metrics summary.")
    parser.add_argument("--report", action="store_true", help="Generate accuracy and latency report.")
    parser.add_argument(
        "--format",
        choices=("text", "html", "csv", "json"),
        default=None,
        help="Report output format (default: text). Inferred from --output extension if set.",
    )
    parser.add_argument("--output", metavar="PATH", help="Write report output to specified file.")
    parser.add_argument("--open", action="store_true", help="Open HTML report in default browser via xdg-open.")
    parser.add_argument("--since", metavar="TIME", help="Filter report runs since ISO date or relative duration (e.g. 24h, 7d).")
    parser.add_argument("--last", metavar="N", default=None, help="Filter report to last N runs or 'all' (default: 200).")
```

#### Core Pattern: Lazy CLI Dispatch in `main()` (Zero Heavy Imports)
From [voice.py:4057-4074](file:///home/pera/github_repo/Voice/voice.py#L4057-L4074):
```python
    if getattr(args, "metrics", False):
        try:
            import voicemode_report
            return voicemode_report.handle_metrics_command(args)
        except Exception as exc:
            print(f"Error displaying metrics: {exc}", file=sys.stderr)
            return 1

    if getattr(args, "report", False):
        try:
            import voicemode_report
            return voicemode_report.handle_report_command(args)
        except Exception as exc:
            print(f"Error generating report: {exc}", file=sys.stderr)
            return 1
```

#### Core Pattern: Worker Lifecycle Hook in `finalize_background_run()` (D-18, D-20)
From [voice.py:1298-1308](file:///home/pera/github_repo/Voice/voice.py#L1298-L1308):
```python
                voicemode_telemetry.append_ledger_row(record)
                row_written = True

                # Post-paste calibration cache update (strictly after ledger write)
                try:
                    voicemode_telemetry.update_calibration_from_run(record)
                except Exception:
                    pass

                # Pre-render report.html for instant click-through (last 200 runs) (D-18, D-20)
                try:
                    import voicemode_report
                    voicemode_report.generate_prerendered_report()
                except Exception as rpt_exc:
                    print(f"Error generating prerendered report: {rpt_exc}", file=sys.stderr, flush=True)
```

#### Core Pattern: Publishing `report_path` in `status.json` (Open Question 2 Resolution)
From [voice.py:2183-2196](file:///home/pera/github_repo/Voice/voice.py#L2183-L2196):
```python
    status_state = {
        "pid": pid,
        "run_id": run_id,
        "started_at": ts_start,
        "audio_s": 0.0,
        "segments": 0,
        "segments_done": 0,
        "transcribed_audio_s": 0.0,
        "eta_remaining_s": None,
        "eta_confidence": None,
        "eta_source": None,
        "overrun": False,
        "report_path": str(voicemode_telemetry.get_state_dir() / "report.html"),
    }
```

---

### `tests/test_report.py` (test, unit / integration / CLI / file-I/O)

**Analog:** `tests/test_eta_cli.py`, `tests/test_telemetry.py`  
**Purpose:** Comprehensive automated test coverage for RPT-01 through RPT-06.

#### Imports Pattern
From [tests/test_eta_cli.py:1-15](file:///home/pera/github_repo/Voice/tests/test_eta_cli.py#L1-L15):
```python
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

from _hermetic import TempXdgTestCase
import voice
import voicemode_report
import voicemode_telemetry
```

#### Core Pattern: Synthetic Record Factory
From [tests/test_eta_cli.py:21-83](file:///home/pera/github_repo/Voice/tests/test_eta_cli.py#L21-L83):
```python
def _make_record(
    run_id="run-1",
    audio_s=4.0,
    pred_s=2.5,
    actual_s=2.4,
    load_ms=200.0,
    decode_ms=2100.0,
    finalize_ms=50.0,
    insert_ms=50.0,
    model="medium",
    device="cpu",
    outcome="success",
    ts_start=None,
):
    now = time.time()
    return {
        "schema": 1,
        "source": "stt",
        "run_id": run_id,
        "install_id": "test-install",
        "ts_start": ts_start or (now - 10.0),
        "ts_end": now,
        "outcome": outcome,
        "error_stage": None,
        "actual": {
            "total_ms": (actual_s * 1000.0) if actual_s is not None else None,
            "load_ms": load_ms,
            "decode_ms": decode_ms,
            "finalize_ms": finalize_ms,
            "insert_ms": insert_ms,
        },
        "predicted": {
            "shown_s": pred_s,
            "shown_at_epoch": now - 8.0,
            "source": "calibrated",
            "key_level": "L0",
            "n": 10,
            "confidence": "high",
            "revisions": 0,
            "actual_s": actual_s,
        },
        "audio_s": audio_s,
        "chars_out": 25,
        "chars_typed": 25,
        "fallback_used": False,
        "insert_ok": True,
        "segments": [],
        "config": {
            "model": model,
            "device": device,
            "compute_type": "int8",
            "beam_size": 1,
            "vad_filter": True,
            "language": "en",
            "chunk_s": 180.0,
        },
        "backend": f"{device}, int8",
    }
```

#### Core Pattern: Zero-Heavy-Imports Test (FND-01 / RPT-01)
```python
class TestReportCLI(TempXdgTestCase):
    def test_no_heavy_imports_on_report_path(self):
        """RPT-01: voice --report must never load faster_whisper, numpy, or sounddevice."""
        code = (
            "import sys; "
            "import voice; "
            "args = voice.parse_args(['--report']); "
            "import voicemode_report; "
            "voicemode_report.handle_report_command(args); "
            "forbidden = ['faster_whisper', 'numpy', 'sounddevice']; "
            "loaded = [m for m in forbidden if m in sys.modules]; "
            "assert not loaded, f'Heavy modules imported: {loaded}'"
        )
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Import assertion failed: {res.stderr}")
```

#### Core Pattern: Self-Contained Zero-JS HTML Test (RPT-02, D-01, D-03)
```python
class TestHTMLReport(TempXdgTestCase):
    def test_html_report_zero_js_and_self_contained(self):
        """RPT-02: HTML report contains zero <script> tags, zero http(s) links, and all 4 SVG charts."""
        records = [_make_record(run_id=f"r-{i}", audio_s=2.0 + i) for i in range(10)]
        metrics = voicemode_report.compute_report_metrics(records)
        html_doc = voicemode_report.render_html_report(records, metrics)

        self.assertNotIn("<script", html_doc.lower())
        self.assertNotIn("http://", html_doc.lower())
        self.assertNotIn("https://", html_doc.lower())
        self.assertIn("viewBox=", html_doc)
        self.assertIn("<title>", html_doc)  # Tooltips
        self.assertIn("privacy-card", html_doc)
```

#### Core Pattern: Empty State Visual Onboarding Test (RPT-03, D-08)
```python
class TestEmptyStateAndPrivacy(TempXdgTestCase):
    def test_empty_state_rendering(self):
        """RPT-03: Empty ledger renders visual onboarding card, ghost outlines, and shortcut reminder."""
        records = []
        metrics = voicemode_report.compute_report_metrics(records)
        html_doc = voicemode_report.render_html_report(records, metrics)

        self.assertIn("SUPER+SHIFT+M", html_doc)
        self.assertIn("No recordings yet", html_doc)
        self.assertIn("ghost-chart", html_doc)
```

#### Core Pattern: Pre-Render Worker Hook Test (RPT-04, D-18, D-20)
```python
class TestPreRenderWorker(TempXdgTestCase):
    def test_finalize_background_run_prerenders_report(self):
        """RPT-04: finalize_background_run atomically creates report.html in state directory."""
        state_dir = voicemode_telemetry.get_state_dir()
        report_file = state_dir / "report.html"
        self.assertFalse(report_file.exists())

        run_state = {
            "lock": MagicMock(),
            "finalized": False,
            "pid": 9999,
            "run_id": "test-prerender",
            "ts_start": time.time() - 2.0,
            "t_start": time.monotonic() - 2.0,
            "args": voice.parse_args([]),
            "recorder": None,
            "wav_paths": [],
            "should_delete": False,
            "outcome": "success",
            "error_stage": None,
            "results": {},
            "loader_state": {"load_ms": 100.0, "backend": "cpu, int8"},
            "model_holder": {"state": None},
            "text_holder": {"text": "hello"},
            "chars_typed": [5],
            "audio_s": 2.0,
            "status_state": {},
            "finalize_ms": 30.0,
            "insert_ms": 20.0,
            "insert_ok": True,
            "backend": "cpu, int8",
            "predicted": {"shown_s": 1.5, "actual_s": 1.4},
            "text": "hello",
        }

        with patch("voicemode_report.generate_prerendered_report", wraps=voicemode_report.generate_prerendered_report) as mock_gen:
            voice.finalize_background_run(run_state, outcome="success")
            mock_gen.assert_called_once()
            self.assertTrue(report_file.exists())
```

#### Core Pattern: Converged JSON Schema Test (RPT-05, D-12)
```python
class TestExportFormats(TempXdgTestCase):
    def test_converged_json_schema(self):
        """RPT-05: voice --metrics --json and voice --report --format json produce identical schema."""
        rec = _make_record(run_id="r1")
        voicemode_telemetry.append_ledger_row(rec)

        metrics_args = voice.parse_args(["--metrics", "--json-status"])
        report_args = voice.parse_args(["--report", "--format", "json"])

        metrics_out = StringIO()
        report_out = StringIO()

        with patch("sys.stdout", metrics_out):
            voice.main(["--metrics", "--json-status"])
        with patch("sys.stdout", report_out):
            voice.main(["--report", "--format", "json"])

        m_obj = json.loads(metrics_out.getvalue().strip())
        r_obj = json.loads(report_out.getvalue().strip())

        self.assertEqual(m_obj.keys(), r_obj.keys())
        self.assertEqual(m_obj["summary"].keys(), r_obj["summary"].keys())
        self.assertEqual(m_obj["ledger"].keys(), r_obj["ledger"].keys())
```

#### Core Pattern: `xdg-open` Containment Security Test (RPT-06, D-24)
```python
class TestXdgOpenSecurity(TempXdgTestCase):
    def test_xdg_open_path_validation(self):
        """RPT-06: Paths outside state/metrics directory are rejected with warning."""
        evil_path = Path("/etc/passwd")
        with patch("subprocess.Popen") as mock_popen, \
             patch("voice.notify") as mock_notify:
            ok = voicemode_report.open_report_file(evil_path)
            self.assertFalse(ok)
            mock_popen.assert_not_called()
            mock_notify.assert_called_once()

    def test_xdg_open_argument_list_execution(self):
        """RPT-06: Valid target passes argument list to subprocess.Popen."""
        safe_path = voicemode_telemetry.get_state_dir() / "report.html"
        safe_path.touch()

        with patch("shutil.which", return_value="/usr/bin/xdg-open"), \
             patch("subprocess.Popen") as mock_popen:
            ok = voicemode_report.open_report_file(safe_path)
            self.assertTrue(ok)
            mock_popen.assert_called_once_with(["/usr/bin/xdg-open", str(safe_path.resolve())], start_new_session=True)
```

---

## Shared Patterns

### 1. Atomic Persistence via Tempfile Replacement
**Source:** [voicemode_telemetry.py:362-386](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L362-L386)  
**Apply to:** `generate_prerendered_report()`, `save_report_to_file()`.  
**Mechanism:** `tempfile.mkstemp(dir=target.parent)` $\to$ `os.write` $\to$ `os.fsync` $\to$ `os.chmod(0o600)` $\to$ `os.replace`. Guarantees readers (such as Quickshell or a browser) never observe a half-written file.

### 2. Strict Zero Heavy-Import Enforcement
**Source:** [voice.py:672](file:///home/pera/github_repo/Voice/voice.py#L672), [08-RESEARCH.md:248-255](file:///home/pera/github_repo/Voice/.planning/phases/08-accuracy-report-click-through/08-RESEARCH.md#L248-L255)  
**Apply to:** `voicemode_report.py`, `voice.py` (`--report`, `--metrics` CLI branches).  
**Mechanism:** Standard library only. Lazy module loading within dispatch functions. Keeps execution times under 100 ms and prevents loading the 1.9 GB CTranslate2/Whisper runtime.

### 3. Fail-Open / Best-Effort Worker Finalization
**Source:** [voice.py:1301-1306](file:///home/pera/github_repo/Voice/voice.py#L1301-L1306)  
**Apply to:** Report regeneration hook inside `finalize_background_run()`.  
**Mechanism:** Wrap background report generation in a broad `try ... except Exception as rpt_exc: print(..., file=sys.stderr)`. If report generation fails for any reason, the transcription is still safely typed into the user's window and the PID lock is properly released.

### 4. Hermetic Test Environment
**Source:** [tests/_hermetic.py:19-53](file:///home/pera/github_repo/Voice/tests/_hermetic.py#L19-L53)  
**Apply to:** All test cases in `tests/test_report.py`.  
**Mechanism:** Inherits from `TempXdgTestCase`. Re-routes `XDG_RUNTIME_DIR` and `XDG_STATE_HOME` to isolated temp directories to prevent leaking test records into user state.

### 5. Containment Path Validation
**Source:** [08-RESEARCH.md:474-500](file:///home/pera/github_repo/Voice/.planning/phases/08-accuracy-report-click-through/08-RESEARCH.md#L474-L500)  
**Apply to:** `open_report_file()` before spawning `xdg-open`.  
**Mechanism:** `os.path.commonpath([target, allowed_dir]) == str(allowed_dir)`. Protects against directory traversal attacks and prevents launching arbitrary user executables via `xdg-open`.

---

## No Analog Found

- **Zero-Dependency Inline SVG Charts:** Generating inline SVG strings (scatter plot, trend curve, residual histogram, and stacked stage bars) directly from Python f-strings without external charting packages (e.g. Matplotlib, Vega, Chart.js) is new to this codebase.  
  *Direct Analog / Design:* Directly modeled on W3C SVG 1.1 specifications using fluid responsive `<svg viewBox="0 0 W H">` containers, native `<title>` tooltip elements, and CSS `:hover` states, following the zero-JS/zero-network architecture established in `08-CONTEXT.md` and `08-RESEARCH.md`.

---

## Metadata

**Analog search scope:**
- `voicemode_telemetry.py` (atomic I/O, schemas, ledger reading, ledger health)
- `voice.py` (CLI parsing, process lifecycle, worker finalization, desktop notification)
- `tests/test_eta_cli.py` (CLI argument execution, JSON status assertion, hermetic tests)
- `tests/test_telemetry.py` (ledger append and serialization tests)
- `tests/_hermetic.py` (hermetic XDG runtime/state environment)

**Files scanned:** 6  
**Pattern mapping date:** 2026-10-30
