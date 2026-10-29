---
phase: 08-accuracy-report-click-through
plan: 02
subsystem: html-dashboard-svg-charts
tags: [html, svg, charts, dark-theme, zero-js, offline, empty-state, privacy]

# Dependency graph
requires:
  - 08-01
provides:
  - "Zero-JavaScript, dark-themed offline HTML report dashboard"
  - "4 responsive inline SVG charts (Predicted vs Actual scatter, Error % Over Time trend, Residual Histogram, Stage Breakdown stacked bars)"
  - "Fluid viewBox scaling with native SVG <title> hover tooltips"
  - "3-tier color coding: Green (<15%), Amber (15-30%), Crimson (>30%)"
  - "Scrollable recent runs table (25 in view, up to 200 rows)"
  - "Visual onboarding empty state card with ghost/dashed chart outlines and SUPER+SHIFT+M shortcut prompt"
  - "Structured 4-subpanel privacy footer with explicit purge and reset commands"
affects: [08-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [pure f-string svg chart generation, zero-js html dashboard, native svg tooltips, responsive viewbox, visual onboarding empty state]

key-files:
  created: []
  modified:
    - voicemode_report.py
    - tests/test_report.py

key-decisions:
  - "Charts and dashboard are strictly zero-JavaScript, zero-external-assets, zero-CDN, with all styling and SVGs embedded inline"
  - "SVG charts use viewBox='0 0 500 320' with fluid CSS max-width: 100% and native SVG <title> elements for browser hover tooltips"
  - "Empty state card presents visual onboarding explaining calibration tiers, displays ghost chart outlines, and prompts SUPER+SHIFT+M"
  - "Privacy footer explicitly documents data file path, retained schema allowlist, clipboard caveat, and purge/reset commands"

requirements-completed: [RPT-02, RPT-03]

coverage:
  - deliverable: "Zero-JavaScript dark HTML dashboard"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestHTMLReport.test_html_report_zero_js_and_self_contained
      status: pass
    human_judgment: false
  - deliverable: "4 responsive inline SVG charts"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestSVGCharts
      status: pass
    human_judgment: false
  - deliverable: "Visual onboarding empty state with ghost chart outlines"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestEmptyStateAndPrivacy.test_empty_state_rendering
      status: pass
    human_judgment: false
  - deliverable: "4-subpanel privacy footer"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestEmptyStateAndPrivacy.test_privacy_footer_subpanels
      status: pass
    human_judgment: false

---

# Plan 08-02 Summary: Offline HTML Dashboard & Inline SVG Charts

Built the self-contained, zero-JavaScript, dark-themed offline HTML dashboard and fluid responsive SVG charting engine in `voicemode_report.py`, verified with hermetic test suites.

## Key Changes
- **`voicemode_report.py`**:
  - Implemented 4 responsive inline SVG charts:
    - `render_scatter_svg`: Predicted vs Actual scatter plot with 45° diagonal dashed line ($y = x$), 3-tier colored data points, and `<title>` tooltips.
    - `render_trend_svg`: Error % Over Time trend curve with 15% and 30% tolerance reference lines, polyline connecting runs, and point tooltips.
    - `render_histogram_svg`: Residual error magnitude $|pred - actual|$ distribution across 8 bins (0–0.25s up to >3s) with rounded column rects.
    - `render_stage_bars_svg`: Stacked horizontal bars decomposing latency into Load (`#6366f1`), Decode (`#38bdf8`), Finalize (`#8b5cf6`), and Insert (`#10b981`).
  - Implemented `render_runs_table`: Scrollable table (max-height 700px, 25 visible, holding up to 200 runs) with sticky header and 3-tier color badges.
  - Implemented `render_empty_state_card`: Visual onboarding card explaining calibration tiers, embedding ghost chart outlines (`render_ghost_charts_svg`), and prompting `SUPER+SHIFT+M`.
  - Implemented `render_privacy_footer`: Dedicated 4-subpanel card detailing Local Storage Location, Retained Schema, Clipboard Caveat, and Purge & Reset commands.
  - Assembled `render_html_report` into a complete standalone HTML document with embedded CSS and zero external network calls.
- **`tests/test_report.py`**:
  - Added `TestSVGCharts` covering viewBox dimensions, coordinate boundaries, tooltips, single-run, and empty datasets.
  - Added `TestHTMLReport` verifying zero `<script>` tags, zero network URLs, XSS escaping, hero cards, and table layout.
  - Added `TestEmptyStateAndPrivacy` verifying onboarding card, ghost outlines, shortcut reminders, 4 privacy subpanels, and skip warning banners.

## Verification
- `uv run pytest tests/test_report.py -v`: 46 passed
- `uv run pytest tests/test_eta_cli.py tests/test_telemetry.py -v`: 34 passed, 10 subtests passed
- Commit hash: `ef2ba35`
