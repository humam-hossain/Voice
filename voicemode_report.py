"""Accuracy & latency reporting engine for voicemode.

Provides tolerant JSONL ledger loading, multi-criteria filtering,
statistics aggregation, terminal summary, canonical CSV export,
converged JSON output, and secure browser launch.

Imports: stdlib only + voicemode_telemetry.  Never imports faster_whisper,
numpy, sounddevice, or jinja2 (FND-01 / RPT-01).
"""
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


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CSV_HEADERS = [
    "run_id", "timestamp", "model", "device", "audio_s", "predicted_s",
    "actual_s", "error_s", "error_pct", "load_s", "record_s", "decode_s",
    "finalize_s", "insert_s", "outcome", "eta_source", "confidence",
]


# ---------------------------------------------------------------------------
# Ledger Loading (D-21)
# ---------------------------------------------------------------------------

def load_ledger_records(
    paths: Optional[list[Path]] = None,
    max_records: Optional[int] = None,
) -> tuple[list[dict], int]:
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


# ---------------------------------------------------------------------------
# Filtering (D-14, D-16)
# ---------------------------------------------------------------------------

def parse_since_argument(val: str) -> Optional[float]:
    """Parses ISO 8601 timestamps or relative intervals (24h, 7d, 30d, 60m) into epoch."""
    if not val:
        return None
    val = val.strip()
    # Relative intervals
    m = re.match(r"^(\d+)([hdwm])$", val, re.IGNORECASE)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        now = time.time()
        if unit == "h":
            return now - amount * 3600
        elif unit == "d":
            return now - amount * 86400
        elif unit == "w":
            return now - amount * 604800
        elif unit == "m":
            return now - amount * 60
        return None
    # ISO 8601
    try:
        dt = datetime.datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


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


# ---------------------------------------------------------------------------
# Statistics Aggregation
# ---------------------------------------------------------------------------

def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def compute_report_metrics(records: list[dict]) -> dict:
    """Computes aggregate metrics: total runs, median error %, p90 latency, stage breakdowns."""
    total_runs = len(records)
    if total_runs == 0:
        return {
            "total_runs": 0,
            "median_error_pct": None,
            "p90_latency_s": None,
            "calibration_tier": "prior",
            "last_run_timestamp": None,
            "overrun_count": 0,
            "stage_medians": {},
            "stage_p90s": {},
        }

    error_pcts: list[float] = []
    latencies: list[float] = []
    load_vals: list[float] = []
    decode_vals: list[float] = []
    finalize_vals: list[float] = []
    insert_vals: list[float] = []
    overrun_count = 0

    for r in records:
        pred = r.get("predicted") or {}
        act = r.get("actual") or {}

        pred_s = pred.get("shown_s")
        act_s = pred.get("actual_s")
        if act_s is None and act.get("total_ms") is not None:
            act_s = _safe_float(act["total_ms"]) / 1000.0

        if pred_s is not None and act_s is not None:
            try:
                p = float(pred_s)
                a = float(act_s)
                if a > 0:
                    err_pct = abs(p - a) / a * 100.0
                    error_pcts.append(err_pct)
                    if p < a:
                        overrun_count += 1
            except (ValueError, TypeError):
                pass

        # Total latency
        if act.get("total_ms") is not None:
            latencies.append(_safe_float(act["total_ms"]) / 1000.0)

        # Stage latencies
        if act.get("load_ms") is not None:
            load_vals.append(_safe_float(act["load_ms"]) / 1000.0)
        if act.get("decode_ms") is not None:
            decode_vals.append(_safe_float(act["decode_ms"]) / 1000.0)
        if act.get("finalize_ms") is not None:
            finalize_vals.append(_safe_float(act["finalize_ms"]) / 1000.0)
        if act.get("insert_ms") is not None:
            insert_vals.append(_safe_float(act["insert_ms"]) / 1000.0)

    median_error_pct = round(statistics.median(error_pcts), 1) if error_pcts else None
    p90_latency_s = _percentile(latencies, 0.90) if latencies else None

    # Stage medians and p90s
    stage_medians: dict[str, float] = {}
    stage_p90s: dict[str, float] = {}
    for name, vals in [("load", load_vals), ("decode", decode_vals),
                       ("finalize", finalize_vals), ("insert", insert_vals)]:
        if vals:
            stage_medians[name] = round(statistics.median(vals), 3)
            stage_p90s[name] = _percentile(vals, 0.90)

    # Calibration tier
    try:
        cal = voicemode_telemetry.load_calibration()
        cal_tier = "prior"
        accs = cal.get("accumulators", {})
        for tier in ("L0", "L1", "L2"):
            tier_map = accs.get(tier, {})
            for entry in tier_map.values():
                if isinstance(entry, dict) and entry.get("n", 0) >= 3:
                    cal_tier = tier
                    break
            if cal_tier != "prior":
                break
    except Exception:
        cal_tier = "prior"

    last_ts = None
    for r in reversed(records):
        ts = r.get("ts_end") or r.get("ts_start")
        if ts is not None:
            last_ts = float(ts)
            break

    return {
        "total_runs": total_runs,
        "median_error_pct": median_error_pct,
        "p90_latency_s": p90_latency_s,
        "calibration_tier": cal_tier,
        "last_run_timestamp": last_ts,
        "overrun_count": overrun_count,
        "stage_medians": stage_medians,
        "stage_p90s": stage_p90s,
    }


def _percentile(values: list[float], pct: float) -> float:
    """Computes percentile by sorted index selection."""
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(math.ceil(pct * len(s))) - 1
    idx = max(0, min(idx, len(s) - 1))
    return round(s[idx], 3)


# ---------------------------------------------------------------------------
# CSV Export (D-11, RPT-05)
# ---------------------------------------------------------------------------

def record_to_csv_row(rec: dict) -> dict[str, Any]:
    """Extracts a flat row from a ledger record for CSV export."""
    pred = rec.get("predicted") or {}
    act = rec.get("actual") or {}
    cfg = rec.get("config") or {}

    audio_s = _safe_float(rec.get("audio_s"))
    pred_s = float(pred["shown_s"]) if pred.get("shown_s") is not None else None

    act_s = None
    if pred.get("actual_s") is not None:
        act_s = float(pred["actual_s"])
    elif act.get("total_ms") is not None:
        act_s = round(_safe_float(act["total_ms"]) / 1000.0, 3)

    error_s = round(pred_s - act_s, 3) if pred_s is not None and act_s is not None else None
    error_pct = round(abs(error_s) / act_s * 100.0, 1) if error_s is not None and act_s and act_s > 0 else None

    ts = rec.get("ts_start") or rec.get("ts_end") or 0.0
    ts_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""

    return {
        "run_id": rec.get("run_id") or "",
        "timestamp": ts_str,
        "model": cfg.get("model") or "",
        "device": cfg.get("device") or "",
        "audio_s": audio_s,
        "predicted_s": pred_s if pred_s is not None else "",
        "actual_s": act_s if act_s is not None else "",
        "error_s": error_s if error_s is not None else "",
        "error_pct": error_pct if error_pct is not None else "",
        "load_s": round(_safe_float(act.get("load_ms")) / 1000.0, 3) if act.get("load_ms") is not None else 0.0,
        "record_s": audio_s,
        "decode_s": round(_safe_float(act.get("decode_ms")) / 1000.0, 3) if act.get("decode_ms") is not None else 0.0,
        "finalize_s": round(_safe_float(act.get("finalize_ms")) / 1000.0, 3) if act.get("finalize_ms") is not None else 0.0,
        "insert_s": round(_safe_float(act.get("insert_ms")) / 1000.0, 3) if act.get("insert_ms") is not None else 0.0,
        "outcome": rec.get("outcome") or "unknown",
        "eta_source": pred.get("source") or "",
        "confidence": pred.get("confidence") or "",
    }


def render_csv(records: list[dict]) -> str:
    """Exports records to CSV with exact 17 canonical headers (D-11, RPT-05)."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, lineterminator="\n")
    writer.writeheader()
    for rec in records:
        writer.writerow(record_to_csv_row(rec))
    return output.getvalue()


# ---------------------------------------------------------------------------
# JSON Export (D-12, RPT-05)
# ---------------------------------------------------------------------------

def _get_ledger_info() -> dict:
    """Gathers ledger health info for JSON output."""
    try:
        health = voicemode_telemetry.ledger_health()
        return {
            "path": health.get("path", ""),
            "bytes": health.get("bytes", 0),
            "rows": health.get("rows", 0),
            "archives": health.get("archives", 0),
        }
    except Exception:
        return {"path": "", "bytes": 0, "rows": 0, "archives": 0}


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


# ---------------------------------------------------------------------------
# Terminal Summary (D-09)
# ---------------------------------------------------------------------------

def render_terminal_summary(
    records: list[dict],
    metrics: dict,
    skipped_count: int = 0,
) -> str:
    """Formats CLI summary card with aggregate metrics and recent runs table (D-09)."""
    lines: list[str] = []

    total = metrics.get("total_runs", 0)
    med_err = metrics.get("median_error_pct")
    p90 = metrics.get("p90_latency_s")
    cal_tier = metrics.get("calibration_tier", "prior")
    overrun = metrics.get("overrun_count", 0)

    # Hero card
    lines.append("╔══════════════════════════════════════════════════╗")
    lines.append("║            Voice Accuracy Report                 ║")
    lines.append("╠══════════════════════════════════════════════════╣")
    lines.append(f"║  Total Runs:      {total:<30}║")
    med_str = f"{med_err:.1f}%" if med_err is not None else "N/A"
    lines.append(f"║  Median Error:    {med_str:<30}║")
    p90_str = f"{p90:.3f}s" if p90 is not None else "N/A"
    lines.append(f"║  P90 Latency:     {p90_str:<30}║")
    lines.append(f"║  Calibration:     {cal_tier:<30}║")
    lines.append(f"║  Overruns:        {overrun:<30}║")
    if skipped_count > 0:
        lines.append(f"║  Skipped Rows:    {skipped_count:<30}║")
    lines.append("╚══════════════════════════════════════════════════╝")

    if total == 0:
        lines.append("")
        lines.append("No runs recorded yet. Start dictating with SUPER+SHIFT+M!")
        report_path = voicemode_telemetry.get_state_dir() / "report.html"
        lines.append(f"\nReport: {report_path}")
        return "\n".join(lines)

    # Recent runs table (last 10)
    lines.append("")
    header = f"{'RUN_ID':<14} {'DATE/TIME':<20} {'AUDIO':>6} {'PRED':>6} {'ACTUAL':>6} {'ERR%':>6} {'STATUS':<8} {'L/D/F/I'}"
    lines.append(header)
    lines.append("─" * len(header))

    recent = records[-10:]
    for r in recent:
        pred = r.get("predicted") or {}
        act = r.get("actual") or {}
        cfg = r.get("config") or {}

        run_id = str(r.get("run_id", ""))[:12]
        ts = r.get("ts_start") or r.get("ts_end") or 0.0
        dt_str = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)) if ts else "N/A"

        audio_s = _safe_float(r.get("audio_s"))
        pred_s = _safe_float(pred.get("shown_s")) if pred.get("shown_s") is not None else None
        act_s = _safe_float(pred.get("actual_s")) if pred.get("actual_s") is not None else None
        if act_s is None and act.get("total_ms") is not None:
            act_s = _safe_float(act["total_ms"]) / 1000.0

        if pred_s is not None and act_s is not None and act_s > 0:
            err_pct = abs(pred_s - act_s) / act_s * 100.0
            err_str = f"{err_pct:.1f}%"
        else:
            err_str = "N/A"

        outcome = r.get("outcome", "?")[:7]
        load_s = _safe_float(act.get("load_ms")) / 1000.0 if act.get("load_ms") is not None else 0.0
        decode_s = _safe_float(act.get("decode_ms")) / 1000.0 if act.get("decode_ms") is not None else 0.0
        fin_s = _safe_float(act.get("finalize_ms")) / 1000.0 if act.get("finalize_ms") is not None else 0.0
        ins_s = _safe_float(act.get("insert_ms")) / 1000.0 if act.get("insert_ms") is not None else 0.0
        stages = f"{load_s:.2f}/{decode_s:.2f}/{fin_s:.2f}/{ins_s:.2f}"

        audio_str = f"{audio_s:.1f}" if audio_s else "N/A"
        pred_str = f"{pred_s:.2f}" if pred_s is not None else "N/A"
        act_str = f"{act_s:.2f}" if act_s is not None else "N/A"

        lines.append(
            f"{run_id:<14} {dt_str:<20} {audio_str:>6} {pred_str:>6} {act_str:>6} "
            f"{err_str:>6} {outcome:<8} {stages}"
        )

    report_path = voicemode_telemetry.get_state_dir() / "report.html"
    lines.append(f"\nReport: {report_path}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Secure Browser Launch (D-24, RPT-06)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Pre-Render Hook (D-18, D-19, D-20)
# ---------------------------------------------------------------------------

def generate_prerendered_report(dest_path: Optional[Path] = None) -> Path:
    """Pre-renders report.html for the last 200 runs and atomically writes to disk (D-18, D-19)."""
    if dest_path is None:
        dest_path = voicemode_telemetry.get_state_dir() / "report.html"

    records, skipped_count = load_ledger_records(max_records=200)
    metrics = compute_report_metrics(records)

    # Minimal HTML stub for now (Phase 08-02 will add full SVG charts)
    html_content = _render_html_stub(records, metrics, skipped_count)

    voicemode_telemetry.atomic_write_text(dest_path, html_content, mode=0o600)
    return dest_path


def _render_html_stub(records: list[dict], metrics: dict, skipped_count: int = 0) -> str:
    """Minimal HTML report skeleton (full SVG charts added in plan 08-02)."""
    total = metrics.get("total_runs", 0)
    med_err = metrics.get("median_error_pct")
    p90 = metrics.get("p90_latency_s")
    cal_tier = metrics.get("calibration_tier", "prior")
    med_str = f"{med_err:.1f}%" if med_err is not None else "N/A"
    p90_str = f"{p90:.3f}s" if p90 is not None else "N/A"
    metrics_path = html.escape(str(voicemode_telemetry.get_ledger_path()))

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Voice Accuracy Report</title></head>
<body style="background:#0f172a;color:#f8fafc;font-family:system-ui,sans-serif;padding:2rem;">
<h1>Voice Accuracy Report</h1>
<p>Total Runs: {total} | Median Error: {med_str} | P90 Latency: {p90_str} | Calibration: {html.escape(cal_tier)}</p>
{_render_skipped_warning(skipped_count)}
<div class="privacy-card"><p>Ledger: <code>{metrics_path}</code></p></div>
</body></html>"""


def _render_skipped_warning(skipped_count: int) -> str:
    if skipped_count > 0:
        return f'<p style="color:#f59e0b;">⚠️ {skipped_count} row(s) skipped due to parse errors.</p>'
    return ""


# ---------------------------------------------------------------------------
# CLI Command Handlers
# ---------------------------------------------------------------------------

def _infer_format(args: argparse.Namespace) -> str:
    """Infers output format from --format flag or --output file extension."""
    fmt = getattr(args, "format", None)
    if fmt:
        return fmt

    output_path = getattr(args, "output", None)
    if output_path:
        ext = Path(output_path).suffix.lower()
        ext_map = {".csv": "csv", ".json": "json", ".html": "html", ".htm": "html"}
        return ext_map.get(ext, "text")

    return "text"


def handle_report_command(args: argparse.Namespace) -> int:
    """Handles `voice --report` with filtering, format selection, and output routing."""
    try:
        records, skipped_count = load_ledger_records()

        # Apply filters
        since = getattr(args, "since", None)
        last = getattr(args, "last", None)
        if last is None:
            last = 200
        model_filter = getattr(args, "model", None)
        device_filter = getattr(args, "device", None)

        filtered = filter_records(records, since=since, last=last, model=model_filter, device=device_filter)
        metrics = compute_report_metrics(filtered)

        fmt = _infer_format(args)
        output_path = getattr(args, "output", None)

        if fmt == "csv":
            content = render_csv(filtered)
        elif fmt == "json":
            ledger_info = _get_ledger_info()
            content = render_json(metrics, ledger_info)
        elif fmt == "html":
            content = _render_html_stub(filtered, metrics, skipped_count)
        else:
            content = render_terminal_summary(filtered, metrics, skipped_count)

        if output_path:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(content, encoding="utf-8")
            print(f"Report written to {out_p}", flush=True)
        else:
            print(content, flush=True)

        # --open flag
        if getattr(args, "open", False):
            if output_path:
                open_report_file(Path(output_path), args)
            else:
                report_path = voicemode_telemetry.get_state_dir() / "report.html"
                if not report_path.exists():
                    generate_prerendered_report(report_path)
                open_report_file(report_path, args)

        return 0
    except Exception as exc:
        print(f"Error generating report: {exc}", file=sys.stderr, flush=True)
        return 1


def handle_metrics_command(args: argparse.Namespace) -> int:
    """Handles `voice --metrics` with JSON output support."""
    try:
        json_mode = getattr(args, "json_status", False) or getattr(args, "json", False)

        if json_mode:
            records, _ = load_ledger_records()
            metrics = compute_report_metrics(records)
            ledger_info = _get_ledger_info()
            content = render_json(metrics, ledger_info)
            print(content, flush=True)
        else:
            # Quick text summary
            health = voicemode_telemetry.ledger_health()
            records, skipped = load_ledger_records()
            metrics = compute_report_metrics(records)
            lines = [
                f"Ledger: {health.get('path', 'N/A')}",
                f"Size: {health.get('bytes', 0)} bytes",
                f"Rows: {health.get('rows', 0)}",
                f"Archives: {health.get('archives', 0)}",
                f"Total Runs: {metrics.get('total_runs', 0)}",
            ]
            med = metrics.get("median_error_pct")
            if med is not None:
                lines.append(f"Median Error: {med:.1f}%")
            p90 = metrics.get("p90_latency_s")
            if p90 is not None:
                lines.append(f"P90 Latency: {p90:.3f}s")
            lines.append(f"Calibration: {metrics.get('calibration_tier', 'prior')}")
            if skipped > 0:
                lines.append(f"Skipped Rows: {skipped}")
            print("\n".join(lines), flush=True)

        return 0
    except Exception as exc:
        print(f"Error displaying metrics: {exc}", file=sys.stderr, flush=True)
        return 1
