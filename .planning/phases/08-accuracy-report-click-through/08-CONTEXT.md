# Phase 8: Accuracy Report & Click-Through - Context

**Gathered:** 2026-10-30
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase builds an offline, self-contained accuracy report proving ETA honesty. It delivers: a `voice --report` CLI command producing terminal summary, CSV, and HTML output with `--since`/`--last`/`--format`/`--output`/`--open` flags; a zero-JavaScript dark-themed HTML dashboard with inline SVG charts (predicted vs actual scatter, error trend, residual histogram, stage breakdown) and privacy footer; a pre-rendered `report.html` (last 200 runs) regenerated atomically after each worker run for instant click-through from the Quickshell pill (Phase 9); and `voice --metrics` as a quick telemetry health summary. No new dependencies. No Whisper/numpy imports on report paths. No transcript text in any output.
</domain>

<decisions>
## Implementation Decisions

### HTML Report Visual Design
- **D-01:** Fixed dark theme only — no light mode, no `prefers-color-scheme` adaptation. Matches the Arch Linux / Hyprland terminal aesthetic. — **Reversibility:** reversible — adding a light theme later is additive CSS.
- **D-02:** Page layout is 4-card hero metrics at top (total runs, median error %, p90 latency, calibration tier), followed by a 2×2 SVG chart grid (Predicted vs Actual scatter, Error % Over Time trend, Residual Histogram, Stage Breakdown bars), followed by a recent runs table. — **Reversibility:** costly — chart generation functions and HTML structure are tightly coupled to this layout.
- **D-03:** SVG chart interactivity uses native SVG `<title>` elements for browser hover tooltips and CSS `:hover` for stroke/fill highlighting. Zero JavaScript, zero external assets, zero network requests. — **Reversibility:** reversible — could add JS later without breaking the base.
- **D-04:** SVGs use `viewBox="0 0 W H"` with CSS `width: 100%; height: auto; max-width: ...` for fully fluid responsive rendering at any window size or DPI. — **Reversibility:** reversible.
- **D-05:** 3-tier color thresholds for ETA accuracy: Muted Green (<15% error), Amber (15–30% error), Crimson (>30% error or severe overrun). Used consistently in charts and table row highlighting. — **Reversibility:** reversible — palette constants.
- **D-06:** Recent runs table shows 25 runs in direct view with a fixed-height CSS-scrollable container for all 200 pre-rendered runs. — **Reversibility:** reversible — CSS change.
- **D-07:** Privacy footer is a dedicated structured card with 4 sub-panels: data file path, retained schema (timings & char counts only), clipboard caveat, and purge/reset commands (`rm` path, `voice --reset-calibration`). — **Reversibility:** reversible.

### Empty State
- **D-08:** Visual onboarding card when no runs exist: explains what calibration is, shows ghost/dashed SVG chart outlines, displays SUPER+SHIFT+M shortcut to start recording. — **Reversibility:** reversible.

### Terminal Summary & Output Formats
- **D-09:** `voice --report` prints a formatted CLI summary card (key aggregate metrics, calibration level) plus a table of the last 10 runs with stage timings and a link to the HTML report file path. — **Reversibility:** reversible — display formatting.
- **D-10:** `--metrics` is quick statistics and JSON telemetry health (ledger size, schema version, run count). `--report` is the full multi-format report generator (HTML, CSV, terminal, `--open`). They are distinct commands with distinct purposes. — **Reversibility:** reversible.
- **D-11:** CSV export uses canonical flattened columns: `run_id, timestamp, model, device, audio_s, predicted_s, actual_s, error_s, error_pct, load_s, record_s, decode_s, finalize_s, insert_s, outcome, eta_source, confidence`. Headers are stable across versions. — **Reversibility:** costly — downstream tools may depend on column order and names.
- **D-12:** `--metrics --json` and `--report --format json` converge to the same structured summary schema: `{ summary: { total_runs, median_error_pct, p90_latency_s, calibration_tier, last_run_timestamp }, ledger: { path, size_bytes, schema_version } }`. One schema, two entry points. — **Reversibility:** costly — published JSON contract.

### Report Filtering & CLI Interface
- **D-13:** `voice --report` prints terminal summary by default; `--open` flag is required to launch the HTML report in a browser. Prevents unwanted browser popups in terminal/SSH sessions. — **Reversibility:** reversible.
- **D-14:** Default filter is last 200 runs (matches the pre-rendered cache). `--since` accepts ISO date (`2026-10-01`) or relative intervals (`24h`, `7d`, `30d`). `--last` accepts an integer or `all`. — **Reversibility:** reversible.
- **D-15:** Unified `--format {text,html,csv,json}` + `--output <path>` flags. Auto-infers format from file extension when `--output report.csv` is given without explicit `--format`. Default format is `text` (terminal). — **Reversibility:** reversible.
- **D-16:** Passing existing `--model` or `--device` flags alongside `--report` filters report data to matching runs. No new `--filter-*` flags. — **Reversibility:** reversible.
- **D-17:** The pre-rendered `report.html` (last 200 runs) is always unfiltered — it shows all models/devices. CLI-time filters (`--since`, `--last`, `--model`, `--device`) only affect terminal output, CSV export, and on-demand HTML via `--output`. — **Reversibility:** reversible.

### Pre-Render Lifecycle & Performance
- **D-18:** `report.html` is regenerated in `finalize_background_run()`, after the ledger row is appended, as the last step before PID cleanup. — **Reversibility:** reversible — could move to a post-run hook later.
- **D-19:** Atomic write pattern: tempfile in the same directory → `os.replace()` to `report.html`. Consistent with existing `status.json` and `calibration.json` patterns. — **Reversibility:** reversible.
- **D-20:** Report generation errors are best-effort: catch any exception, log to stderr and `voice.log`, never fail the overall transcription run. The report is a side-effect, not the primary outcome. — **Reversibility:** reversible.
- **D-21:** Corrupt or malformed ledger rows are skipped with a warning count in the report footer ("2 of 204 rows skipped due to parse errors"). The generator never crashes on bad input. — **Reversibility:** reversible.

### Module Architecture
- **D-22:** Reporting logic lives in a new `voicemode_report.py` module, separate from `voicemode_telemetry.py`. Clean separation: telemetry handles data collection and calibration; report handles rendering and output. Keeps both modules import-light for CLI paths that only need one. — **Reversibility:** costly — moving functions between modules later breaks import paths.
- **D-23:** HTML+SVG generation uses pure f-strings and string concatenation. Builder functions like `render_scatter_svg()`, `render_histogram_svg()` return SVG string fragments. No new dependencies. — **Reversibility:** reversible — could switch to `string.Template` later.

### xdg-open Security
- **D-24:** Strict path validation before `xdg-open`: resolve to absolute path, verify it starts with the state directory prefix via `os.path.commonpath()`, check `shutil.which('xdg-open')` exists, pass as argument list (not shell string). On failure: desktop notification with the file path + print to stderr. — **Reversibility:** reversible — relaxing validation is easy; tightening later is harder.

### The Agent's Discretion
- Exact CSS color hex values within the dark theme palette and 3-tier thresholds.
- SVG chart dimensions (viewBox width/height) and axis label formatting.
- Exact terminal table column widths and alignment.
- Internal function naming and code organization within `voicemode_report.py`.
- Test placement and mocking strategy for report generation.
- Whether the `--output` flag creates parent directories automatically.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone
- `.planning/REQUIREMENTS.md` — RPT-01 through RPT-06 requirements (6)
- `.planning/ROADMAP.md` — Phase 8 goal and success criteria

### Prior phase context
- `.planning/phases/06-foundations-ledger-status-contract/06-CONTEXT.md` — Ledger schema v1, `atomic_write_json()` pattern, privacy allowlist, status contract, history retention (keep everything by default)
- `.planning/phases/07-eta-engine-and-calibration/07-CONTEXT.md` — ETA engine architecture, calibration key hierarchy, `prior_eta_seconds()`, `calibrated_eta_seconds()`, mid-run blending, confidence tiers, `status.json` field set

### Codebase
- `voice.py` — CLI dispatch (`main()`), `finalize_background_run()`, existing `--report` placeholder (line 4065), `--metrics` handler, `report_stt_failure()`, `parse_args()`
- `voicemode_telemetry.py` — `read_ledger_rows()`, `calibration_key()`, `load_calibration()`, `get_metrics_dir()`, `get_state_dir()`, `atomic_write_json()`, `SCHEMA_V1_KEYS`, `ledger_health()`
- `.planning/codebase/ARCHITECTURE.md` — IPC/state machine, worker coordination
- `.planning/codebase/TESTING.md` — Test patterns, mocking strategy
- `.planning/codebase/STACK.md` — Dependencies, no-new-deps constraint

### Architecture visualization
- `.planning/phases/07-eta-engine-and-calibration/07-architecture.html` — Interactive architecture diagrams including formula breakdown and calibration data flow
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `read_ledger_rows()` in `voicemode_telemetry.py` — Reads JSONL ledger; returns parsed row dicts. Direct input to report generation.
- `atomic_write_json()` in `voicemode_telemetry.py` — Atomic tempfile + `os.replace()` pattern; reuse for `report.html` writes (adapt for text content).
- `calibration_key()` and `load_calibration()` — Retrieve current calibration tier and confidence for the summary card.
- `ledger_health()` — Returns run count, ledger path, size, schema version; feeds `--metrics --json` output.
- `get_state_dir()` / `get_metrics_dir()` — Canonical path resolution for report file placement.
- Existing `--report` placeholder at voice.py line 4065 — Currently just prints run count; replace with full implementation.
- Existing `--metrics` handler at voice.py line 4058 — Currently outputs `ledger_health()` JSON; extend with summary statistics.
- `notify()` function in `voice.py` — Desktop notification wrapper for `xdg-open` failure fallback.

### Established Patterns
- Detached worker processes with PID tracking in `$XDG_RUNTIME_DIR/voice-stt/`
- File-based IPC: `status.json` (advisory) + PID file (authority)
- All state files use `0o700` directories and `0o600` files
- Import-light CLI: non-transcription commands avoid heavy imports
- `finalize_background_run()` handles post-transcription cleanup and telemetry; report regeneration slots in here

### Integration Points
- `finalize_background_run()` in `voice.py` — Insert report regeneration call after ledger append
- `parse_args()` in `voice.py` — Add `--format`, `--output`, `--open`, `--since`, `--last` flags to the `--report` argument group
- `main()` CLI dispatch in `voice.py` — Replace report placeholder with dispatch to `voicemode_report` module
- `status.json` `report_path` field — Already published by Phase 7; points to the pre-rendered `report.html` for Phase 9 click-through
</code_context>

<specifics>
## Specific Ideas

- The 4-card hero metrics should show: Total Runs, Median Error %, P90 Latency, and Calibration Tier (L0/L1/L2/prior with sample count).
- The 2×2 chart grid order: Predicted vs Actual scatter (top-left), Error % Over Time trend (top-right), Residual Histogram (bottom-left), Stage Breakdown stacked bars (bottom-right).
- CSS-only scrollable table uses `max-height` + `overflow-y: auto` on a wrapper div; the first 25 rows are always visible without scrolling.
- The privacy footer card should show the actual `$XDG_STATE_HOME/voice/` path, not a variable reference, so the user can `ls` or `rm` it directly.
- `--metrics --json` and `--report --format json` produce identical output — one schema, two entry points.
- Pre-rendered `report.html` is always the full last 200 runs (unfiltered); CLI-time filters only affect on-demand outputs.
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---
*Phase: 08-Accuracy Report & Click-Through*
*Context gathered: 2026-10-30*
