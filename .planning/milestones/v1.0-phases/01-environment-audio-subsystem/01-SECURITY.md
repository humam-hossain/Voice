---
phase: "01"
slug: "environment-audio-subsystem"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-09-18"
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| External Network / PyPI / Hugging Face -> Local Filesystem | Dependency resolution and AI model weight retrieval | Python wheels, CTranslate2 binary model weights |
| Desktop Shell / User Arguments -> Launcher Wrapper | Command line arguments forwarded to Python script | String arguments to `~/.local/bin/voicemode` |
| Microphone Input -> Local Audio Pipeline | Continuous microphone PCM capture and temporary disk caching | Raw audio PCM samples, temporary WAV files |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-01-01 | Tampering | Package Management | High | mitigate | Explicit dependencies in `pyproject.toml` via `uv` with PyPI index hash verification; no system `pacman` calls | closed |
| T-01-02 | Elevation of Privilege | Launcher Wrapper | Medium | mitigate | Strict `exec "$VENV_PYTHON" "$VOICE_SCRIPT" "$@"` execution with variable quoting, avoiding eval or unquoted expansion | closed |
| T-01-03 | Elevation of Privilege | Execution Context | High | mitigate | Execution strictly isolated to unprivileged desktop user space (`~/.local/bin` and `.venv`) | closed |
| T-01-04 | Denial of Service | Audio Capture Loop | Medium | mitigate | Hard 300-second (`MAX_RECORDING_SECONDS = 300.0`) ceiling in recording loop terminates runaway captures | closed |
| T-01-05 | Information Disclosure | Temporary Audio Files | Medium | mitigate | User-exclusive (0600) permissions on temporary WAV files with immediate cleanup in `finally` blocks | closed |
| T-01-06 | Tampering / Code Exec | Model Weights | High | mitigate | CTranslate2 native binary model format from official Hugging Face repository without Python pickle deserialization | closed |

---

## Accepted Risks Log

No accepted risks.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-18 | 6 | 6 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-18
