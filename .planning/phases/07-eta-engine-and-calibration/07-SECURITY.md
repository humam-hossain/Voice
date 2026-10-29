---
phase: "07"
slug: "eta-engine-and-calibration"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-10-29"
---

# Phase 07 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| File cache -> Memory | `calibration.json` read from filesystem into `voicemode_telemetry` | Rate data / priors |
| Worker process -> `status.json` | Status file written to tmpfs for consumption by external processes (CLI / Quickshell) | Status JSON snapshot |
| Whisper generator -> Worker | Per-segment timing and duration measurements fed into mid-run estimation | Segment metadata / audio duration |
| Tmpfs marker -> Worker | `.boot_session` read/written in `$XDG_RUNTIME_DIR/voice-stt` | Empty flag file |
| CLI caller -> Dispatcher | CLI flags (`--status --json`, `--reset-calibration`) invoked by shell | CLI arguments |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-07-01 | Denial of Service | `voicemode_telemetry:resolve_calibrated_rate` | medium | mitigate | Check for zero/negative audio durations in ratio of sums calculation; fall back to prior RTF if audio sum is non-positive per D-08 | closed |
| T-07-02 | Tampering | `voicemode_telemetry:resolve_calibrated_rate` | medium | mitigate | Sanity-check computed rate against numerical bounds [0.01, 10.0]; reject out-of-bounds rates and fall back to broader hierarchy tier per D-31 | closed |
| T-07-03 | Information Disclosure | `voicemode_telemetry:extract_hierarchy_keys` | low | mitigate | Hierarchy keys format strictly model, device, compute_type, backend, beam_size, vad_filter, language, chunk_s; never interpolate user text, clipboard, or audio paths | closed |
| T-07-04 | Repudiation | `voice.py:update_midrun_eta` | low | mitigate | Persist monotonic `revision_count`, `last_revised_at`, and `max_upward_jump_s` in run state and finalize ledger row per D-11 | closed |
| T-07-05 | Denial of Service | `voice.py:update_midrun_eta` | medium | mitigate | Enforce strict asymmetric hysteresis filter (delta >= 1.0s AND elapsed >= 2.0s) to prevent UI jitter and excessive status writes per D-09 | closed |
| T-07-06 | Integrity | `voice.py:format_eta_pill` | medium | mitigate | Dwell at 1s for 1.0s then transition to explicit 'Finishing…' with overrun: true; never show 0s or negative numbers per D-12, D-16 | closed |
| T-07-07 | Elevation of Privilege | `voicemode_telemetry:save_calibration` | high | mitigate | Enforce `0o600` permissions on `calibration.json` and `.boot_session` and `0o700` on parent directories using `atomic_write_json` | closed |
| T-07-08 | Tampering | `voicemode_telemetry:load_calibration` | high | mitigate | Catch JSON decode errors and malformed data in `load_calibration()`; fall back to shipped priors immediately without raising exceptions per D-08 | closed |
| T-07-09 | Denial of Service | `voicemode_telemetry:fit_calibration_from_ledger` | medium | mitigate | Persist `reset_timestamp` in `.calibration_reset`; ignore ledger records dated before the reset epoch when rebuilding cache per D-03 | closed |

*Status: all 9 threats closed (threats_open: 0)*

---

## Accepted Risks Log

No accepted risks.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-29 | 9 | 9 | 0 | orchestrator |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-29
