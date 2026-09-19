---
phase: 04-hyprland-integration-daemon-lifecycle
plan: "02"
subsystem: daemon-lifecycle
tags: [daemon, pid-state, signals, sigusr1, sigterm, mutex, watchdogs, focus-safety, notifications, cues]

requires:
  - phase: 04-hyprland-integration-daemon-lifecycle
    plan: "01"
    provides: Hyprland keybinding shortcuts and dotfiles integration
provides:
  - "Atomic PID lifecycle state tracking in `recorder.pid` (`starting` -> `recording` -> `transcribing` -> `idle`)"
  - "Double-tap startup race mitigation with 300ms child readiness polling"
  - "Busy state protection emitting dual-tone error chime when invoked during transcription or text typing"
  - "Clean signal differentiation: `SIGUSR1` initiates stop and transcribe; `SIGTERM`/`SIGINT` aborts immediately and cleans up without typing"
  - "Symmetric STT/TTS mutual exclusion to prevent audio bleed and device contention in both directions"
  - "Hardened process aliveness check verifying `/proc/<pid>/cmdline` against PID recycling"
  - "60-second transcription watchdog preventing zombie daemon state if inference or typing stalls"
  - "Dynamic recording ceiling (`VOICE_MAX_RECORDING_SECONDS`) defaulting to 300s"
  - "Periodic reminder cue tick interval (`VOICE_RECORDING_BEEP_INTERVAL`) defaulting to 5.0s"
  - "Focus-safe desktop notification policy suppressing routine STT toasts to prevent Wayland keystroke disruption"
  - "Low-urgency quick auto-dismiss configuration for TTS toasts (`-u low -t 2000`)"
  - "Full unit test coverage in `tests/test_hyprland_daemon.py`"
affects: [05-system-verification]

actuals:
  tasks: 3
  commits: 1

tech-stack:
  added: [/proc/<pid>/cmdline, threading.Timer]
  patterns: [pid-state-machine, readiness-polling, cmdline-identity-check, watchdog-timer, focus-safe-notifications]

key-files:
  modified: [voice.py, tests/test_hyprland_daemon.py]

key-decisions:
  - "Recorded explicit state tokens in recorder.pid (starting -> recording -> transcribing -> idle) with backward compatibility for plain integer PIDs (per D-11, D-12)"
  - "Mitigated double-tap startup races by polling up to 300ms for child to transition from starting to recording before sending SIGUSR1 (per D-11, T-04-06 mitigation)"
  - "Protected transcribing state with error cue chime, rejecting duplicate actuation while worker is transcribing/typing (per D-12)"
  - "Differentiated SIGUSR1 (graceful stop, WAV export, transcription, typing) from SIGTERM/SIGINT (clean abort, buffer cleanup, exit 0) (per D-13)"
  - "Enforced symmetric STT/TTS mutual exclusion: starting STT silences active TTS via stop_tts; starting TTS aborts active STT via cancel_active_stt with SIGTERM (per D-14, T-04-09 mitigation)"
  - "Hardened process_alive(pid) by checking /proc/<pid>/cmdline for voice/python/voicemode tokens to prevent signal misdirection on PID recycling (per D-15, T-04-02 mitigation)"
  - "Armed 60-second transcription watchdog timer around model loading, transcription, and typing to terminate hung daemons (per D-16, T-04-04 mitigation)"
  - "Suppressed routine STT desktop toasts (Recording..., Transcribing..., Transcript inserted.) during normal dictation to prevent Wayland focus stealing during wtype keystroke simulation (per D-17, T-04-07 mitigation)"
  - "Retained STT desktop toasts strictly for exceptional events: errors, no speech detected, or max recording duration ceiling (per D-18)"
  - "Played quiet periodic reminder cue tick every 5 seconds (overridable via VOICE_RECORDING_BEEP_INTERVAL) to confirm active microphone (per D-19)"
  - "Configured low urgency and 2000ms timeout for TTS toasts (-u low -t 2000) (per D-20)"

patterns-established:
  - "read_pid_state / write_pid_state: multi-token PID file state tracking"
  - "process_alive: Linux /proc cmdline process identity verification"
  - "transcription_watchdog_handler: daemon deadman switch for inference/typing hangs"
  - "cancel_active_stt: cross-subsystem mutual exclusion"

requirements-completed: [HYPR-02]

coverage:
  - id: D-11
    description: "Multi-state PID tracking (starting -> recording) and 300ms double-tap race mitigation"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDaemonLifecycleStates.test_write_and_read_pid_state"
        status: pass
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDaemonLifecycleStates.test_double_tap_startup_race_wait"
        status: pass
    human_judgment: false
  - id: D-12
    description: "Busy state protection emitting error chime when invoked during transcription"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDaemonLifecycleStates.test_busy_state_protection_error_cue"
        status: pass
    human_judgment: false
  - id: D-13
    description: "Differentiate SIGUSR1 (stop & transcribe) from SIGTERM/SIGINT (clean abort)"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDaemonLifecycleStates.test_signal_differentiation_usr1_vs_term"
        status: pass
    human_judgment: false
  - id: D-14
    description: "Symmetric STT/TTS mutual exclusion to eliminate concurrent audio access"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDaemonLifecycleStates.test_symmetric_mutex_stt_stops_tts"
        status: pass
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDaemonLifecycleStates.test_symmetric_mutex_tts_stops_stt"
        status: pass
    human_judgment: false
  - id: D-15
    description: "Hardened process_alive checking /proc/<pid>/cmdline against PID recycling"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDaemonLifecycleStates.test_hardened_process_alive_cmdline_verification"
        status: pass
    human_judgment: false
  - id: D-16
    description: "60-second transcription watchdog and configurable recording ceiling"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDaemonLifecycleStates.test_transcription_watchdog_timeout"
        status: pass
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDaemonLifecycleStates.test_safety_recording_duration_ceiling_override"
        status: pass
    human_judgment: false
  - id: D-17
    description: "Suppress routine STT desktop toasts to prevent Wayland focus stealing during wtype typing"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDesktopNotificationBehavior.test_routine_stt_notifications_suppressed"
        status: pass
    human_judgment: false
  - id: D-18
    description: "Retain STT desktop toasts for exceptional conditions"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDesktopNotificationBehavior.test_exceptional_stt_notifications_allowed"
        status: pass
    human_judgment: false
  - id: D-19
    description: "Periodic reminder cue tick interval"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDesktopNotificationBehavior.test_periodic_reminder_cue_interval"
        status: pass
    human_judgment: false
  - id: D-20
    description: "Low-urgency quick auto-dismiss configuration for TTS toasts (-u low -t 2000)"
    requirement: "HYPR-02"
    verification:
      - kind: automated
        ref: "tests/test_hyprland_daemon.py#TestDesktopNotificationBehavior.test_tts_notification_urgency_and_timeout"
        status: pass
    human_judgment: false
---

## Self-Check: PASSED
- `tests/test_hyprland_daemon.py` passes all 22 tests.
- Full test suite `python -m unittest discover tests` passes (73 tests).
- `git log` returns commit `4cf32db` for `04-02`.
- `voice --status` verified returning `idle`.
