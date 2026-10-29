---
phase: 08-accuracy-report-click-through
plan: 03
subsystem: worker-prerender-and-secure-launcher
tags: [telemetry, worker, lifecycle, status, xdg-open, containment, security, notification]

# Dependency graph
requires:
  - 08-01
  - 08-02
provides:
  - "Atomic report.html pre-rendering in finalize_background_run()"
  - "Best-effort worker error isolation preventing transcription or PID cleanup failures"
  - "status.json report_path publication pointing to pre-rendered report.html"
  - "Secure open_report_file() launcher with os.path.commonpath() directory containment"
  - "Argument list execution of xdg-open with desktop notification fallback"
  - "Seamless voice --report --open integration"
affects: [09-packaging-release]

# Tech tracking
tech-stack:
  added: []
  patterns: [worker pre-render lifecycle hook, status.json report advertisement, commonpath directory containment, argument-list subprocess invocation]

key-files:
  created: []
  modified:
    - voicemode_report.py
    - voice.py
    - tests/test_report.py

key-decisions:
  - "report.html is pre-rendered atomically in state directory immediately after appending to ledger"
  - "Worker pre-rendering errors are strictly best-effort: exceptions are logged to stderr without disrupting transcription or PID cleanup"
  - "status_state['report_path'] is advertised throughout recording and transcribing for Quickshell status pill integration"
  - "open_report_file strictly enforces directory containment under state/metrics directory via os.path.commonpath, rejecting directory targets and external files"

requirements-completed: [RPT-04, RPT-06]

coverage:
  - deliverable: "Atomic worker pre-rendering lifecycle hook in finalize_background_run"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestPreRenderWorker.test_finalize_background_run_prerenders_report
      status: pass
    human_judgment: false
  - deliverable: "Worker error isolation during report pre-rendering"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestPreRenderWorker.test_prerender_exception_does_not_crash_finalization
      status: pass
    human_judgment: false
  - deliverable: "status.json report_path publication"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestPreRenderWorker.test_status_json_contains_report_path
      status: pass
    human_judgment: false
  - deliverable: "Secure xdg-open path validation and argument list execution"
    verification:
      kind: pytest
      ref: tests/test_report.py#TestXdgOpenSecurity
      status: pass
    human_judgment: false

---

# Plan 08-03 Summary: Worker Pre-Rendering & Secure xdg-open Launcher

Integrated the atomic report pre-rendering lifecycle hook into worker finalization, published `report_path` in `status.json`, and implemented the secure `xdg-open` launcher with strict path containment and notification fallbacks.

## Key Changes
- **`voice.py`**:
  - Initialized `status_state["report_path"]` to `str(voicemode_telemetry.get_state_dir() / "report.html")` in `run_background_recording()`, advertising the pre-rendered HTML path across all status updates.
  - Wired `generate_prerendered_report()` hook into `finalize_background_run()` immediately after appending ledger rows and updating calibration, protected by fail-safe error isolation.
- **`voicemode_report.py`**:
  - Implemented `open_report_file()` enforcing strict path containment using `os.path.commonpath()`, checking that targets reside inside `$XDG_RUNTIME_DIR/voice-stt/` or `$XDG_STATE_HOME/voicemode/` and rejecting directories or outside files.
  - Launched `xdg-open` using an argument list (`[xdg_bin, str(target)]`) with `start_new_session=True` and fallback to desktop notifications and `sys.stderr` on missing binary or execution failure.
  - Wired `handle_report_command()` to open the pre-rendered report (or custom output file) when `--open` is specified.
- **`tests/test_report.py`**:
  - Added `TestPreRenderWorker` testing `finalize_background_run` pre-rendering, error isolation, and `status.json` `report_path` presence.
  - Added `TestXdgOpenSecurity` testing path validation, directory rejection, missing binary fallback, argument list execution, and `--report --open` CLI dispatch.

## Verification
- `uv run pytest tests/test_report.py -v`: 55 passed
- `uv run pytest tests/`: 260 passed (100% clean test suite)
- Commit hash: `b71bb19`
