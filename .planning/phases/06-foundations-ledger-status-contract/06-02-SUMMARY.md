---
phase: 06-foundations-ledger-status-contract
plan: 02
subsystem: telemetry
tags: [telemetry, schema, ledger, privacy, rotation, install-id]

# Dependency graph
requires:
  - phase: 06-foundations-ledger-status-contract
    provides: [telemetry module seam, hermetic tests]
provides:
  - "Schema v1 with allowlist validator and build_record"
  - "Privacy enforcement via allowlist; chars-only; TTS-reserved fields"
  - "Size-based rotation with unique archive names"
  - "Install ID (salted hash), ledger reader/health"
  - "docs/telemetry.md"
affects: [06-03, 06-04, 06-05, 06-06]

# Tech tracking
tech-stack:
  added: []
  patterns: [schema allowlist validation, rotation with uniqueness, salted install id]

key-files:
  created:
    - docs/telemetry.md
  modified:
    - voicemode_telemetry.py
    - tests/test_telemetry.py

key-decisions:
  - "Schema is frozen via SCHEMA_V1_KEYS allowlist enforced on every append"
  - "Install ID derived from salted machine-id hash, stored locally with 0600"

patterns-established:
  - "All ledger writes validated before disk access"
  - "Rotation never loses history"

requirements-completed: [LED-01, LED-02, LED-03, LED-04, LED-05, LED-06, LED-07]

# Metrics
duration: ~15min
completed: 2026-10-28
status: complete
---

# Phase 06: Foundations, Ledger & Status Contract Summary

**Frozen ledger schema v1 with allowlist validation, privacy enforcement, rotation, install identity, and documentation.**

## Accomplishments
- Added schema v1 allowlist (`SCHEMA_V1_KEYS`), nested key sets, `validate_record`, `build_record` with full defaults
- Enforced privacy (rejects extra keys like transcript/text/prompt; chars-only counts; TTS fields reserved null)
- Added size-based rotation (~5MB) with uniquely named archives preserving history
- Added `get_install_id()` (salted machine-id hash), `read_ledger_rows()`, `ledger_health()`
- Created `docs/telemetry.md` documenting schema, privacy, env vars, deletion

## Files Created/Modified
- `voicemode_telemetry.py` - Schema, validation, rotation, install id, reader/health
- `tests/test_telemetry.py` - Schema/privacy/chars/install-id/kill-switch tests
- `docs/telemetry.md` - Documentation

## Deviations from Plan
None - plan executed exactly as written
