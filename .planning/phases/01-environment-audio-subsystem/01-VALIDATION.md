---
phase: "01"
slug: "environment-audio-subsystem"
status: draft
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-18"
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | CLI self-checks & python import smoke tests |
| **Config file** | none — self-contained verification commands |
| **Quick run command** | `voicemode --status` |
| **Full suite command** | `voicemode --check && voicemode --test-beep` |
| **Estimated runtime** | ~3 seconds |

---

## Sampling Rate

- **After every task commit:** Run `voicemode --status` (or `python -c "import voice"`)
- **After every plan wave:** Run `voicemode --check && voicemode --test-beep`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | ENV-01 | — | N/A | integration | `uv run python -c "import faster_whisper, kokoro_onnx, edge_tts, sounddevice"` | ✅ | ⬜ pending |
| 01-01-02 | 01 | 1 | ENV-01 | — | N/A | integration | `~/.local/bin/voicemode --help` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 2 | ENV-02 | — | N/A | integration | `voicemode --check` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 2 | ENV-02 | — | N/A | integration | `voicemode --test-beep` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `~/.local/bin/voicemode` launcher script (created in Plan 01)
- [ ] Model cache download check (`voicemode --check` verified in Plan 02)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PipeWire node name in pavucontrol/wpctl | ENV-02 | External GUI/mixer verification | Run `wpctl status` or `pavucontrol` while recording to confirm stream is labeled `voicemode`. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** verified 2026-09-18
