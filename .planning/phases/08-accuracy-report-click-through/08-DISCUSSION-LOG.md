# Phase 8: Accuracy Report & Click-Through - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-30
**Phase:** 08-Accuracy Report & Click-Through
**Areas discussed:** HTML Report Visual Design & Charts, Terminal Summary & Output Formats, Report Filtering & CLI Interface, Pre-Render Lifecycle & Performance, Report Module Placement, HTML Generation Approach, xdg-open Security Hardening

---

## HTML Report Visual Design & Charts

### Theme

| Option | Description | Selected |
|--------|-------------|----------|
| Adaptive dark/light theme | Defaults to dark, adapts via CSS `prefers-color-scheme` | |
| Fixed dark theme only | Always dark with high-contrast slate/cyan accents | ✓ |
| Minimal clean monochrome | Neutral slate/white card layout | |

**User's choice:** "only dark theme"

### Page Layout

| Option | Description | Selected |
|--------|-------------|----------|
| 4-Card Hero Metrics + 2x2 SVG Chart Grid | Summary stats at top, 4 charts, then runs table | ✓ |
| Vertical Narrative Stream | Linear top-to-bottom with full-width charts | |
| Dense Analytics Dashboard | Side-by-side compact panels with sidebar | |

**User's choice:** 4-Card Hero Metrics + 2x2 SVG Chart Grid

### Chart Interactivity

| Option | Description | Selected |
|--------|-------------|----------|
| SVG `<title>` tooltips + CSS hover | Native browser tooltips, zero-JS | ✓ |
| Static SVG value callouts | Labels rendered directly on peaks/medians | |
| Charts only + tabular data below | No interactivity on charts | |

**User's choice:** SVG `<title>` tooltips + CSS hover effects

### Empty State

| Option | Description | Selected |
|--------|-------------|----------|
| Visual Onboarding Card | Calibration explanation, ghost SVG outlines, SUPER+SHIFT+M shortcut | ✓ |
| Minimal Banner | Simple "No runs recorded yet" notice | |
| You decide | Builder's discretion | |

**User's choice:** Visual Onboarding Card

### SVG Responsiveness

| Option | Description | Selected |
|--------|-------------|----------|
| Fully fluid responsive SVGs | viewBox + CSS width: 100%, height: auto | ✓ |
| Fixed-width centered canvas | 960px or 1200px container | |
| You decide | Builder's discretion | |

**User's choice:** Fully fluid responsive SVGs

### Color Thresholds

| Option | Description | Selected |
|--------|-------------|----------|
| 3-tier dark-palette | Green (<15%), Amber (15–30%), Crimson (>30%) | ✓ |
| 2-tier | Cyan (<25%) vs Red/Orange (>25%) | |
| Continuous gradient | Smooth hue interpolation | |

**User's choice:** 3-tier dark-palette thresholds

### Table Size

| Option | Description | Selected |
|--------|-------------|----------|
| Recent 25 + scrollable 200 | Direct view of 25, scrollable container for all 200 | ✓ |
| Pageless all 200 | All rows directly visible | |
| Top 20 + Top 5 Outliers | Split tables for recent and diagnostic | |

**User's choice:** Recent 25 in direct view + scrollable container for all 200

### Privacy Footer

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated structured card | 4 sub-panels: Path, Schema, Clipboard Caveat, Purge/Reset | ✓ |
| Collapsible `<details>` drawer | Hidden until clicked | |
| You decide | Builder's discretion | |

**User's choice:** Dedicated structured card with 4 sub-panels

---

## Terminal Summary & Output Formats

### Default Terminal Output

| Option | Description | Selected |
|--------|-------------|----------|
| Summary card + last 10 runs table | Metrics header + aligned table + HTML report link | ✓ |
| Compact 6-line block | Key figures only, point to --open | |
| Full verbose tabular dump | All matching runs in wide table | |

**User's choice:** Formatted CLI summary card + last 10 runs table

### --metrics vs --report

| Option | Description | Selected |
|--------|-------------|----------|
| Distinct commands | --metrics = quick stats/health; --report = full multi-format | ✓ |
| Alias | --metrics = --report --format text | |
| You decide | Builder's discretion | |

**User's choice:** Distinct commands with distinct purposes

### CSV Columns

| Option | Description | Selected |
|--------|-------------|----------|
| Canonical flattened | run_id, timestamp, model, device, audio_s, predicted_s, actual_s, error_s, error_pct, stage timings, outcome, eta_source, confidence | ✓ |
| Minimalist | timestamp, audio_s, predicted_s, actual_s, error_pct, outcome | |
| Full raw dump | Every ledger field flattened | |

**User's choice:** Canonical flattened columns

### JSON Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Structured summary object | { summary: {...}, ledger: {...} } | ✓ |
| Raw row array | [ { run_id, ... }, ... ] | |
| Hybrid | { summary: {...}, runs: [...] } | |

**User's choice:** Structured summary object

---

## Report Filtering & CLI Interface

### Browser Opening

| Option | Description | Selected |
|--------|-------------|----------|
| Require --open | Terminal summary by default, --open launches browser | ✓ |
| Auto-open | Always opens browser, --no-open to suppress | |
| Prompt interactively | Ask [y/N] in terminal | |

**User's choice:** Require --open flag

### Default Filter & Syntax

| Option | Description | Selected |
|--------|-------------|----------|
| Last 200 runs + relative --since | --since accepts ISO date or 24h/7d/30d; --last accepts integer or 'all' | ✓ |
| All history default | Unless --last or --since provided | |
| Last 50 + --all | Smaller default with explicit expansion | |

**User's choice:** Last 200 runs default with relative --since and --last

### Format & Output Flags

| Option | Description | Selected |
|--------|-------------|----------|
| Unified --format + --output | --format {text,html,csv,json} + --output <path>, auto-infer from extension | ✓ |
| Separate flags | --html, --csv, --json | |
| You decide | Builder's discretion | |

**User's choice:** Unified --format + --output with auto-infer

### Model/Device Filtering

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing flags | --model and --device alongside --report filter matching runs | ✓ |
| Dedicated --filter-* flags | Add explicit filter flags | |
| No model filtering | Charts show breakdown, no CLI filter | |

**User's choice:** Reuse existing --model and --device flags

---

## Pre-Render Lifecycle & Performance

### Regeneration Timing

| Option | Description | Selected |
|--------|-------------|----------|
| In finalize_background_run() | After ledger append, before PID cleanup | ✓ |
| Post-run hook | After worker exits completely | |
| Lazy on next CLI | Skip background pre-render | |

**User's choice:** In finalize_background_run() after ledger append

### Atomicity

| Option | Description | Selected |
|--------|-------------|----------|
| Tempfile + os.replace() | Consistent with existing status.json pattern | ✓ |
| Direct write | Non-atomic, simpler | |
| You decide | Builder's discretion | |

**User's choice:** Standard atomic pattern

### Error Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Best-effort + stderr log | Catch, log, never fail the run | ✓ |
| Strict propagation | User sees failure via notification | |
| Silent swallow | No logging | |

**User's choice:** Best-effort with stderr log

### Corrupt Rows

| Option | Description | Selected |
|--------|-------------|----------|
| Skip + warning count | "2 of 204 rows skipped due to parse errors" in footer | ✓ |
| Halt on error | Show corrupt line number | |
| You decide | Builder's discretion | |

**User's choice:** Skip with warning count in footer

---

## Report Module Placement

| Option | Description | Selected |
|--------|-------------|----------|
| New voicemode_report.py | Clean separation: telemetry vs report | ✓ |
| Add to voicemode_telemetry.py | Single module, grows to 1000+ lines | |
| You decide | Builder's discretion | |

**User's choice:** New voicemode_report.py module

---

## HTML Generation Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Pure f-strings | No dependencies, builder functions return SVG fragments | ✓ |
| string.Template | Stdlib $variable placeholders | |
| Jinja2/Mako | Powerful but adds dependency (violates constraint) | |

**User's choice:** Pure f-strings and string concatenation

---

## xdg-open Security Hardening

| Option | Description | Selected |
|--------|-------------|----------|
| Strict validation | Absolute path, commonpath check, shutil.which, argument list, notification fallback | ✓ |
| Moderate | File exists + state dir check + shell-escape | |
| You decide | Builder's discretion | |

**User's choice:** Strict validation with notification fallback

---

## The Agent's Discretion

- Exact CSS color hex values within the dark theme palette and 3-tier thresholds
- SVG chart dimensions (viewBox width/height) and axis label formatting
- Exact terminal table column widths and alignment
- Internal function naming and code organization within voicemode_report.py
- Test placement and mocking strategy for report generation
- Whether --output flag creates parent directories automatically

## Deferred Ideas

None — discussion stayed within phase scope.

## Cross-Check Notes

- Confirmed: `--metrics --json` and `--report --format json` produce the same structured summary schema (converged).
- Confirmed: Pre-rendered `report.html` is always unfiltered (last 200 runs); CLI-time filters only affect on-demand outputs.
