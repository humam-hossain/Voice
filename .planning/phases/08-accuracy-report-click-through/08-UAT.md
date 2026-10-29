---
status: complete
phase: 08-accuracy-report-click-through
source:
  - 08-01-SUMMARY.md
  - 08-02-SUMMARY.md
  - 08-03-SUMMARY.md
started: 2026-10-30T04:10:00Z
updated: 2026-10-30T04:10:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Core Reporting CLI & Zero-Heavy-Import Startup
expected: Running `voice --report` executes in sub-100ms without importing `faster_whisper`, `numpy`, or `sounddevice`. Terminal output renders a formatted hero metrics card and a 10-run summary table.
result: pass

### 2. Multi-Criteria Filtering & Tolerant Ledger Reading
expected: Ledger parsing tolerates torn or corrupt rows and reports `skipped_count`; filtering by `--since` (ISO date or relative `24h`/`7d`/`30d`), `--last` (integer or `all`), `--model`, and `--device` correctly scopes records.
result: pass

### 3. Canonical 17-Column CSV Export & Converged JSON Contract
expected: `--format csv` / `.csv` output produces exactly 17 canonical headers in stable order (`run_id, timestamp, model, device, audio_s, predicted_s, actual_s, error_s, error_pct, load_s, record_s, decode_s, finalize_s, insert_s, outcome, eta_source, confidence`). `--metrics --json` and `--report --format json` emit identical converged `{ "summary": {...}, "ledger": {...} }` schemas.
result: pass

### 4. Zero-JavaScript Dark HTML Dashboard & Inline SVG Charts
expected: `render_html_report()` produces a standalone, zero-JS HTML5 document with dark theme (`#0f172a`), 4 hero metric cards, 4 fluid responsive inline SVG charts (Predicted vs Actual scatter with 45° diagonal, Error % Over Time trend with 15%/30% lines, Residual Histogram across 8 bins, Stage Breakdown stacked bars), native `<title>` tooltips, 3-tier color coding (green <15%, amber 15–30%, crimson >30%), and a scrollable runs table (25 in view, up to 200 runs).
result: pass

### 5. Visual Onboarding Empty State & 4-Subpanel Privacy Footer
expected: On an empty ledger, an onboarding card with ghost chart outlines and `SUPER+SHIFT+M` shortcut prompt is displayed. The privacy footer contains 4 distinct sub-panels: Local Storage Location, Retained Schema allowlist, Clipboard Caveat, and Purge & Reset commands (`rm ...` and `voice --reset-calibration`).
result: pass

### 6. Atomic Worker Pre-Rendering & Secure xdg-open Browser Launch
expected: `voice.py:finalize_background_run()` atomically regenerates `report.html` (last 200 runs) immediately after ledger write; errors in pre-rendering are caught and isolated so PID unlinking and transcript completion never wedge. `status.json` publishes `report_path`. `open_report_file()` enforces directory containment under state/metrics directory via `os.path.commonpath()`, executes `xdg-open` via argument list, and falls back to desktop notifications and stderr.
result: pass

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
