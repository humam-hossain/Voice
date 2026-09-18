---
phase: "03"
slug: "text-to-speech-model-asset-pipeline"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-19"
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python standard library `unittest` |
| **Config file** | none — standard discovery in `tests/` |
| **Quick run command** | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest discover tests` |
| **Full suite command** | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest discover tests && /home/pera/github_repo/Voice/.venv/bin/python voice.py --tts-check` |
| **Estimated runtime** | ~3 seconds |

---

## Sampling Rate

- **After every task commit:** Run `/home/pera/github_repo/Voice/.venv/bin/python -m unittest discover tests`
- **After every plan wave:** Run `/home/pera/github_repo/Voice/.venv/bin/python -m unittest discover tests && /home/pera/github_repo/Voice/.venv/bin/python voice.py --tts-check`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | TTS-01 | — | N/A | test stub | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_tts_pipeline.py` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | TTS-01 | — | Model asset integrity & safe download | unit / integration | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_tts_pipeline.py -k TestKokoroAssetManagement` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | TTS-01 | — | Offline verification and voice enumeration | CLI check | `/home/pera/github_repo/Voice/.venv/bin/python voice.py --tts-check` | ✅ | ⬜ pending |
| 03-02-01 | 02 | 1 | TTS-02 | — | ANSI, markdown, URL, code identifier normalization | unit | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_tts_pipeline.py -k TestTtsTextNormalization` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | TTS-02 | — | Primary selection reading, timeout guard, error chime | unit / integration | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_tts_pipeline.py -k TestWaylandSelectionCapture` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 2 | TTS-02 | — | Stream tagging and silent interruption lifecycle | unit / integration | `/home/pera/github_repo/Voice/.venv/bin/python -m unittest tests/test_tts_pipeline.py -k TestAudioPlaybackAndInterruption` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tts_pipeline.py` — test stubs for TTS-01 and TTS-02 (asset verification, text normalization, selection reading, and playback lifecycle)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Audible audio output via PipeWire | TTS-02 | Requires physical or virtual sound card output check | Run `voice.py --speak "Testing sound hardware"` and confirm clear audible speech |
| Desktop toast preview & notifications | TTS-02 | Requires visual inspection of desktop notification daemon | Trigger `voice.py --speak-selection` and observe toast notification |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
