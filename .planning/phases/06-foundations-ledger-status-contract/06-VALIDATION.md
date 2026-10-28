---
phase: "6"
slug: "foundations-ledger-status-contract"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: true
created: "2026-10-28"
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` (stdlib) — pytest is NOT installed in this project |
| **Config file** | none — discovery via `python -m unittest discover -s tests` |
| **Quick run command** | `cd /home/pera/github_repo/Voice && .venv/bin/python -m unittest discover -s tests -p "test_<module>.py" -v` |
| **Full suite command** | `cd /home/pera/github_repo/Voice && .venv/bin/python -m unittest discover -s tests` |
| **Estimated runtime** | ~20–40 seconds for the full suite |

---

## Sampling Rate

- **After every task commit:** the plan task's own `<automated>` command (single test module, `tail`-truncated)
- **After every plan wave:** full suite (`unittest discover -s tests`)
- **Before `/gsd-verify-work`:** full suite must be green
- **Max feedback latency:** ~40 seconds (full suite)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | FND-01, LED-01, LED-06 | T-06-01 / T-06-02 | Shared hermetic harness (`tests/_hermetic.py`) before any write; ledger row `0600`, no transcript text; `status.json` removed after run | integration | `python -m unittest discover -s tests -p "test_telemetry.py"` and full suite (legacy modules converted) | ✅ harness + `test_telemetry.py` created | ⬜ pending |
| 06-01-02 | 01 | 1 | FND-01 | T-06-03 | Non-transcription commands load no numpy/sounddevice/faster-whisper | unit | `cd /home/pera/github_repo/Voice && .venv/bin/python -m unittest discover -s tests -p "test_import_light.py" -v` | ✅ created in this task | ⬜ pending |
| 06-01-03 | 01 | 1 | LED-01, LED-06, FND-01 | T-06-04 | Atomic append, `0700` dirs / `0600` files, `VOICE_METRICS=off` writes nothing | unit | `cd /home/pera/github_repo/Voice && .venv/bin/python -m unittest discover -s tests -v` | ✅ existing + new | ⬜ pending |
| 06-02-01 | 02 | 2 | LED-01, LED-02, LED-03 | T-06-05 / T-06-06 | Allowlisted builder rejects unknown/private keys | unit | inline `python -c` schema assertion (see plan) | ✅ created in this task | ⬜ pending |
| 06-02-02 | 02 | 2 | LED-04, LED-05, LED-07 | T-06-07 | Rotation at ~5 MB into a uniquely named archive (sequence-suffixed, never overwritten or deleted); reader tolerates torn tail; docs name `VOICE_*` knobs | unit | inline `python -c` rotation/reader assertion (see plan) + `grep -c` on `docs/telemetry.md` | ✅ created in this task | ⬜ pending |
| 06-02-03 | 02 | 2 | LED-01..07 | T-06-07 | Chars-only, no paths/host/user, TTS fields reserved and empty | unit | `python -m unittest discover -s tests -p "test_telemetry.py"` (fail-able `grep -q "^OK"`) | ✅ | ⬜ pending |
| 06-03-01 | 03 | 2 | FND-02, FND-03 | T-06-09 | Duplicate toggles serialize under `flock`; PID write atomic | unit/integration | `cd /home/pera/github_repo/Voice && .venv/bin/python -m unittest discover -s tests -p "test_pid_race.py" -v` | ✅ created in this task | ⬜ pending |
| 06-03-02 | 03 | 2 | FND-03 | T-06-10 | Worker re-verifies ownership before recording (no phantom worker) | unit | `cd /home/pera/github_repo/Voice && .venv/bin/python -m unittest discover -s tests -p "test_pid_race.py" -v` | ✅ | ⬜ pending |
| 06-03-03 | 03 | 2 | FND-02, FND-05 | T-06-11 | No new PID state strings; torn reads never observed | unit | `python -m unittest discover -s tests -p "test_pid_race.py" -k TestTornReadAndStates` (4 tests) + full suite | ✅ (`TestTornReadAndStates`, 4 cases) | ⬜ pending |
| 06-04-01 | 04 | 3 | STS-01, STS-02 | T-06-12 / T-06-13 | 17-field snapshot schema, clamped non-negative ETA, prior ETA present before model load | unit | inline `python -c` builder assertion (see plan) | ✅ created in this task | ⬜ pending |
| 06-04-02 | 04 | 3 | STS-03, STS-04, STS-05 | T-06-14 | Atomic publish at every transition, 5 s heartbeat, remove on exit, PID stays authority | unit/integration | full suite + shared-vocabulary assertion (see plan) | ✅ | ⬜ pending |
| 06-04-03 | 04 | 3 | STS-01..05 | T-06-15 | Expiry honored; deleting `status.json` never changes bar state; 06-01 harness precondition asserted (legacy modules not edited here) | unit | `python -m unittest discover -s tests -p "test_status_contract.py"` (fail-able `grep -q "^OK"`) | ✅ (9 cases) | ⬜ pending |
| 06-05-01 | 05 | 4 | DEC-01, DEC-02, LED-02 | T-06-16 / T-06-17 | Timed decode spans full generator consumption; per-segment evidence; fallback instrumented | unit | inline `python -c` evidence assertion (see plan) | ✅ created in this task | ⬜ pending |
| 06-05-02 | 05 | 4 | DEC-03, DEC-04 | T-06-18 | Consumer starts after all shared state; monotonic durations; chunk decode while recording; model loaded once before stop | unit/integration | `python -m unittest discover -s tests -p "test_incremental_transcription.py" -k TestIncrementalConsumption` (3 tests) | ✅ (`TestIncrementalConsumption`, 3 cases; created here) | ⬜ pending |
| 06-05-03 | 05 | 4 | DEC-01..04, LED-02 | T-06-19 | Per-chunk `audio_s` reaches evidence/ledger; D-03 cadence (no per-chunk decode writes while capture is open; decode progress rides the heartbeat; `transcribing/decode` at most every 5 s); migrated mocks preserve cancel semantics; `test_telemetry` end-to-end retargeted to `transcribe_timed` | unit | `test_timing.py -k TestTimedSeam` (5) + `test_incremental_transcription.py -k TestIncrementalEdgeCases` (4) + full suite | ✅ (`TestTimedSeam` 5, `TestIncrementalEdgeCases` 4) | ⬜ pending |
| 06-06-01 | 06 | 5 | FND-04, STS-05 | T-06-20 / T-06-21 | One `finalize_background_run()` authority; `run_id`-guarded status cleanup; abandoned-run reconciliation under lock, row built through `build_record` (valid schema/source/install_id) | integration | `python -m unittest discover -s tests -p "test_lifecycle_outcomes.py" -k TestFinalizeAndReconcile` (6 tests) | ✅ (`TestFinalizeAndReconcile`, 6 cases; created here) | ⬜ pending |
| 06-06-02 | 06 | 5 | FND-04 | T-06-22 | Watchdog writes a terminal row before forced exit | unit | `cd /home/pera/github_repo/Voice && .venv/bin/python -m unittest discover -s tests -p "test_hyprland_daemon.py" -v` | ✅ existing | ⬜ pending |
| 06-06-03 | 06 | 5 | FND-04, STS-05 | T-06-23 | Every abnormal exit reaches a terminal outcome; watchdog/finally race yields one row; toggle reconciles before spawn; no stale `transcribing` | integration | `test_lifecycle_outcomes.py -k TestWorkerOutcomes` (8) + full suite | ✅ (`TestWorkerOutcomes`, 8 cases) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

No separate Wave 0 plan is needed: each plan creates its own test module inside the same task that introduces the behavior, so the RED→GREEN cycle happens in-task.

- [x] `tests/_hermetic.py` — created by 06-01-01 **before** write-enabling wiring; provides `TempXdgTestCase` and `advancing_monotonic()` (not discovered: leading underscore)
- [x] `tests/test_telemetry.py` — created by 06-01-01 (extended by 06-02-03; end-to-end seam retargeted by 06-05-03)
- [x] `tests/test_import_light.py` — created by 06-01-02
- [x] `tests/test_pid_race.py` — created by 06-03-01
- [x] `tests/test_status_contract.py` — created by 06-04-01/03 (extended by 06-05-03)
- [x] `tests/test_timing.py` — created by 06-05-01/03
- [x] `tests/test_incremental_transcription.py` — created by 06-05-02 (`TestIncrementalConsumption`); edge cases appended by 06-05-03 (`TestIncrementalEdgeCases`)
- [x] `tests/test_lifecycle_outcomes.py` — created by 06-06-01 (`TestFinalizeAndReconcile`); worker outcomes appended by 06-06-03 (`TestWorkerOutcomes`)
- [x] `tests/test_audio_chunking.py` / `tests/test_hyprland_daemon.py` — converted to `TempXdgTestCase` and `advancing_monotonic()` by 06-01-01 (no later plan edits these for hermeticity)
- [x] Framework install — none needed; `unittest` is stdlib and `.venv/bin/python` already exists

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `voice --status` completes in under 100 ms warm | FND-01 | Wall-clock timing on the developer's machine; automated timing is flaky in CI. The plan includes an automated best-of-N subprocess probe |
| GPU→CPU fallback produces real per-backend evidence | DEC-03 | Requires CUDA hardware; the dev machine is CPU-only, so only the simulated fallback path is automated |
| Two rapid physical toggle presses leave one worker | FND-03 | Hardware keypress timing; automated test uses two concurrent `Popen` calls under `flock` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
