---
phase: 05-end-to-end-system-verification
plan: "01"
subsystem: diagnostics-and-verification
tags: [diagnostics, doctor, recovery, kill, verification, 3-tier, compositor, hyprctl, wireplumber, test-matrix]

requires:
  - phase: 04-hyprland-integration-daemon-lifecycle
    plan: "02"
    provides: Hardened daemon lifecycle, PID state tracking, and focus safety
provides:
  - Pre-flight diagnostic probe `voice --doctor` verifying Arch binaries, PipeWire mic volume/mute, models, Hyprland Lua keybinds with Stow preservation, and daemon PIDs
  - Contextual Arch Linux remediation commands (`sudo pacman -S ...`, `scripts/download-kokoro-assets.sh`, `voice --install-hotkey`)
  - Daemon recovery command `voice --kill` terminating orphaned recorder/TTS processes and unlinking stale PID locks
  - 3-tier verification framework `voice --verify` and `scripts/verify-e2e.sh`
  - Dynamic compositor interrogation via `hyprctl activewindow -j` extracting window class, title, PID, and workspace
  - Automated Tier 2 synthetic loopback pipeline self-test (~3-4s runtime) verifying tone generation, Kokoro TTS synthesis, Whisper STT loopback decode, and Wayland primary selection round-trip
  - Standardized test payload matrix evaluating conversational prose, punctuation/capitalization, programming code with special symbols, and multiline text with newlines
  - Rich summary table, structured JSON output, and Markdown report export
  - Comprehensive unit and integration test coverage in `tests/test_verification_doctor.py` (30 unit tests, 103 suite total)
affects: [05-02]

actuals:
  tasks: 3
  commits: 3

tech-stack:
  added: [hyprctl activewindow -j, wpctl get-volume, uuid, test-matrix]
  patterns: [3-tier-verification, dynamic-compositor-inspection, synthetic-ai-loopback, clipboard-roundtrip, diagnostic-probing]

key-files:
  modified: [voice.py]
  created: [scripts/verify-e2e.sh, tests/test_verification_doctor.py]

key-decisions:
  - "Implemented voice --doctor with 5 comprehensive inspection subsystems: binaries, audio source volume/mute, model weights, Hyprland keybinds with Stow preservation, and daemon PID health (per D-09, D-10)"
  - "Provided exact Arch Linux remediation commands in doctor output hints for missing packages or assets (per D-10)"
  - "Implemented voice --kill to signal active workers with SIGTERM and purge stale PID locks (per D-11)"
  - "Built 3-tier verification architecture: Tier 1 (static diagnostics), Tier 2 (automated synthetic loopback), Tier 3 (interactive desktop application matrix) (per D-05)"
  - "Created scripts/verify-e2e.sh as executable wrapper delegating to virtualenv voice.py --verify (per D-06)"
  - "Integrated dynamic window inspection via hyprctl activewindow -j with 3-second focus transition countdown instead of hardcoded window targets (per D-07)"
  - "Defined 4 standardized test payloads covering conversational prose, punctuation, code snippets with symbols, and multiline newlines (per D-04)"
  - "Added rich terminal summary table, structured JSON export (--json), and Markdown report export (--export-markdown) (per D-08)"

patterns-established:
  - "check_binary / check_audio_source_status / check_models_status: decoupled diagnostic probes returning (ok, details, remediation)"
  - "hyprctl_active_window: dynamic compositor window interrogation with focus settling countdown"
  - "run_tier1_diagnostics / run_tier2_pipeline_test / run_tier3_interactive_test: tiered test execution with structured latency measurements"
  - "format_verification_markdown / print_verification_summary_table: standardized reporting across console, json, and markdown"

requirements-completed: [VERIF-01, VERIF-02]

coverage:
  - id: D-04
    description: "Standardized test payload matrix covering prose, punctuation, code/symbols, and newlines"
    requirement: "VERIF-01"
    verification:
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestVerificationTiers.test_payloads_matrix"
        status: pass
    human_judgment: false
  - id: D-05
    description: "3-tier verification architecture (Tier 1 static, Tier 2 automated loopback, Tier 3 interactive)"
    requirement: "VERIF-01"
    verification:
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestVerificationTiers.test_run_tier1_diagnostics"
        status: pass
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestVerificationTiers.test_run_tier2_pipeline_test"
        status: pass
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestVerificationTiers.test_run_tier3_interactive_test_headless"
        status: pass
    human_judgment: false
  - id: D-06
    description: "scripts/verify-e2e.sh wrapper delegating to voice.py --verify"
    requirement: "VERIF-01"
    verification:
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestCLIDispatch.test_verify_e2e_script_exists_and_runs_help"
        status: pass
    human_judgment: false
  - id: D-07
    description: "Dynamic window inspection via hyprctl activewindow -j with countdown delays"
    requirement: "VERIF-01"
    verification:
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestCompositorInterrogation.test_hyprctl_active_window_success"
        status: pass
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestCompositorInterrogation.test_hyprctl_active_window_empty_or_no_client"
        status: pass
    human_judgment: false
  - id: D-08
    description: "Terminal summary table, structured JSON output, and Markdown report export"
    requirement: "VERIF-01"
    verification:
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestVerificationTiers.test_run_verification_and_markdown_export"
        status: pass
    human_judgment: false
  - id: D-09
    description: "Diagnostic probe checking binaries, audio devices, models, keybinds, and PIDs"
    requirement: "VERIF-02"
    verification:
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestDoctorDiagnostics.test_check_binary_found_and_missing"
        status: pass
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestDoctorDiagnostics.test_check_audio_source_status_active"
        status: pass
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestDoctorDiagnostics.test_check_models_status_all_valid"
        status: pass
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestDoctorDiagnostics.test_check_hyprland_keybinds_status"
        status: pass
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestDoctorDiagnostics.test_check_daemon_pid_health"
        status: pass
    human_judgment: false
  - id: D-10
    description: "Exact Arch Linux remediation commands in output hints"
    requirement: "VERIF-02"
    verification:
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestDoctorDiagnostics.test_check_binary_found_and_missing"
        status: pass
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestDoctorDiagnostics.test_check_audio_source_status_muted"
        status: pass
    human_judgment: false
  - id: D-11
    description: "Daemon recovery command voice --kill and stale PID file detection"
    requirement: "VERIF-02"
    verification:
      - kind: automated
        ref: "tests/test_verification_doctor.py#TestDaemonRecovery.test_kill_all_daemons_active_and_stale"
        status: pass
    human_judgment: false
---

## Self-Check: PASSED
- `tests/test_verification_doctor.py` passes all 30 tests.
- Full test suite `python -m unittest discover tests` passes all 103 tests.
- `voice --doctor` verified passing on live system.
- `voice --verify --tier 1` verified passing on live system.
- `voice --verify --tier 2` verified passing on live system (4.02s).
- `scripts/verify-e2e.sh --help` verified functioning cleanly.
