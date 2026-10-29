---
phase: 08-accuracy-report-click-through
plan: 01
subsystem: telemetry-reporting-engine
tags: [telemetry, report, cli, csv, json, filtering, stats]

# Dependency graph
requires:
  - 06-01
  - 07-01
provides:
  - "voicemode_report.py core reporting module"
  - "Tolerant JSONL ledger reading with torn row tracking (load_ledger_records)"
  - "Multi-criteria filtering by --since, --last, --model, --device"
  - "Summary card metrics calculation (median error %, p90 latency, stage medians/p90s)"
  - "Canonical 17-column CSV export with stable headers"
  - "Converged JSON schema for --metrics --json and --report --format json"
  - "Terminal summary hero card with 10-run summary table"
  - "Lazy CLI argument registration and dispatch in voice.py with zero heavy imports"
affects: [08-02, 08-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [stdlib-only reporting engine, tolerant jsonl reading, 17-column csv export, converged json schema, lazy cli dispatch]

key-files:
  created:
    - voicemode_report.py
    - tests/test_report.py
  modified:
    - voice.py

key-decisions:
  - "voicemode_report.py imports exclusively standard library modules and voicemode_telemetry, maintaining sub-100ms startup without loading faster_whisper, numpy, or sounddevice"
  - "Torn or malformed JSONL ledger rows increment skipped_count without crashing"
  - "CSV export canonicalizes 17 columns in fixed order: run_id, timestamp, model, device, audio_s, predicted_s, actual_s, error_s, error_pct, load_s, record_s, decode_s, finalize_s, insert_s, outcome, eta_source, confidence"
  - "voice.main() accepts optional argv list to support programmatic test execution and CLI dispatch"

requirements-completed: [RPT-01, RPT-05]

coverage:
  - deliverable: "Zero heavy imports on voice --report"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestReportCLI.test_no_heavy_imports_on_report_path
      status: pass
    human_judgment: false
  - deliverable: "Tolerant ledger loading with skip tracking"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestReportCLI.test_ledger_loading_with_torn_lines
      status: pass
    human_judgment: false
  - deliverable: "Multi-criteria filtering"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestReportFilteringAndStats
      status: pass
    human_judgment: false
  - deliverable: "Canonical 17-column CSV export"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestExportFormats.test_csv_export_headers_and_data
      status: pass
    human_judgment: false
  - deliverable: "Converged JSON schema"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestExportFormats.test_converged_json_schema
      status: pass
    human_judgment: false

---

# Plan 08-01 Summary: Core Reporting Engine & CLI Dispatch

Implemented the core reporting engine module `voicemode_report.py`, registered reporting CLI arguments and lazy dispatch handlers in `voice.py`, and verified zero-heavy-import constraints and data contracts with comprehensive hermetic tests.

## Key Changes
- **`voicemode_report.py`**:
  - `load_ledger_records`: Loads metrics records from `metrics.jsonl` and rotated archives, gracefully tracking torn or corrupt rows in `skipped_count`.
  - `filter_records`: Supports filtering by ISO timestamp or relative intervals (`24h`, `7d`, `30d`, `60m`), limit count (`last`), `model`, and `device`.
  - `compute_report_metrics`: Calculates median error %, p90 latency, stage medians/p90s, and calibration tier.
  - `render_terminal_summary`: Formats an ASCII hero card and a 10-row summary table showing stage durations and the report path.
  - `render_csv`: Generates the exact 17 canonical headers in stable order.
  - `render_json`: Unifies `--metrics --json` and `--report --format json` under `{ "summary": {...}, "ledger": {...} }`.
  - `open_report_file`: Implements path-validation-contained execution of `xdg-open` with desktop notification fallbacks.
  - `generate_prerendered_report`: Atomically pre-renders `report.html` for instant click-through.
- **`voice.py`**:
  - Registered `--report`, `--metrics`, `--format`, `--output`, `--open`, `--since`, `--last` CLI flags.
  - Wired lazy dispatch handlers in `main()` into `voicemode_report`.
  - Added pre-render worker hook into `finalize_background_run()` after ledger write.
  - Allowed `main(argv)` parameter for clean programmatic testing.
- **`tests/test_report.py`**:
  - 34 hermetic unit and CLI tests verifying zero-import enforcement, corrupt line recovery, filtering, formatting, and file export options.

## Verification
- `uv run pytest tests/test_report.py -v`: 34 passed
- `uv run pytest tests/test_eta_cli.py tests/test_telemetry.py -v`: 34 passed, 10 subtests passed
- Commit hash: `7a3f20f`
