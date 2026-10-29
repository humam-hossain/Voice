---
phase: "8"
slug: "accuracy-report-click-through"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-30"
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.2.0 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/test_report.py -q` |
| **Full suite command** | `uv run pytest tests/` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_report.py -q`
- **After every plan wave:** Run `uv run pytest tests/test_report.py tests/test_eta_cli.py tests/test_telemetry.py tests/test_timing.py tests/test_status_contract.py`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | RPT-01 | — | Report CLI functions without importing Whisper/numpy/sounddevice | Unit/CLI | `uv run pytest tests/test_report.py::test_no_heavy_imports_on_report_path -x` | ❌ W0 | ⬜ pending |
| 08-01-02 | 01 | 1 | RPT-05 | — | Stable 17-column CSV headers & converged JSON output | Unit | `uv run pytest tests/test_report.py::test_csv_export_headers_and_data tests/test_report.py::test_converged_json_schema -x` | ❌ W0 | ⬜ pending |
| 08-02-01 | 02 | 2 | RPT-02 | T-08-02 | Inline SVGs render without JS or external resources | Unit | `uv run pytest tests/test_report.py::test_html_report_zero_js_and_self_contained -x` | ❌ W0 | ⬜ pending |
| 08-02-02 | 02 | 2 | RPT-03 | T-08-04 | Empty state with ghost charts & privacy footer with 4 subpanels | Unit | `uv run pytest tests/test_report.py::test_empty_state_rendering tests/test_report.py::test_privacy_footer_content -x` | ❌ W0 | ⬜ pending |
| 08-03-01 | 03 | 3 | RPT-04 | T-08-03 | Pre-render report atomically in finalize_background_run | Integration | `uv run pytest tests/test_report.py::test_finalize_background_run_prerenders_report -x` | ❌ W0 | ⬜ pending |
| 08-03-02 | 03 | 3 | RPT-06 | T-08-01 | Strict path validation under state dir & fallback for xdg-open | Unit | `uv run pytest tests/test_report.py::test_xdg_open_path_validation tests/test_report.py::test_xdg_open_missing_fallback -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_report.py` — test harness and stubs for RPT-01 through RPT-06

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual rendering in Wayland browser via `voice --report --open` | RPT-02 | Validates browser layout, dark theme appearance, and SVG tooltip hover in desktop environment | Run `voice --report --open` on Wayland desktop; verify dark theme aesthetic and hover tooltips on scatter points |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
