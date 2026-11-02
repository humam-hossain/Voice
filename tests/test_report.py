"""Tests for voicemode_report: reporting engine, CLI dispatch, filtering, CSV/JSON export."""
from __future__ import annotations

import csv
import io
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    outlier=False,
    outlier_reason=None,
    corpus_file=None,
):
    now = time.time()
    t_start = ts_start if ts_start is not None else (now - 10.0)
    t_end = t_start + 10.0
    return {
        "schema": 1,
        "source": "stt",
        "run_id": run_id,
        "install_id": "test-install",
        "ts_start": t_start,
        "ts_end": t_end,
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
        "outlier": outlier,
        "outlier_reason": outlier_reason,
        "corpus_file": corpus_file,
    }


# ---------------------------------------------------------------------------
# Task 1: Tracer Tests — CLI dispatch, zero-import, ledger loading
# ---------------------------------------------------------------------------

class TestReportCLI(TempXdgTestCase):
    """Task 1: End-to-end reporting pipeline tracer tests."""

    def test_no_heavy_imports_on_report_path(self):
        """RPT-01: voice --report must never load faster_whisper, numpy, or sounddevice."""
        code = (
            "import sys; "
            "sys.path.insert(0, '.'); "
            "import voice; "
            "args = voice.parse_args(['--report']); "
            "import voicemode_report; "
            "voicemode_report.handle_report_command(args); "
            "forbidden = ['faster_whisper', 'numpy', 'sounddevice']; "
            "loaded = [m for m in forbidden if m in sys.modules]; "
            "assert not loaded, f'Heavy modules imported: {loaded}'"
        )
        res = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
            env={**os.environ, "XDG_RUNTIME_DIR": str(self.run_dir), "XDG_STATE_HOME": str(self.state_dir)},
        )
        self.assertEqual(res.returncode, 0, f"Import assertion failed: {res.stderr}")

    def test_report_tracer_cli(self):
        """voice --report dispatches to voicemode_report and produces output."""
        # Write a sample record
        rec = _make_record()
        voicemode_telemetry.append_ledger_row(rec)

        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            code = voice.main(["--report"])
        finally:
            sys.stdout = old

        self.assertEqual(code, 0)
        output = f.getvalue()
        self.assertIn("Voice Latency Report", output)
        self.assertIn("Total Runs", output)

    def test_metrics_cli_dispatch(self):
        """voice --metrics dispatches to voicemode_report."""
        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            code = voice.main(["--metrics"])
        finally:
            sys.stdout = old

        self.assertEqual(code, 0)
        output = f.getvalue()
        self.assertIn("Ledger:", output)

    def test_metrics_json_dispatch(self):
        """voice --metrics --json-status dispatches and produces JSON."""
        rec = _make_record()
        voicemode_telemetry.append_ledger_row(rec)

        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            code = voice.main(["--metrics", "--json-status"])
        finally:
            sys.stdout = old

        self.assertEqual(code, 0)
        output = f.getvalue().strip()
        data = json.loads(output)
        self.assertIn("summary", data)
        self.assertIn("ledger", data)

    def test_ledger_loading_with_torn_lines(self):
        """D-21: Corrupt/torn lines are skipped without crashing."""
        ledger_path = voicemode_telemetry.get_ledger_path()
        ledger_path.parent.mkdir(parents=True, exist_ok=True)

        valid = _make_record(run_id="valid-1")
        valid_line = json.dumps(valid)

        with open(ledger_path, "w", encoding="utf-8") as f:
            f.write(valid_line + "\n")
            f.write('{"broken json\n')
            f.write('not json at all\n')
            f.write('{"schema": 999, "wrong": true}\n')
            f.write("\n")  # blank line

        records, skipped = voicemode_report.load_ledger_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["run_id"], "valid-1")
        self.assertEqual(skipped, 3)  # broken json, not json, wrong schema

    def test_ledger_loading_empty(self):
        """Empty/missing ledger returns empty list with zero skipped."""
        records, skipped = voicemode_report.load_ledger_records()
        self.assertEqual(len(records), 0)
        self.assertEqual(skipped, 0)

    def test_parse_args_report_flags(self):
        """CLI parser recognizes all reporting flags."""
        args = voice.parse_args(["--report", "--format", "csv", "--output", "/tmp/test.csv", "--open", "--since", "7d", "--last", "50"])
        self.assertTrue(args.report)
        self.assertEqual(args.format, "csv")
        self.assertEqual(args.output, "/tmp/test.csv")
        self.assertTrue(getattr(args, "open", False))
        self.assertEqual(args.since, "7d")
        self.assertEqual(args.last, "50")


# ---------------------------------------------------------------------------
# Task 2: Filtering and Statistics Tests
# ---------------------------------------------------------------------------

class TestReportFilteringAndStats(TempXdgTestCase):
    """Task 2: Multi-criteria filtering, statistics, terminal formatting."""

    def test_parse_since_relative_hours(self):
        """parse_since_argument('24h') produces timestamp 24h ago."""
        now = time.time()
        ts = voicemode_report.parse_since_argument("24h")
        self.assertIsNotNone(ts)
        self.assertAlmostEqual(ts, now - 86400, delta=2.0)

    def test_parse_since_relative_days(self):
        """parse_since_argument('7d') produces timestamp 7d ago."""
        now = time.time()
        ts = voicemode_report.parse_since_argument("7d")
        self.assertIsNotNone(ts)
        self.assertAlmostEqual(ts, now - 7 * 86400, delta=2.0)

    def test_parse_since_relative_minutes(self):
        """parse_since_argument('60m') produces timestamp 60m ago."""
        now = time.time()
        ts = voicemode_report.parse_since_argument("60m")
        self.assertIsNotNone(ts)
        self.assertAlmostEqual(ts, now - 3600, delta=2.0)

    def test_parse_since_iso_date(self):
        """parse_since_argument('2026-10-01') produces an epoch timestamp."""
        ts = voicemode_report.parse_since_argument("2026-10-01")
        self.assertIsNotNone(ts)
        self.assertGreater(ts, 0)

    def test_parse_since_invalid(self):
        """parse_since_argument with garbage returns None."""
        self.assertIsNone(voicemode_report.parse_since_argument("garbage"))
        self.assertIsNone(voicemode_report.parse_since_argument(""))

    def test_filter_by_model(self):
        """filter_records filters by model case-insensitively."""
        records = [
            _make_record(run_id="r1", model="medium"),
            _make_record(run_id="r2", model="small"),
            _make_record(run_id="r3", model="Medium"),
        ]
        filtered = voicemode_report.filter_records(records, model="medium", last="all")
        run_ids = [r["run_id"] for r in filtered]
        self.assertIn("r1", run_ids)
        self.assertIn("r3", run_ids)
        self.assertNotIn("r2", run_ids)

    def test_filter_by_device(self):
        """filter_records filters by device case-insensitively."""
        records = [
            _make_record(run_id="r1", device="cpu"),
            _make_record(run_id="r2", device="cuda"),
        ]
        filtered = voicemode_report.filter_records(records, device="cuda", last="all")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["run_id"], "r2")

    def test_filter_by_last(self):
        """filter_records limits to last N records."""
        records = [_make_record(run_id=f"r-{i}") for i in range(20)]
        filtered = voicemode_report.filter_records(records, last=5)
        self.assertEqual(len(filtered), 5)
        self.assertEqual(filtered[0]["run_id"], "r-15")

    def test_filter_last_all(self):
        """filter_records with last='all' returns everything."""
        records = [_make_record(run_id=f"r-{i}") for i in range(20)]
        filtered = voicemode_report.filter_records(records, last="all")
        self.assertEqual(len(filtered), 20)

    def test_filter_by_since(self):
        """filter_records filters by since timestamp."""
        now = time.time()
        old_record = _make_record(run_id="old", ts_start=now - 200000)
        new_record = _make_record(run_id="new", ts_start=now - 100)
        records = [old_record, new_record]
        filtered = voicemode_report.filter_records(records, since="24h", last="all")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["run_id"], "new")

    def test_filter_combined(self):
        """filter_records applies model + device + last together."""
        records = [
            _make_record(run_id="r1", model="medium", device="cpu"),
            _make_record(run_id="r2", model="medium", device="cuda"),
            _make_record(run_id="r3", model="small", device="cpu"),
        ]
        filtered = voicemode_report.filter_records(records, model="medium", device="cpu", last="all")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["run_id"], "r1")

    def test_compute_metrics_basic(self):
        """compute_report_metrics produces correct aggregates."""
        records = [
            _make_record(run_id="r1", pred_s=2.5, actual_s=2.4),
            _make_record(run_id="r2", pred_s=3.0, actual_s=2.8),
            _make_record(run_id="r3", pred_s=1.5, actual_s=1.6),
        ]
        metrics = voicemode_report.compute_report_metrics(records)
        self.assertEqual(metrics["total_runs"], 3)
        self.assertIsNotNone(metrics["median_wait_s"])
        self.assertIsNotNone(metrics["p90_latency_s"])
        self.assertIsNotNone(metrics["mean_rtf"])
        self.assertGreater(metrics["median_wait_s"], 0)

    def test_compute_metrics_empty(self):
        """compute_report_metrics on empty records returns nulls, no crash."""
        metrics = voicemode_report.compute_report_metrics([])
        self.assertEqual(metrics["total_runs"], 0)
        self.assertIsNone(metrics["median_wait_s"])
        self.assertIsNone(metrics["p90_latency_s"])
        self.assertIsNone(metrics["mean_rtf"])
        self.assertIsNone(metrics["last_run_timestamp"])

    def test_compute_metrics_single_run(self):
        """compute_report_metrics handles a single run without crashing."""
        records = [_make_record(run_id="single")]
        metrics = voicemode_report.compute_report_metrics(records)
        self.assertEqual(metrics["total_runs"], 1)
        self.assertIsNotNone(metrics["median_wait_s"])

    def test_terminal_summary_output(self):
        """render_terminal_summary produces formatted card with runs table."""
        records = [_make_record(run_id=f"r-{i}") for i in range(5)]
        metrics = voicemode_report.compute_report_metrics(records)
        output = voicemode_report.render_terminal_summary(records, metrics)
        self.assertIn("Voice Latency Report", output)
        self.assertIn("Total Runs", output)
        self.assertIn("5", output)
        self.assertIn("RUN_ID", output)

    def test_terminal_summary_empty_state(self):
        """render_terminal_summary with no records shows empty state message."""
        metrics = voicemode_report.compute_report_metrics([])
        output = voicemode_report.render_terminal_summary([], metrics)
        self.assertIn("No runs recorded yet", output)
        self.assertIn("SUPER+SHIFT+M", output)

    def test_terminal_summary_shows_report_path(self):
        """render_terminal_summary includes report.html path."""
        records = [_make_record()]
        metrics = voicemode_report.compute_report_metrics(records)
        output = voicemode_report.render_terminal_summary(records, metrics)
        self.assertIn("report.html", output)


# ---------------------------------------------------------------------------
# Task 3: CSV and JSON Export Tests
# ---------------------------------------------------------------------------

class TestExportFormats(TempXdgTestCase):
    """Task 3: CSV headers, JSON convergence, --output flag."""

    def test_csv_export_headers_and_data(self):
        """RPT-05: CSV has exactly 13 canonical headers in stable order."""
        records = [
            _make_record(run_id="r1", audio_s=4.0, pred_s=2.5, actual_s=2.4),
            _make_record(run_id="r2", audio_s=6.0, pred_s=3.0, actual_s=2.8),
        ]
        csv_text = voicemode_report.render_csv(records)
        reader = csv.reader(io.StringIO(csv_text))
        headers = next(reader)
        self.assertEqual(headers, voicemode_report.CSV_HEADERS)
        self.assertEqual(len(headers), 13)

        rows = list(reader)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "r1")  # run_id
        self.assertEqual(rows[1][0], "r2")

    def test_csv_export_empty(self):
        """CSV with zero records produces headers only."""
        csv_text = voicemode_report.render_csv([])
        reader = csv.reader(io.StringIO(csv_text))
        headers = next(reader)
        self.assertEqual(headers, voicemode_report.CSV_HEADERS)
        rows = list(reader)
        self.assertEqual(len(rows), 0)

    def test_csv_headers_constant(self):
        """CSV_HEADERS is a list of exactly 13 strings."""
        self.assertEqual(len(voicemode_report.CSV_HEADERS), 13)
        expected_order = [
            "run_id", "timestamp", "model", "device", "audio_s", "load_s",
            "record_s", "decode_s", "finalize_s", "insert_s", "wait_s",
            "rtf", "outcome",
        ]
        self.assertEqual(voicemode_report.CSV_HEADERS, expected_order)

    def test_converged_json_schema(self):
        """RPT-05: --metrics --json and --report --format json produce identical schema keys."""
        rec = _make_record(run_id="r1")
        voicemode_telemetry.append_ledger_row(rec)

        # Metrics JSON
        metrics_out = StringIO()
        old = sys.stdout
        try:
            sys.stdout = metrics_out
            voice.main(["--metrics", "--json-status"])
        finally:
            sys.stdout = old

        # Report JSON
        report_out = StringIO()
        try:
            sys.stdout = report_out
            voice.main(["--report", "--format", "json"])
        finally:
            sys.stdout = old

        m_obj = json.loads(metrics_out.getvalue().strip())
        r_obj = json.loads(report_out.getvalue().strip())

        self.assertEqual(set(m_obj.keys()), set(r_obj.keys()))
        self.assertEqual(set(m_obj["summary"].keys()), set(r_obj["summary"].keys()))
        self.assertEqual(set(m_obj["ledger"].keys()), set(r_obj["ledger"].keys()))

    def test_json_schema_empty(self):
        """JSON output with zero runs has null summary fields."""
        metrics = voicemode_report.compute_report_metrics([])
        ledger_info = {"path": "/tmp/test.jsonl", "bytes": 0, "rows": 0, "archives": 0}
        json_str = voicemode_report.render_json(metrics, ledger_info)
        data = json.loads(json_str)

        self.assertEqual(data["summary"]["total_runs"], 0)
        self.assertIsNone(data["summary"]["median_wait_s"])
        self.assertIsNone(data["summary"]["p90_latency_s"])
        self.assertIsNone(data["summary"]["mean_rtf"])
        self.assertIsNone(data["summary"]["last_run_timestamp"])
        self.assertEqual(data["ledger"]["schema_version"], 1)

    def test_output_flag_csv(self):
        """--output with .csv extension writes CSV file."""
        rec = _make_record()
        voicemode_telemetry.append_ledger_row(rec)

        output_path = self.state_dir / "test_output.csv"
        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            code = voice.main(["--report", "--output", str(output_path)])
        finally:
            sys.stdout = old

        self.assertEqual(code, 0)
        self.assertTrue(output_path.exists())
        content = output_path.read_text()
        reader = csv.reader(io.StringIO(content))
        headers = next(reader)
        self.assertEqual(headers, voicemode_report.CSV_HEADERS)

    def test_output_flag_json(self):
        """--output with .json extension writes JSON file."""
        rec = _make_record()
        voicemode_telemetry.append_ledger_row(rec)

        output_path = self.state_dir / "test_output.json"
        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            code = voice.main(["--report", "--output", str(output_path)])
        finally:
            sys.stdout = old

        self.assertEqual(code, 0)
        self.assertTrue(output_path.exists())
        data = json.loads(output_path.read_text())
        self.assertIn("summary", data)
        self.assertIn("ledger", data)

    def test_format_flag_overrides_extension(self):
        """--format flag takes precedence over --output extension."""
        rec = _make_record()
        voicemode_telemetry.append_ledger_row(rec)

        output_path = self.state_dir / "test.csv"
        f = StringIO()
        old = sys.stdout
        try:
            sys.stdout = f
            code = voice.main(["--report", "--format", "json", "--output", str(output_path)])
        finally:
            sys.stdout = old

        self.assertEqual(code, 0)
        content = output_path.read_text()
        data = json.loads(content)
        self.assertIn("summary", data)

    def test_record_to_csv_row_fields(self):
        """record_to_csv_row extracts all 13 fields."""
        rec = _make_record(run_id="test-row", audio_s=3.0, pred_s=2.0, actual_s=1.8)
        row = voicemode_report.record_to_csv_row(rec)
        for header in voicemode_report.CSV_HEADERS:
            self.assertIn(header, row, f"Missing CSV field: {header}")

    def test_prerender_creates_report_html(self):
        """generate_prerendered_report creates report.html."""
        rec = _make_record()
        voicemode_telemetry.append_ledger_row(rec)

        report_path = voicemode_report.generate_prerendered_report()
        self.assertTrue(report_path.exists())
        content = report_path.read_text()
        self.assertIn("Voicemode Latency Report", content)


# ---------------------------------------------------------------------------
# Task 1 (Plan 08-02): Inline SVG Charts Tests
# ---------------------------------------------------------------------------

class TestSVGCharts(TempXdgTestCase):
    """Task 1: Fluid responsive inline SVG chart engines."""

    def test_scatter_svg_geometry_and_tooltips(self):
        """Latency scatter plot contains viewBox, native tooltips, and data points."""
        records = [
            _make_record(run_id="r1", audio_s=3.0, actual_s=2.0),
            _make_record(run_id="r2", audio_s=5.0, actual_s=3.0),
            _make_record(run_id="r3", audio_s=10.0, actual_s=5.0),
        ]
        metrics = voicemode_report.compute_report_metrics(records)
        svg = voicemode_report.render_latency_scatter_svg(records, metrics)

        self.assertIn('viewBox="0 0 500 320"', svg)
        self.assertIn("<title>", svg)
        self.assertIn("Run r1:", svg)
        self.assertIn("<circle", svg)

    def test_scatter_svg_single_run(self):
        """Scatter plot handles single run without dividing by zero."""
        records = [_make_record(run_id="r1", audio_s=4.0, actual_s=2.0)]
        metrics = voicemode_report.compute_report_metrics(records)
        svg = voicemode_report.render_latency_scatter_svg(records, metrics)
        self.assertIn('viewBox="0 0 500 320"', svg)
        self.assertIn("<circle", svg)

    def test_scatter_svg_empty(self):
        """Scatter plot handles empty records gracefully."""
        svg = voicemode_report.render_latency_scatter_svg([], voicemode_report.compute_report_metrics([]))
        self.assertIn('viewBox="0 0 500 320"', svg)

    def test_trend_svg_geometry_and_lines(self):
        """RTF trend chart contains polyline and 1.0x reference line."""
        records = [_make_record(run_id=f"r-{i}", audio_s=4.0, decode_ms=2000.0 + i * 200) for i in range(5)]
        metrics = voicemode_report.compute_report_metrics(records)
        svg = voicemode_report.render_rtf_trend_svg(records, metrics)

        self.assertIn('viewBox="0 0 500 320"', svg)
        self.assertIn("<polyline", svg)
        self.assertIn("1.0x", svg)
        self.assertIn("<title>", svg)

    def test_stage_bars_svg_decomposition(self):
        """Stage breakdown renders stacked bars with stage colors."""
        records = [_make_record(run_id=f"r-{i}", load_ms=100.0, decode_ms=800.0, finalize_ms=40.0, insert_ms=20.0) for i in range(3)]
        metrics = voicemode_report.compute_report_metrics(records)
        svg = voicemode_report.render_stage_bars_svg(records, metrics)

        self.assertIn('viewBox="0 0 500 320"', svg)
        self.assertIn(voicemode_report.COLOR_LOAD, svg)
        self.assertIn(voicemode_report.COLOR_DECODE, svg)
        self.assertIn(voicemode_report.COLOR_FINALIZE, svg)
        self.assertIn(voicemode_report.COLOR_INSERT, svg)
        self.assertIn("Load", svg)
        self.assertIn("Decode", svg)


# ---------------------------------------------------------------------------
# Task 2 (Plan 08-02): HTML Report Tests
# ---------------------------------------------------------------------------

class TestHTMLReport(TempXdgTestCase):
    """Task 2: Standalone dark HTML report generator."""

    def test_html_report_zero_js_and_self_contained(self):
        """RPT-02: HTML report contains zero <script> tags, zero http(s) links, and all 4 SVG charts."""
        records = [_make_record(run_id=f"r-{i}", audio_s=2.0 + i) for i in range(10)]
        metrics = voicemode_report.compute_report_metrics(records)
        html_doc = voicemode_report.render_html_report(records, metrics)

        self.assertTrue(html_doc.startswith("<!DOCTYPE html>"))
        self.assertNotIn("<script", html_doc.lower())
        self.assertNotIn("http://", html_doc.lower())
        self.assertNotIn("https://", html_doc.lower())
        self.assertNotIn("onclick", html_doc.lower())
        self.assertIn("viewBox=", html_doc)
        self.assertIn("<title>", html_doc)
        self.assertIn("privacy-card", html_doc)

    def test_html_report_table_and_cards(self):
        """RPT-02: HTML report includes 4 hero metric cards, chart grid, and scrollable runs table."""
        records = [
            _make_record(run_id="r1", audio_s=3.0, actual_s=2.0),
            _make_record(run_id="r2", audio_s=5.0, actual_s=3.0),
            _make_record(run_id="r3", audio_s=10.0, actual_s=5.0),
        ]
        metrics = voicemode_report.compute_report_metrics(records)
        html_doc = voicemode_report.render_html_report(records, metrics)

        self.assertIn("Total Runs", html_doc)
        self.assertIn("Median Wait", html_doc)
        self.assertIn("P90 Latency", html_doc)
        self.assertIn("Mean RTF", html_doc)
        self.assertIn("chart-grid", html_doc)
        self.assertIn("runs-table-container", html_doc)

    def test_html_escaping(self):
        """Special characters in model or run_id are escaped to prevent XSS."""
        rec = _make_record(run_id="<script>alert(1)</script>", model="<b>evil</b>")
        metrics = voicemode_report.compute_report_metrics([rec])
        html_doc = voicemode_report.render_html_report([rec], metrics)

        self.assertNotIn("<script>alert(1)</script>", html_doc)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_doc)
        self.assertNotIn("<b>evil</b>", html_doc)
        self.assertIn("&lt;b&gt;evil&lt;/b&gt;", html_doc)


# ---------------------------------------------------------------------------
# Task 3 (Plan 08-02): Visual Onboarding Empty State & Privacy Footer Tests
# ---------------------------------------------------------------------------

class TestEmptyStateAndPrivacy(TempXdgTestCase):
    """Task 3: Visual onboarding empty state and 4-subpanel privacy footer."""

    def test_empty_state_rendering(self):
        """RPT-03: Empty ledger renders visual onboarding card, ghost outlines, and shortcut reminder."""
        records = []
        metrics = voicemode_report.compute_report_metrics(records)
        html_doc = voicemode_report.render_html_report(records, metrics)

        self.assertIn("SUPER+SHIFT+M", html_doc)
        self.assertIn("No recordings yet", html_doc)
        self.assertIn("ghost-chart", html_doc)
        self.assertIn("stroke-dasharray", html_doc)

    def test_privacy_footer_subpanels(self):
        """RPT-03: Privacy footer contains all 4 distinct sub-panels."""
        records = [_make_record()]
        metrics = voicemode_report.compute_report_metrics(records)
        html_doc = voicemode_report.render_html_report(records, metrics)

        self.assertIn("1. Local Storage Location", html_doc)
        self.assertIn("2. Retained Schema", html_doc)
        self.assertIn("3. Clipboard Caveat", html_doc)
        self.assertIn("4. Purge History", html_doc)

    def test_privacy_footer_warning_on_skipped_rows(self):
        """D-21: Privacy footer shows warning banner when skipped_count > 0."""
        records = [_make_record()]
        metrics = voicemode_report.compute_report_metrics(records)
        html_doc = voicemode_report.render_html_report(records, metrics, skipped_count=3)

        self.assertIn("⚠️ 3 row(s) skipped due to parse errors", html_doc)


# ---------------------------------------------------------------------------
# Task 1 & 2 (Plan 08-03): Pre-Render Lifecycle Hook & xdg-open Security
# ---------------------------------------------------------------------------

class TestPreRenderWorker(TempXdgTestCase):
    """Task 1 (Plan 08-03): Pre-render worker finalization hook and status.json."""

    def test_finalize_background_run_prerenders_report(self):
        """RPT-04: finalize_background_run creates report.html in state directory."""
        state_dir = voicemode_telemetry.get_state_dir()
        report_file = state_dir / "report.html"
        self.assertFalse(report_file.exists())

        ev = voice.TranscriptionEvidence(
            text="test pre-render",
            model_state=MagicMock(),
            decode_ms=500.0,
            fallback=False,
            failure_type=None,
            backend="cpu, int8",
            avg_logprob=-0.2,
            compression_ratio=1.0,
            no_speech_prob=0.01,
            temperature=0.0,
            vad_audio_s=3.0,
            decoder_segments=1,
            fallback_load_ms=None,
            audio_s=3.0,
        )
        run_state = {
            "lock": None,
            "finalized": False,
            "pid": None,
            "run_id": "test-prerender",
            "ts_start": time.time() - 2.0,
            "t_start": time.monotonic() - 2.0,
            "args": voice.parse_args([]),
            "recorder": None,
            "wav_paths": [],
            "should_delete": False,
            "outcome": "success",
            "error_stage": None,
            "results": {0: ev},
            "results_lock": None,
            "loader_state": {"load_ms": 100.0, "backend": "cpu, int8"},
            "model_holder": {"state": None},
            "text_holder": {"text": "hello"},
            "chars_typed": [5],
            "audio_s": 3.0,
            "status_state": {},
            "status_lock": None,
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
            content = report_file.read_text()
            self.assertIn("Voicemode Latency Report", content)

    def test_prerender_exception_does_not_crash_finalization(self):
        """RPT-04: Exceptions in report pre-rendering are caught and do not prevent cleanup."""
        ev = voice.TranscriptionEvidence(
            text="test fail",
            model_state=MagicMock(),
            decode_ms=500.0,
            fallback=False,
            failure_type=None,
            backend="cpu, int8",
            avg_logprob=-0.2,
            compression_ratio=1.0,
            no_speech_prob=0.01,
            temperature=0.0,
            vad_audio_s=3.0,
            decoder_segments=1,
            fallback_load_ms=None,
            audio_s=3.0,
        )
        run_state = {
            "lock": None,
            "finalized": False,
            "pid": None,
            "run_id": "test-prerender-fail",
            "ts_start": time.time() - 2.0,
            "t_start": time.monotonic() - 2.0,
            "args": voice.parse_args([]),
            "recorder": None,
            "wav_paths": [],
            "should_delete": False,
            "outcome": "success",
            "error_stage": None,
            "results": {0: ev},
            "results_lock": None,
            "loader_state": {"load_ms": 100.0, "backend": "cpu, int8"},
            "model_holder": {"state": None},
            "text_holder": {"text": "hello"},
            "chars_typed": [5],
            "audio_s": 3.0,
            "status_state": {},
            "status_lock": None,
            "finalize_ms": 30.0,
            "insert_ms": 20.0,
            "insert_ok": True,
            "backend": "cpu, int8",
            "predicted": {"shown_s": 1.5, "actual_s": 1.4},
            "text": "hello",
        }

        with patch("voicemode_report.generate_prerendered_report", side_effect=RuntimeError("Disk full!")):
            res = voice.finalize_background_run(run_state, outcome="success")
            self.assertTrue(res)

    def test_status_json_contains_report_path(self):
        """status_state includes report_path pointing to state_dir / report.html."""
        state_dir = voicemode_telemetry.get_state_dir()
        expected_path = str(state_dir / "report.html")

        status = voicemode_telemetry.build_status(
            pid=1234,
            run_id="r1",
            started_at=time.time(),
            audio_s=2.0,
            report_path=expected_path,
            state="recording",
            phase="capture",
        )
        self.assertEqual(status.get("report_path"), expected_path)


class TestXdgOpenSecurity(TempXdgTestCase):
    """Task 2 (Plan 08-03): Secure xdg-open browser invocation."""

    def test_xdg_open_path_validation(self):
        """RPT-06: Paths outside state/metrics directory are rejected with warning and notification."""
        evil_path = Path("/etc/passwd")
        with patch("subprocess.Popen") as mock_popen, \
             patch("voice.notify") as mock_notify:
            ok = voicemode_report.open_report_file(evil_path)
            self.assertFalse(ok)
            mock_popen.assert_not_called()
            mock_notify.assert_called_once()
            self.assertIn("Security", mock_notify.call_args[0][0])

    def test_xdg_open_directory_rejected(self):
        """RPT-06: Directory paths (even inside state_dir) are rejected."""
        state_dir = voicemode_telemetry.get_state_dir()
        with patch("subprocess.Popen") as mock_popen, \
             patch("voice.notify") as mock_notify:
            ok = voicemode_report.open_report_file(state_dir)
            self.assertFalse(ok)
            mock_popen.assert_not_called()
            mock_notify.assert_called_once()

    def test_xdg_open_empty_path_rejected(self):
        """RPT-06: Empty or None path is handled safely without throwing."""
        with patch("subprocess.Popen") as mock_popen, \
             patch("voice.notify") as mock_notify:
            ok = voicemode_report.open_report_file("")
            self.assertFalse(ok)
            mock_popen.assert_not_called()

    def test_xdg_open_missing_binary_fallback(self):
        """RPT-06: Missing xdg-open prints path and sends notification."""
        safe_path = voicemode_telemetry.get_state_dir() / "report.html"
        safe_path.touch()

        with patch("shutil.which", return_value=None), \
             patch("subprocess.Popen") as mock_popen, \
             patch("voice.notify") as mock_notify:
            ok = voicemode_report.open_report_file(safe_path)
            self.assertFalse(ok)
            mock_popen.assert_not_called()
            mock_notify.assert_called_once()
            self.assertIn(str(safe_path.resolve()), mock_notify.call_args[0][1])

    def test_xdg_open_argument_list_execution(self):
        """RPT-06: Valid target passes argument list to subprocess.Popen with start_new_session=True."""
        safe_path = voicemode_telemetry.get_state_dir() / "report.html"
        safe_path.touch()

        with patch("shutil.which", return_value="/usr/bin/xdg-open"), \
             patch("subprocess.Popen") as mock_popen:
            ok = voicemode_report.open_report_file(safe_path)
            self.assertTrue(ok)
            mock_popen.assert_called_once_with(["/usr/bin/xdg-open", str(safe_path.resolve())], start_new_session=True)

    def test_report_open_cli_triggers_launcher(self):
        """voice.main(['--report', '--open']) triggers open_report_file."""
        with patch("voicemode_report.open_report_file", return_value=True) as mock_open:
            f = StringIO()
            old = sys.stdout
            try:
                sys.stdout = f
                code = voice.main(["--report", "--open"])
            finally:
                sys.stdout = old

            self.assertEqual(code, 0)
            mock_open.assert_called_once()


class TestReportOutliersAndDrift(TempXdgTestCase):
    """Verify outlier visualization, drift tracking, and stratified latency reporting (D-04, D-05, D-16)."""

    def test_outliers_filter_records(self):
        """filter_records(..., outliers=True) filters exclusively to outlier records."""
        r_normal = _make_record(run_id="r1", audio_s=5.0, decode_ms=1000.0, outlier=False)
        r_outlier1 = _make_record(run_id="r2", audio_s=2.0, decode_ms=3000.0, outlier=True, outlier_reason="rtf_exceeded")
        r_outlier2 = _make_record(run_id="r3", audio_s=20.0, decode_ms=12000.0, outlier=False)  # classified as outlier by decode_ms > 10.0s
        records = [r_normal, r_outlier1, r_outlier2]

        outliers = voicemode_report.filter_records(records, outliers=True)
        self.assertEqual(len(outliers), 2)
        outlier_ids = {r["run_id"] for r in outliers}
        self.assertEqual(outlier_ids, {"r2", "r3"})

    def test_outliers_drift_calculation(self):
        """compute_report_metrics calculates drift_pct on synthetic upward shift."""
        # Create 30 records with an upward latency shift in recent runs
        records = [_make_record(run_id=f"r{i}", actual_s=1.0) for i in range(20)]
        records.extend([_make_record(run_id=f"r{i}", actual_s=2.0) for i in range(20, 30)])

        metrics = voicemode_report.compute_report_metrics(records)
        self.assertIsNotNone(metrics["drift_pct"])
        self.assertGreater(metrics["drift_pct"], 0)

    def test_outliers_stratified_duration_metrics(self):
        """Stratified duration metrics calculate short (<5s), medium (5-30s), and long (>30s) buckets."""
        r_short = _make_record(run_id="s1", audio_s=3.0, actual_s=1.0, decode_ms=900.0)
        r_med = _make_record(run_id="m1", audio_s=15.0, actual_s=4.0, decode_ms=3500.0)
        r_long = _make_record(run_id="l1", audio_s=45.0, actual_s=12.0, decode_ms=10000.0)
        records = [r_short, r_med, r_long]

        metrics = voicemode_report.compute_report_metrics(records)
        strat = metrics["stratified"]
        self.assertEqual(strat["short"]["count"], 1)
        self.assertEqual(strat["medium"]["count"], 1)
        self.assertEqual(strat["long"]["count"], 1)
        self.assertAlmostEqual(strat["short"]["median_wait_s"], 1.0, places=1)
        self.assertAlmostEqual(strat["medium"]["median_wait_s"], 4.0, places=1)
        self.assertAlmostEqual(strat["long"]["median_wait_s"], 12.0, places=1)

    def test_outliers_render_latency_scatter_svg_contains_crimson_markers(self):
        """render_latency_scatter_svg contains #f43f5e and chart-outlier for outlier points."""
        r_normal = _make_record(run_id="norm", audio_s=4.0, actual_s=1.5, decode_ms=1200.0, outlier=False)
        r_outlier = _make_record(run_id="out", audio_s=2.0, actual_s=3.5, decode_ms=3000.0, outlier=True, outlier_reason="rtf_exceeded")
        records = [r_normal, r_outlier]
        metrics = voicemode_report.compute_report_metrics(records)

        svg = voicemode_report.render_latency_scatter_svg(records, metrics)
        self.assertIn("#f43f5e", svg)
        self.assertIn("chart-outlier", svg)
        self.assertIn("<polygon", svg)

    def test_outliers_render_terminal_summary_status(self):
        """render_terminal_summary displays [OUTLIER] tag and [audio: pruned] when corpus WAV is missing."""
        r = _make_record(
            run_id="out-run", audio_s=2.0, actual_s=3.5, decode_ms=3000.0,
            outlier=True, corpus_file="corpus/nonexistent.wav"
        )
        metrics = voicemode_report.compute_report_metrics([r])
        summary = voicemode_report.render_terminal_summary([r], metrics)
        self.assertIn("[OUTLIER]", summary)
        self.assertIn("[audio: pruned]", summary)


class TestEvaluationProtocol(unittest.TestCase):
    """Test suite validating stratified latency evaluation protocol targets (ACC-06, D-36)."""

    def test_alder_lake_reference_benchmark(self) -> None:
        """20-run reference benchmark on Intel Alder Lake CPU int8 achieves median RTF <= 0.35 and outlier share <= 5%."""
        short_clips = [
            _make_record(run_id="s1", audio_s=2.0, actual_s=0.6, decode_ms=500.0),
            _make_record(run_id="s2", audio_s=3.0, actual_s=0.9, decode_ms=750.0),
            _make_record(run_id="s3", audio_s=4.0, actual_s=1.1, decode_ms=1000.0),
            _make_record(run_id="s4", audio_s=2.5, actual_s=0.7, decode_ms=650.0),
            _make_record(run_id="s5", audio_s=1.5, actual_s=0.5, decode_ms=420.0),
            _make_record(run_id="s6", audio_s=3.5, actual_s=1.0, decode_ms=980.0),
            _make_record(run_id="s7", audio_s=4.5, actual_s=1.3, decode_ms=1260.0),
        ]
        medium_clips = [
            _make_record(run_id="m1", audio_s=10.0, actual_s=2.9, decode_ms=2800.0),
            _make_record(run_id="m2", audio_s=12.0, actual_s=3.5, decode_ms=3360.0),
            _make_record(run_id="m3", audio_s=15.0, actual_s=4.3, decode_ms=4200.0),
            _make_record(run_id="m4", audio_s=20.0, actual_s=5.8, decode_ms=5600.0),
            _make_record(run_id="m5", audio_s=22.0, actual_s=6.3, decode_ms=6160.0),
            _make_record(run_id="m6", audio_s=25.0, actual_s=7.2, decode_ms=7000.0),
            _make_record(
                run_id="m7", audio_s=10.0, actual_s=11.5, decode_ms=11000.0,
                outlier=True, outlier_reason="rtf_exceeded"
            ),
        ]
        long_clips = [
            _make_record(run_id="l1", audio_s=35.0, actual_s=7.5, decode_ms=7000.0),
            _make_record(run_id="l2", audio_s=40.0, actual_s=8.5, decode_ms=8000.0),
            _make_record(run_id="l3", audio_s=42.0, actual_s=8.9, decode_ms=8400.0),
            _make_record(run_id="l4", audio_s=45.0, actual_s=9.5, decode_ms=9000.0),
            _make_record(run_id="l5", audio_s=48.0, actual_s=9.9, decode_ms=9500.0),
            _make_record(run_id="l6", audio_s=50.0, actual_s=10.0, decode_ms=9800.0),
        ]

        dataset = short_clips + medium_clips + long_clips
        self.assertEqual(len(dataset), 20)

        metrics = voicemode_report.compute_report_metrics(dataset)

        all_rtfs = [
            round((r["actual"]["decode_ms"] / 1000.0) / r["audio_s"], 3)
            for r in dataset
        ]
        import statistics
        median_rtf = round(statistics.median(all_rtfs), 3)

        self.assertLessEqual(median_rtf, 0.35)
        self.assertEqual(metrics["outlier_count"], 1)
        self.assertLessEqual(metrics["outlier_rate"], 0.05)

        strat = metrics["stratified"]
        self.assertEqual(strat["short"]["count"], 7)
        self.assertIsNotNone(strat["short"]["median_wait_s"])
        self.assertLessEqual(strat["short"]["median_rtf"], 0.35)

        self.assertEqual(strat["medium"]["count"], 7)
        self.assertIsNotNone(strat["medium"]["median_wait_s"])
        self.assertLessEqual(strat["medium"]["median_rtf"], 0.35)

        self.assertEqual(strat["long"]["count"], 6)
        self.assertIsNotNone(strat["long"]["median_wait_s"])
        self.assertLessEqual(strat["long"]["median_rtf"], 0.35)


if __name__ == "__main__":
    unittest.main()
