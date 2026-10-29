---
phase: "08"
slug: "accuracy-report-click-through"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-10-30"
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Disk JSONL -> Memory | Ledger records read from `metrics.jsonl` into Python dictionaries | JSONL rows / timing telemetry |
| Telemetry -> CLI / Filesystem | Aggregated metrics exported to terminal, CSV, or JSON files | Aggregated statistics, CSV/JSON text |
| User CLI Input -> Filter Engine | User parameters passed via `--since`, `--last`, `--model`, `--device`, `--output` | Filter expressions, path arguments |
| Memory -> HTML String | Model names, devices, metrics formatted into HTML document | Interpolated strings |
| Browser -> Local System | Browser rendering local HTML document | Standalone HTML/SVG file |
| CLI / Worker -> Browser Process | Target file path passed to system `xdg-open` binary | File path argument |
| Worker Process -> Runtime State | Pre-rendered `report.html` written to tmpfs state directory | Standalone HTML document |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-08-01 | Elevation of Privilege / Arbitrary File Execution | `voicemode_report:open_report_file` | high | mitigate | Strict directory containment check via `os.path.commonpath()`; argument list invocation (never shell); ensure target `is_file()` (D-24, RPT-06) | closed |
| T-08-02 | Tampering / XSS | `voicemode_report:render_html_report` | high | mitigate | Zero `<script>` tags, zero event handlers; run all text values through `html.escape()`; zero external script or style inclusion (D-03, RPT-02) | closed |
| T-08-03 | Denial of Service | `voicemode_report:load_ledger_records` | medium | mitigate | Parse each JSONL line in isolated `try ... except json.JSONDecodeError`; increment `skipped_count` and continue without crashing (D-21) | closed |
| T-08-04 | Information Disclosure | `voicemode_report:record_to_csv_row` | high | mitigate | Operate strictly on numeric timings, character counts, and model parameters; never write transcript text, prompts, hotwords, or clipboard text to CSV/JSON (LED-04, RPT-05) | closed |
| T-08-05 | Tampering / File Overwrite | `voicemode_report:handle_report_command` | medium | mitigate | Enforce directory containment check and warn if output file exists, preventing arbitrary system file overwriting | closed |
| T-08-06 | Information Disclosure | `voicemode_report:render_privacy_footer` | low | mitigate | Explicitly clarify stored schema and purge commands so user has complete transparency and control over local telemetry data (D-07, RPT-03) | closed |
| T-08-07 | Denial of Service / Worker Wedging | `voice:finalize_background_run` | medium | mitigate | Wrap report regeneration in catch-all `try ... except Exception`; worker PID cleanup and transcript completion guaranteed even on report error (D-20, RPT-04) | closed |

*Status: all 7 threats closed (threats_open: 0)*

---

## Accepted Risks Log

No accepted risks.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-30 | 7 | 7 | 0 | orchestrator |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-30
