---
status: resolved
trigger: "Fix ETA prediction leak: background chunk decoding during recording leaks 1s-4s ETAs and poisons predicted.shown_s in ledger, causing >90% false error rate in voice --report"
created: 2026-10-30
updated: 2026-10-30
symptoms:
  expected: "ETAs must stay None while recording. shown_s must only capture the initial ETA calculated for the full audio upon transitioning to transcribing."
  actual: "While recording, background consumer transcribes 5-second audio chunks. In _on_segment_yield, it calculates an ETA for only that single chunk (resulting in ~1s–4s). In _publish_status, run_state['predicted']['shown_s'] captures the first non-null eta_remaining_s. Because it leaks during recording, the ledger locks in a 1s–4s prediction for runs that actually have 30s–200s of audio and take 40s–250s of actual time, causing false 90%+ error rates in voice --report."
  errors: ">90% false error rate in voice --report due to poisoned predicted.shown_s"
  timeline: "Discovered during analysis of voice --report metrics with background chunk decoding enabled."
  reproduction: "Run voice STT with background chunk decoding during recording, observe status.json and ledger predicted.shown_s capturing single-chunk 1s-4s ETA instead of waiting for transcription transition."
---

## Current Focus
- hypothesis: Background chunk decoding during recording publishes an eta_remaining_s calculated for only that chunk via _on_segment_yield, which _publish_status records in run_state['predicted']['shown_s'] prematurely. (CONFIRMED)
- test: TestEtaLeakageDuringRecording in tests/test_midrun_eta.py reproduces the leak on unpatched code and verifies fix.
- expecting: ETAs remain None during recording; shown_s only captures initial full-audio ETA on transitioning to transcribing.
- next_action: None; bug fixed and verified.

reasoning_checkpoint:
  hypothesis: "In voice.py, background chunk decoding while recording calls _on_segment_yield for 5s chunks, which calculates remaining_s (~1s-4s) for that chunk and publishes state='transcribing' with eta_remaining_s. _publish_status records the first non-null eta_remaining_s into run_state['predicted']['shown_s'], locking in a 1s-4s prediction before recording completes and full-audio ETA can be calculated."
  confirming_evidence:
    - "voice.py lines 2349-2415: _on_segment_yield computes remaining_s from total_audio_s (the single chunk duration) and calls _publish_status('transcribing', 'decode', ..., eta_remaining_s=disp['display_s']) without checking whether capture_closed is set."
    - "voice.py lines 2288-2300: _publish_status checks if pred.get('shown_s') is None and captures rem immediately whenever rem is not None, regardless of whether state is 'recording' or 'transcribing'."
    - "voice.py lines 2440: transcribe_timed is invoked for each chunk from chunk_queue with on_segment_yield=_on_segment_yield while recording is active."
    - "Reproduced in tests/test_midrun_eta.py: prior to fix, test_chunk_decoding_during_recording_does_not_leak_eta_or_poison_shown_s failed with AssertionError: 4 not greater than or equal to 10.0 (shown_s captured 4.0 for a 30s recording)."
  falsification_test: "If chunk decoding during recording does not calculate or publish ETA, and if shown_s is only set on transition to transcribing, shown_s would accurately reflect the full-audio ETA instead of a 1s-4s chunk ETA."
  fix_rationale: "Ensuring ETAs remain None during recording (by returning early in _on_segment_yield when not capture_closed.is_set(), and enforcing eta fields are None in _publish_status when state in ('starting', 'recording')) prevents leaking chunk ETAs. Ensuring shown_s is only captured when state == 'transcribing' prevents any premature ETA capture."
  blind_spots: "Need to verify that mid-run ETA revisions after capture_closed is set still function properly when transcribing remaining chunks."
  candidate_causes:
    - "code: _on_segment_yield lacks capture_closed check and _publish_status lacks state == 'transcribing' gate for shown_s"
    - "data: chunks have audio_s=5.0 which produces small 1s-4s ETA values"
  and_gate: "no - code defect in _on_segment_yield and _publish_status is solely sufficient to trigger the leak whenever chunked background recording is active"

## Evidence
- timestamp: 2026-10-30 19:50 +06
  observation: Inspected voice.py:2349-2415 (_on_segment_yield). It computes remaining_s from single-chunk audio_s and calls _publish_status('transcribing', 'decode', ..., eta_remaining_s=disp['display_s']) without checking capture_closed.is_set().
- timestamp: 2026-10-30 19:50 +06
  observation: Inspected voice.py:2288-2300 (_publish_status). If pred.get('shown_s') is None and rem is not None, it unconditionally locks pred['shown_s'] = rem, without verifying that the state is 'transcribing'.
- timestamp: 2026-10-30 19:55 +06
  observation: Built reproduction test in tests/test_midrun_eta.py. Unpatched code failed with `AssertionError: 4.0 is not None : ETA leaked during recording state` and `AssertionError: 4 not greater than or equal to 10.0 : shown_s was poisoned with small chunk ETA: 4`.
- timestamp: 2026-10-30 20:00 +06
  observation: After fix, all 7 tests in tests/test_midrun_eta.py passed (0.17s) and full test suite of 262 tests passed (8.78s).

## Eliminated
- hypothesis: The ledger calculation or voice --report parsing itself mutates shown_s.
  reason: Code inspection proves shown_s is captured directly inside _publish_status in voice.py from the worker's status_state dict during chunk segment yielding.

## Resolution
- root_cause: In voice.py, when background chunk recording was introduced, `_consume()` invoked `transcribe_timed` on 5-second audio chunks with `on_segment_yield=_on_segment_yield`. `_on_segment_yield` lacked a `capture_closed.is_set()` check and computed an ETA for only that single chunk (~1s-4s), publishing status with `state='transcribing'` and `eta_remaining_s`. In `_publish_status`, `pred['shown_s']` captured the first non-null `eta_remaining_s` regardless of whether the state was still recording, locking in the 1s-4s prediction for the entire run and poisoning `predicted.shown_s` in the ledger.
- fix:
    1. In `_on_segment_yield`: Added guard `if not capture_closed.is_set(): return` so chunk segment decoding during recording does not compute or publish single-chunk ETAs.
    2. In `_publish_status`:
       - Enforced that when `state in ("starting", "recording")`, `deltas` for `eta_remaining_s`, `eta_epoch`, `eta_source`, and `eta_confidence` are forced to `None`, keeping ETAs None while recording.
       - Enforced that `pred['shown_s']` is only captured when `state == "transcribing"`.
    3. Moved `capture_closed.set()` in `run_background_recording()` immediately after the initial full-audio ETA `_publish_status("transcribing", "finalize", ...)` call, ensuring atomic ordering and eliminating any race before remaining chunks process segment revisions.
    4. Added `TestEtaLeakageDuringRecording` test suite to `tests/test_midrun_eta.py` covering:
       - No ETA leakage or `shown_s` poisoning during chunk recording.
       - Proper mid-run revision handling and `shown_s` preservation after `capture_closed.set()`.
- verification: Passed all 7 tests in `tests/test_midrun_eta.py` and all 262 tests in full test suite (`uv run python -m unittest discover -s tests`).
- oracle_type: specified
- files_changed:
    - voice.py
    - tests/test_midrun_eta.py
    - .planning/debug/fix-eta-prediction-leak.md
