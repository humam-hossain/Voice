"""Accuracy & latency reporting engine for voicemode.

Provides tolerant JSONL ledger loading, multi-criteria filtering,
statistics aggregation, terminal summary, canonical CSV export,
converged JSON output, fluid responsive inline SVG charts, zero-JS
dark HTML dashboard, visual onboarding empty state, and secure browser launch.

Imports: stdlib only + voicemode_telemetry. Never imports faster_whisper,
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
# Constants & Color Palette (Dark Theme / Arch & Hyprland Aesthetic)
# ---------------------------------------------------------------------------

CSV_HEADERS = [
    "run_id", "timestamp", "model", "device", "audio_s", "predicted_s",
    "actual_s", "error_s", "error_pct", "load_s", "record_s", "decode_s",
    "finalize_s", "insert_s", "outcome", "eta_source", "confidence",
]

COLOR_BG = "#0f172a"
COLOR_CARD = "#1e293b"
COLOR_BORDER = "#334155"
COLOR_TEXT = "#f8fafc"
COLOR_MUTED = "#94a3b8"

# 3-tier accuracy color thresholds (D-05)
COLOR_GREEN = "#22c55e"    # <15% error
COLOR_AMBER = "#f59e0b"    # 15–30% error
COLOR_CRIMSON = "#ef4444"  # >30% error or severe overrun

# Stage colors
COLOR_LOAD = "#6366f1"      # Indigo
COLOR_DECODE = "#38bdf8"    # Sky
COLOR_FINALIZE = "#8b5cf6"  # Purple
COLOR_INSERT = "#10b981"    # Emerald


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

    if model:
        m_lower = model.lower()
        filtered = [r for r in filtered if str(r.get("config", {}).get("model", "")).lower() == m_lower]

    if device:
        d_lower = device.lower()
        filtered = [r for r in filtered if str(r.get("config", {}).get("device", "")).lower() == d_lower]

    if since:
        since_ts = parse_since_argument(since)
        if since_ts is not None:
            filtered = [r for r in filtered if (r.get("ts_start") or r.get("ts_end") or 0.0) >= since_ts]

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


def extract_run_points(rec: dict) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Extracts (pred_s, act_s, error_pct) from a ledger record."""
    pred = rec.get("predicted") or {}
    act = rec.get("actual") or {}

    pred_s = _safe_float(pred.get("shown_s")) if pred.get("shown_s") is not None else None
    act_s = _safe_float(pred.get("actual_s")) if pred.get("actual_s") is not None else None
    if act_s is None and act.get("total_ms") is not None:
        act_s = round(_safe_float(act["total_ms"]) / 1000.0, 3)

    error_pct = None
    if pred_s is not None and act_s is not None and act_s > 0:
        error_pct = round(abs(pred_s - act_s) / act_s * 100.0, 1)

    return pred_s, act_s, error_pct


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
        pred_s, act_s, err_pct = extract_run_points(r)
        if pred_s is not None and act_s is not None and act_s > 0:
            error_pcts.append(err_pct)
            if pred_s < act_s:
                overrun_count += 1

        act = r.get("actual") or {}
        if act_s is not None:
            latencies.append(act_s)

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

    stage_medians: dict[str, float] = {}
    stage_p90s: dict[str, float] = {}
    for name, vals in [("load", load_vals), ("decode", decode_vals),
                       ("finalize", finalize_vals), ("insert", insert_vals)]:
        if vals:
            stage_medians[name] = round(statistics.median(vals), 3)
            stage_p90s[name] = _percentile(vals, 0.90)

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

    lines.append("")
    header = f"{'RUN_ID':<14} {'DATE/TIME':<20} {'AUDIO':>6} {'PRED':>6} {'ACTUAL':>6} {'ERR%':>6} {'STATUS':<8} {'L/D/F/I'}"
    lines.append(header)
    lines.append("─" * len(header))

    recent = records[-10:]
    for r in recent:
        run_id = str(r.get("run_id", ""))[:12]
        ts = r.get("ts_start") or r.get("ts_end") or 0.0
        dt_str = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)) if ts else "N/A"

        audio_s = _safe_float(r.get("audio_s"))
        pred_s, act_s, err_pct = extract_run_points(r)
        err_str = f"{err_pct:.1f}%" if err_pct is not None else "N/A"

        act = r.get("actual") or {}
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
# Fluid Responsive Inline SVG Charts (D-02, D-03, D-04, D-05)
# ---------------------------------------------------------------------------

def render_scatter_svg(records: list[dict], metrics: dict) -> str:
    """Predicted vs Actual scatter plot with 45° diagonal dashed line (D-02, D-03, D-05)."""
    w, h = 500, 320
    pad_l, pad_b, pad_t, pad_r = 50, 40, 20, 20
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    valid_pts = []
    for r in records:
        p, a, err = extract_run_points(r)
        if p is not None and a is not None and a > 0:
            valid_pts.append((p, a, err, str(r.get("run_id", ""))))

    max_val = 5.0
    if valid_pts:
        max_p = max(p for p, _, _, _ in valid_pts)
        max_a = max(a for _, a, _, _ in valid_pts)
        max_val = max(1.0, max(max_p, max_a))
    max_val = max(1.0, round(max_val * 1.1, 1))

    # Gridlines and axes
    elements = []
    for step in (0.25, 0.5, 0.75, 1.0):
        val = max_val * step
        x = pad_l + step * plot_w
        y = pad_t + plot_h - step * plot_h
        elements.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t + plot_h}" stroke="{COLOR_BORDER}" stroke-dasharray="2,2" opacity="0.4" />')
        elements.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" stroke="{COLOR_BORDER}" stroke-dasharray="2,2" opacity="0.4" />')
        elements.append(f'<text x="{x:.1f}" y="{pad_t + plot_h + 16}" fill="{COLOR_MUTED}" font-size="10" text-anchor="middle">{val:.1f}s</text>')
        elements.append(f'<text x="{pad_l - 8}" y="{y + 3:.1f}" fill="{COLOR_MUTED}" font-size="10" text-anchor="end">{val:.1f}s</text>')

    # 45-degree diagonal line: y = x (Ideal prediction)
    elements.append(
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" y2="{pad_t}" '
        f'stroke="#475569" stroke-dasharray="4,4" stroke-width="1.5">'
        f'<title>Ideal Prediction (1:1 diagonal)</title></line>'
    )

    # Data points
    for p, a, err, rid in valid_pts:
        cx = pad_l + (min(a, max_val) / max_val) * plot_w
        cy = pad_t + plot_h - (min(p, max_val) / max_val) * plot_h
        color = COLOR_GREEN if err < 15.0 else (COLOR_AMBER if err <= 30.0 else COLOR_CRIMSON)
        elements.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{color}" opacity="0.85" class="chart-dot">'
            f'<title>Run {html.escape(rid)}: Pred {p:.2f}s, Actual {a:.2f}s ({err:.1f}% error)</title>'
            f'</circle>'
        )

    # Axis titles
    elements.append(f'<text x="{pad_l + plot_w / 2}" y="{h - 6}" fill="{COLOR_MUTED}" font-size="11" text-anchor="middle">Actual Latency (s)</text>')
    elements.append(f'<text x="14" y="{pad_t + plot_h / 2}" fill="{COLOR_MUTED}" font-size="11" text-anchor="middle" transform="rotate(-90 14 {pad_t + plot_h / 2})">Predicted (s)</text>')

    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" '
        f'style="width: 100%; height: auto; max-width: 100%; display: block;">'
        f'{"".join(elements)}'
        f'</svg>'
    )


def render_trend_svg(records: list[dict], metrics: dict) -> str:
    """Error % Over Time trend curve with 15% and 30% reference lines (D-02, D-05)."""
    w, h = 500, 320
    pad_l, pad_b, pad_t, pad_r = 50, 40, 20, 20
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    pts = []
    for i, r in enumerate(records):
        _, _, err = extract_run_points(r)
        if err is not None:
            pts.append((str(r.get("run_id", f"run-{i}")), err))

    max_err = 50.0
    if pts:
        max_e = max(err for _, err in pts)
        max_err = max(50.0, max_e * 1.1)
    max_err = min(200.0, max_err)

    elements = []
    # Gridlines
    for step in (0.25, 0.5, 0.75, 1.0):
        val = max_err * step
        y = pad_t + plot_h - step * plot_h
        elements.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" stroke="{COLOR_BORDER}" stroke-dasharray="2,2" opacity="0.3" />')
        elements.append(f'<text x="{pad_l - 8}" y="{y + 3:.1f}" fill="{COLOR_MUTED}" font-size="10" text-anchor="end">{val:.0f}%</text>')

    # 15% and 30% tolerance threshold lines
    y_15 = pad_t + plot_h - (15.0 / max_err) * plot_h
    elements.append(
        f'<line x1="{pad_l}" y1="{y_15:.1f}" x2="{pad_l + plot_w}" y2="{y_15:.1f}" '
        f'stroke="{COLOR_GREEN}" stroke-dasharray="3,3" opacity="0.7">'
        f'<title>15% Tolerance Threshold</title></line>'
        f'<text x="{pad_l + plot_w - 4}" y="{y_15 - 4:.1f}" fill="{COLOR_GREEN}" font-size="10" text-anchor="end">15%</text>'
    )

    y_30 = pad_t + plot_h - (30.0 / max_err) * plot_h
    elements.append(
        f'<line x1="{pad_l}" y1="{y_30:.1f}" x2="{pad_l + plot_w}" y2="{y_30:.1f}" '
        f'stroke="{COLOR_AMBER}" stroke-dasharray="3,3" opacity="0.7">'
        f'<title>30% Warning Threshold</title></line>'
        f'<text x="{pad_l + plot_w - 4}" y="{y_30 - 4:.1f}" fill="{COLOR_AMBER}" font-size="10" text-anchor="end">30%</text>'
    )

    # Polyline and data points
    if pts:
        coords = []
        dots = []
        n = len(pts)
        for i, (rid, err) in enumerate(pts):
            cx = pad_l + (plot_w / 2 if n == 1 else (i / (n - 1)) * plot_w)
            cy = pad_t + plot_h - (min(err, max_err) / max_err) * plot_h
            coords.append(f"{cx:.1f},{cy:.1f}")
            color = COLOR_GREEN if err < 15.0 else (COLOR_AMBER if err <= 30.0 else COLOR_CRIMSON)
            dots.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.5" fill="{color}" class="chart-dot">'
                f'<title>Run {html.escape(rid)}: Error {err:.1f}%</title>'
                f'</circle>'
            )

        elements.append(f'<polyline points="{" ".join(coords)}" fill="none" stroke="#38bdf8" stroke-width="2" />')
        elements.extend(dots)

    elements.append(f'<text x="{pad_l + plot_w / 2}" y="{h - 6}" fill="{COLOR_MUTED}" font-size="11" text-anchor="middle">Chronological Runs</text>')
    elements.append(f'<text x="14" y="{pad_t + plot_h / 2}" fill="{COLOR_MUTED}" font-size="11" text-anchor="middle" transform="rotate(-90 14 {pad_t + plot_h / 2})">Error %</text>')

    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" '
        f'style="width: 100%; height: auto; max-width: 100%; display: block;">'
        f'{"".join(elements)}'
        f'</svg>'
    )


def render_histogram_svg(records: list[dict], metrics: dict) -> str:
    """Residual error |pred - actual| histogram across 8 bins (D-02, D-05)."""
    w, h = 500, 320
    pad_l, pad_b, pad_t, pad_r = 50, 40, 20, 20
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    bin_edges = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, float("inf")]
    bin_labels = ["0-0.25s", "0.25-0.5s", "0.5-0.75s", "0.75-1s", "1-1.5s", "1.5-2s", "2-3s", ">3s"]
    counts = [0] * len(bin_edges)

    for r in records:
        p, a, _ = extract_run_points(r)
        if p is not None and a is not None:
            residual = abs(p - a)
            for idx, edge in enumerate(bin_edges):
                if residual <= edge:
                    counts[idx] += 1
                    break

    max_c = max(1, max(counts))
    total_valid = sum(counts)
    elements = []

    # Y-axis ticks
    for step in (0.5, 1.0):
        val = int(max_c * step)
        y = pad_t + plot_h - step * plot_h
        elements.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" stroke="{COLOR_BORDER}" stroke-dasharray="2,2" opacity="0.3" />')
        elements.append(f'<text x="{pad_l - 8}" y="{y + 3:.1f}" fill="{COLOR_MUTED}" font-size="10" text-anchor="end">{val}</text>')

    bar_gap = 6
    num_bins = len(bin_labels)
    bar_w = (plot_w - (num_bins + 1) * bar_gap) / num_bins

    for idx, (label, count) in enumerate(zip(bin_labels, counts)):
        bx = pad_l + bar_gap + idx * (bar_w + bar_gap)
        bar_h = (count / max_c) * plot_h
        by = pad_t + plot_h - bar_h

        # 3-tier colors for residual magnitudes
        if idx < 2:
            color = COLOR_GREEN
        elif idx < 4:
            color = COLOR_AMBER
        else:
            color = COLOR_CRIMSON

        pct = (count / total_valid * 100.0) if total_valid > 0 else 0.0
        elements.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{color}" rx="3" opacity="0.85">'
            f'<title>Bin {label}: {count} runs ({pct:.1f}%)</title>'
            f'</rect>'
        )
        elements.append(
            f'<text x="{bx + bar_w / 2:.1f}" y="{pad_t + plot_h + 14}" fill="{COLOR_MUTED}" font-size="9" text-anchor="middle">{label}</text>'
        )

    elements.append(f'<text x="{pad_l + plot_w / 2}" y="{h - 6}" fill="{COLOR_MUTED}" font-size="11" text-anchor="middle">Residual Magnitude |Pred - Actual|</text>')
    elements.append(f'<text x="14" y="{pad_t + plot_h / 2}" fill="{COLOR_MUTED}" font-size="11" text-anchor="middle" transform="rotate(-90 14 {pad_t + plot_h / 2})">Runs</text>')

    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" '
        f'style="width: 100%; height: auto; max-width: 100%; display: block;">'
        f'{"".join(elements)}'
        f'</svg>'
    )


def render_stage_bars_svg(records: list[dict], metrics: dict) -> str:
    """Stacked bars decomposing latency into Load, Decode, Finalize, Insert stages."""
    w, h = 500, 320
    pad_l, pad_b, pad_t, pad_r = 75, 50, 30, 20
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    recent = records[-7:] if records else []
    elements = []

    # Legend at top
    legend_items = [
        ("Load", COLOR_LOAD),
        ("Decode", COLOR_DECODE),
        ("Finalize", COLOR_FINALIZE),
        ("Insert", COLOR_INSERT),
    ]
    lx = pad_l
    for label, col in legend_items:
        elements.append(f'<rect x="{lx}" y="8" width="10" height="10" fill="{col}" rx="2" />')
        elements.append(f'<text x="{lx + 14}" y="17" fill="{COLOR_MUTED}" font-size="10">{label}</text>')
        lx += 75

    if not recent:
        elements.append(f'<text x="{w / 2}" y="{h / 2}" fill="{COLOR_MUTED}" font-size="12" text-anchor="middle">No stage data available</text>')
        return f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" style="width: 100%; height: auto; max-width: 100%; display: block;">{"".join(elements)}</svg>'

    # Find max total latency among recent runs
    max_tot = 1.0
    for r in recent:
        act = r.get("actual") or {}
        tot = _safe_float(act.get("total_ms")) / 1000.0
        if tot > max_tot:
            max_tot = tot
    max_tot = max(1.0, round(max_tot * 1.1, 1))

    row_h = min(22.0, (plot_h - 10) / len(recent))
    for i, r in enumerate(recent):
        ry = pad_t + 10 + i * row_h
        act = r.get("actual") or {}
        run_id = str(r.get("run_id", f"run-{i}"))[:8]

        l_s = _safe_float(act.get("load_ms")) / 1000.0
        d_s = _safe_float(act.get("decode_ms")) / 1000.0
        f_s = _safe_float(act.get("finalize_ms")) / 1000.0
        i_s = _safe_float(act.get("insert_ms")) / 1000.0
        tot_s = l_s + d_s + f_s + i_s

        elements.append(f'<text x="{pad_l - 8}" y="{ry + row_h * 0.75:.1f}" fill="{COLOR_MUTED}" font-size="9" text-anchor="end">{html.escape(run_id)}</text>')

        cur_x = pad_l
        for duration, color, name in [
            (l_s, COLOR_LOAD, "Load"),
            (d_s, COLOR_DECODE, "Decode"),
            (f_s, COLOR_FINALIZE, "Finalize"),
            (i_s, COLOR_INSERT, "Insert"),
        ]:
            if duration > 0:
                seg_w = (duration / max_tot) * plot_w
                pct = (duration / tot_s * 100.0) if tot_s > 0 else 0.0
                elements.append(
                    f'<rect x="{cur_x:.1f}" y="{ry:.1f}" width="{seg_w:.1f}" height="{row_h - 4:.1f}" fill="{color}">'
                    f'<title>{name}: {duration:.2f}s ({pct:.0f}%)</title>'
                    f'</rect>'
                )
                cur_x += seg_w

        elements.append(f'<text x="{cur_x + 4:.1f}" y="{ry + row_h * 0.75:.1f}" fill="{COLOR_MUTED}" font-size="9">{tot_s:.2f}s</text>')

    elements.append(f'<text x="{pad_l + plot_w / 2}" y="{h - 10}" fill="{COLOR_MUTED}" font-size="11" text-anchor="middle">Stage Duration (s)</text>')

    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" '
        f'style="width: 100%; height: auto; max-width: 100%; display: block;">'
        f'{"".join(elements)}'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Visual Onboarding Empty State & Ghost Charts (D-08, RPT-03)
# ---------------------------------------------------------------------------

def render_ghost_charts_svg() -> str:
    """Renders dashed ghost chart outlines for visual onboarding (D-08, RPT-03)."""
    return (
        '<div class="ghost-grid">'
        '<div class="ghost-chart">'
        '<svg viewBox="0 0 500 240" style="width:100%;height:auto;display:block;">'
        '<rect x="20" y="20" width="460" height="200" fill="none" stroke="#334155" stroke-dasharray="6,6" rx="8" />'
        '<line x1="60" y1="180" x2="440" y2="60" stroke="#334155" stroke-dasharray="4,4" opacity="0.5" />'
        '<text x="250" y="115" fill="#64748b" font-size="14" text-anchor="middle">Predicted vs Actual Latency</text>'
        '<text x="250" y="140" fill="#475569" font-size="12" text-anchor="middle">Populates after your first dictation</text>'
        '</svg>'
        '</div>'
        '<div class="ghost-chart">'
        '<svg viewBox="0 0 500 240" style="width:100%;height:auto;display:block;">'
        '<rect x="20" y="20" width="460" height="200" fill="none" stroke="#334155" stroke-dasharray="6,6" rx="8" />'
        '<line x1="60" y1="140" x2="440" y2="140" stroke="#334155" stroke-dasharray="4,4" opacity="0.5" />'
        '<text x="250" y="115" fill="#64748b" font-size="14" text-anchor="middle">Error % Over Time</text>'
        '<text x="250" y="140" fill="#475569" font-size="12" text-anchor="middle">Tracks calibration convergence</text>'
        '</svg>'
        '</div>'
        '</div>'
    )


def render_empty_state_card() -> str:
    """Visual onboarding card explaining calibration and prompting shortcut (D-08)."""
    ghost = render_ghost_charts_svg()
    return f"""
    <div class="empty-state">
      <div class="onboarding-card">
        <h2>No recordings yet</h2>
        <p class="onboarding-desc">
          Voicemode predicts transcription latency locally using online calibration.
          As you speak, predictions adapt to your hardware across 3 confidence tiers:
          <strong>Prior &rarr; L0 (audio duration) &rarr; L1 (device) &rarr; L2 (model & compute type)</strong>.
        </p>
        <div class="shortcut-box">
          Press <kbd>SUPER+SHIFT+M</kbd> to record your first dictation
        </div>
      </div>
      {ghost}
    </div>
    """


# ---------------------------------------------------------------------------
# Privacy Footer (D-07, RPT-03)
# ---------------------------------------------------------------------------

def render_privacy_footer(metrics_path: Optional[Path] = None, skipped_count: int = 0) -> str:
    """Renders structured 4-subpanel privacy card with explicit purge commands (D-07)."""
    if metrics_path is None:
        metrics_path = voicemode_telemetry.get_ledger_path()
    path_str = html.escape(str(metrics_path))

    warning_html = ""
    if skipped_count > 0:
        warning_html = (
            f'<div class="corrupt-warning">'
            f'⚠️ {skipped_count} row(s) skipped due to parse errors.'
            f'</div>'
        )

    return f"""
    <div class="privacy-card">
      <div class="privacy-header">
        <h3>Privacy & Telemetry Baseline</h3>
        <span class="privacy-badge">Local Only • Zero Network</span>
      </div>
      <div class="privacy-grid">
        <div class="privacy-subpanel">
          <h4>1. Local Storage Location</h4>
          <code>{path_str}</code>
          <p>Data is stored locally on this machine. Never synced or transmitted anywhere.</p>
        </div>
        <div class="privacy-subpanel">
          <h4>2. Retained Schema</h4>
          <p>Only timings, stage latencies, model parameters, and character counts are stored. Audio buffers, prompts, hotwords, and transcript text are never recorded.</p>
        </div>
        <div class="privacy-subpanel">
          <h4>3. Clipboard Caveat</h4>
          <p>Transcript insertion simulates native Wayland keystrokes or uses system clipboard paste. Active clipboard text is never logged or stored in telemetry.</p>
        </div>
        <div class="privacy-subpanel">
          <h4>4. Purge & Reset</h4>
          <p>To purge all history:</p>
          <code>rm {path_str}</code>
          <p style="margin-top:8px;">To reset calibration to priors:</p>
          <code>voice --reset-calibration</code>
        </div>
      </div>
      {warning_html}
    </div>
    """


# ---------------------------------------------------------------------------
# Recent Runs Table (D-06, D-05)
# ---------------------------------------------------------------------------

def render_runs_table(records: list[dict]) -> str:
    """Renders recent runs table (up to 200, 25 visible, CSS scrollable) with 3-tier badges."""
    if not records:
        return '<div class="table-empty">No runs recorded yet. Dictate your first sentence to populate this ledger.</div>'

    rows_html = []
    for r in reversed(records[-200:]):
        run_id = html.escape(str(r.get("run_id", ""))[:12])
        ts = r.get("ts_start") or r.get("ts_end") or 0.0
        dt_str = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)) if ts else "N/A"

        cfg = r.get("config") or {}
        model = html.escape(str(cfg.get("model", "unknown")))
        audio_s = _safe_float(r.get("audio_s"))

        pred_s, act_s, err_pct = extract_run_points(r)
        if err_pct is not None:
            if err_pct < 15.0:
                badge_cls = "badge-green"
            elif err_pct <= 30.0:
                badge_cls = "badge-amber"
            else:
                badge_cls = "badge-crimson"
            err_badge = f'<span class="badge {badge_cls}">{err_pct:.1f}%</span>'
        else:
            err_badge = '<span class="badge badge-muted">N/A</span>'

        outcome = html.escape(str(r.get("outcome", "unknown")))
        act = r.get("actual") or {}
        load_s = _safe_float(act.get("load_ms")) / 1000.0 if act.get("load_ms") is not None else 0.0
        decode_s = _safe_float(act.get("decode_ms")) / 1000.0 if act.get("decode_ms") is not None else 0.0
        fin_s = _safe_float(act.get("finalize_ms")) / 1000.0 if act.get("finalize_ms") is not None else 0.0
        ins_s = _safe_float(act.get("insert_ms")) / 1000.0 if act.get("insert_ms") is not None else 0.0

        p_str = f"{pred_s:.2f}s" if pred_s is not None else "-"
        a_str = f"{act_s:.2f}s" if act_s is not None else "-"

        rows_html.append(
            f'<tr>'
            f'<td><code>{run_id}</code></td>'
            f'<td>{dt_str}</td>'
            f'<td>{model}</td>'
            f'<td>{audio_s:.1f}s</td>'
            f'<td>{p_str}</td>'
            f'<td>{a_str}</td>'
            f'<td>{err_badge}</td>'
            f'<td><small>{load_s:.2f}/{decode_s:.2f}/{fin_s:.2f}/{ins_s:.2f}</small></td>'
            f'<td>{outcome}</td>'
            f'</tr>'
        )

    return f"""
    <div class="runs-table-container">
      <table class="runs-table">
        <thead>
          <tr>
            <th>Run ID</th>
            <th>Date/Time</th>
            <th>Model</th>
            <th>Audio</th>
            <th>Predicted</th>
            <th>Actual</th>
            <th>Error%</th>
            <th>Stages (L/D/F/I)</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {"".join(rows_html)}
        </tbody>
      </table>
    </div>
    """


# ---------------------------------------------------------------------------
# Standalone HTML Document Generator (D-01, D-02, D-03, RPT-02)
# ---------------------------------------------------------------------------

CSS_STYLES = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0f172a;
  color: #f8fafc;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  padding: 24px;
  line-height: 1.5;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #334155;
}
.header h1 { font-size: 1.5rem; font-weight: 700; color: #f8fafc; }
.header .tagline { font-size: 0.875rem; color: #94a3b8; }
.hero-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 16px 20px;
}
.hero-card .label { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.05em; }
.hero-card .value { font-size: 1.75rem; font-weight: 700; margin-top: 4px; color: #f8fafc; }
.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}
.chart-card h3 { font-size: 0.95rem; font-weight: 600; margin-bottom: 12px; color: #cbd5e1; }
.chart-dot:hover { r: 6; stroke: #ffffff; stroke-width: 1.5; opacity: 1; }
.runs-table-container {
  max-height: 700px;
  overflow-y: auto;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #1e293b;
  margin-bottom: 24px;
}
.runs-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.runs-table th {
  position: sticky;
  top: 0;
  background: #1e293b;
  color: #94a3b8;
  text-align: left;
  padding: 10px 14px;
  border-bottom: 1px solid #334155;
  font-weight: 600;
}
.runs-table td { padding: 8px 14px; border-bottom: 1px solid #1e293b; color: #cbd5e1; }
.runs-table tr:hover td { background: rgba(51, 65, 85, 0.4); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.75rem; }
.badge-green { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.badge-amber { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.badge-crimson { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.badge-muted { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }
.privacy-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 20px;
  margin-top: 32px;
}
.privacy-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.privacy-header h3 { font-size: 1rem; color: #f8fafc; }
.privacy-badge { background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 0.75rem; padding: 3px 8px; border-radius: 4px; font-weight: 600; }
.privacy-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
.privacy-subpanel h4 { font-size: 0.85rem; color: #e2e8f0; margin-bottom: 6px; }
.privacy-subpanel p { font-size: 0.8rem; color: #94a3b8; margin-top: 4px; }
.privacy-subpanel code { font-size: 0.75rem; background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #cbd5e1; word-break: break-all; }
.corrupt-warning { margin-top: 16px; padding: 8px 12px; background: rgba(245, 158, 11, 0.15); color: #f59e0b; border-radius: 6px; font-size: 0.8rem; }
.empty-state { text-align: center; margin: 32px 0; }
.onboarding-card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 32px; max-width: 680px; margin: 0 auto 32px; }
.onboarding-card h2 { font-size: 1.4rem; margin-bottom: 12px; color: #f8fafc; }
.onboarding-desc { color: #94a3b8; font-size: 0.95rem; margin-bottom: 20px; line-height: 1.6; }
.shortcut-box { display: inline-block; background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 10px 18px; font-size: 0.9rem; color: #38bdf8; }
.shortcut-box kbd { background: #334155; color: #f8fafc; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.85rem; }
.ghost-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 20px; margin-top: 24px; }
.ghost-chart { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; }
.table-empty { text-align: center; padding: 32px; color: #94a3b8; font-size: 0.9rem; }
"""


def render_html_report(
    records: list[dict],
    metrics: dict,
    skipped_count: int = 0,
    metrics_path: Optional[Path] = None,
) -> str:
    """Generates the self-contained, zero-JavaScript dark HTML dashboard (D-01, D-02, D-03, RPT-02)."""
    total = metrics.get("total_runs", 0)
    med_err = metrics.get("median_error_pct")
    p90 = metrics.get("p90_latency_s")
    cal_tier = metrics.get("calibration_tier", "prior")

    med_str = f"{med_err:.1f}%" if med_err is not None else "N/A"
    p90_str = f"{p90:.2f}s" if p90 is not None else "N/A"

    hero_cards_html = f"""
    <div class="hero-grid">
      <div class="card hero-card">
        <div class="label">Total Runs</div>
        <div class="value">{total}</div>
      </div>
      <div class="card hero-card">
        <div class="label">Median Error</div>
        <div class="value">{med_str}</div>
      </div>
      <div class="card hero-card">
        <div class="label">P90 Latency</div>
        <div class="value">{p90_str}</div>
      </div>
      <div class="card hero-card">
        <div class="label">Calibration Tier</div>
        <div class="value">{html.escape(cal_tier)}</div>
      </div>
    </div>
    """

    if total == 0:
        main_content = render_empty_state_card()
    else:
        scatter_svg = render_scatter_svg(records, metrics)
        trend_svg = render_trend_svg(records, metrics)
        hist_svg = render_histogram_svg(records, metrics)
        stage_svg = render_stage_bars_svg(records, metrics)

        charts_html = f"""
        <div class="chart-grid">
          <div class="card chart-card">
            <h3>Predicted vs Actual Latency (1:1 Diagonal)</h3>
            {scatter_svg}
          </div>
          <div class="card chart-card">
            <h3>Error % Over Time (Tolerance Thresholds)</h3>
            {trend_svg}
          </div>
          <div class="card chart-card">
            <h3>Residual Error Distribution |Pred - Actual|</h3>
            {hist_svg}
          </div>
          <div class="card chart-card">
            <h3>Stage Timing Breakdown (Load / Decode / Finalize / Insert)</h3>
            {stage_svg}
          </div>
        </div>
        """
        table_html = render_runs_table(records)
        main_content = f"{charts_html}\n{table_html}"

    privacy_html = render_privacy_footer(metrics_path=metrics_path, skipped_count=skipped_count)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Voicemode Accuracy Report</title>
  <style>
{CSS_STYLES}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>Voicemode Accuracy Report</h1>
      <div class="tagline">Local Telemetry & Calibration Dashboard • Arch Linux / Hyprland</div>
    </div>
  </div>
  {hero_cards_html}
  {main_content}
  {privacy_html}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Pre-Render Hook (D-18, D-19, D-20)
# ---------------------------------------------------------------------------

def generate_prerendered_report(dest_path: Optional[Path] = None) -> Path:
    """Pre-renders report.html for the last 200 runs and atomically writes to disk (D-18, D-19)."""
    if dest_path is None:
        dest_path = voicemode_telemetry.get_state_dir() / "report.html"

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


# ---------------------------------------------------------------------------
# Secure Browser Launch (D-24, RPT-06)
# ---------------------------------------------------------------------------

def open_report_file(path: Path | str, args: Optional[argparse.Namespace] = None) -> bool:
    """Strictly validates target path before executing xdg-open with notification fallback (D-24, RPT-06)."""
    if not path:
        msg = "Report file not specified"
        print(msg, file=sys.stderr, flush=True)
        try:
            from voice import notify
            notify("Voice Report", msg, args)
        except Exception:
            pass
        return False

    try:
        target = Path(path).resolve()
    except Exception as exc:
        msg = f"Invalid report path: {exc}"
        print(msg, file=sys.stderr, flush=True)
        try:
            from voice import notify
            notify("Voice Report", msg, args)
        except Exception:
            pass
        return False

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

    if not target.is_file():
        msg = f"Report file not found: {target}"
        print(msg, file=sys.stderr, flush=True)
        try:
            from voice import notify
            notify("Voice Report", f"Report file not found: {target}", args)
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
            content = render_html_report(filtered, metrics, skipped_count)
        else:
            content = render_terminal_summary(filtered, metrics, skipped_count)

        if output_path:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(content, encoding="utf-8")
            print(f"Report written to {out_p}", flush=True)
        else:
            print(content, flush=True)

        if getattr(args, "open", False):
            if output_path and fmt == "html":
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
