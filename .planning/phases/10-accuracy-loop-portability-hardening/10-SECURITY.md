---
phase: "10"
slug: "accuracy-loop-portability-hardening"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-11-02"
---

# Phase 10 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Local Filesystem Permissions | `$XDG_STATE_HOME/voice-stt/corpus/` (0700) and WAV files (0600) | Local audio clips, file descriptors |
| Subprocess Execution | Audio recording and wtype keystroke typing | PCM buffers, synthetic key events |
| Network Boundary | Zero network calls. Corpus capture is entirely local and offline | None (offline air-gapped execution) |
| External Hardware Command | `nvidia-smi` probing with strict 1.0s timeout | CLI query, GPU device metadata |
| Terminal & Browser Output | SVG tooltips and HTML report rendering | Sanitized metric strings |
| Filesystem Path Boundary | XDG runtime and state fallback directories (`/tmp/voice-stt-$UID/`) | Telemetry ledgers, state files |
| Documentation & Examples | Public specifications in `docs/telemetry.md` and `README.md` | Sanitized configuration examples |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-10-01 | Information Disclosure | `voicemode_telemetry:get_state_dir` | medium | mitigate | Enforce POSIX permissions 0700 via os.chmod on state_dir and 0600 on created files; embed os.getuid() in path (D-28) | closed |
| T-10-02 | Denial of Service | `voicemode_telemetry:capture_corpus_sample` | medium | mitigate | Strict 1 GB filesystem free-space check before writing; strict FIFO quotas (max 50 files / 100 MB) with inline pruning (D-02, D-27) | closed |
| T-10-03 | Information Disclosure | `voicemode_telemetry:capture_corpus_sample` | high | mitigate | Corpus capture is opt-in (default disabled); files stored with 0600 permissions; ledger records relative path only (`corpus/{filename}`); zero network calls (D-03) | closed |
| T-10-04 | Denial of Service | `voice:Recorder._write_chunk_file`, `voice:transcribe_timed` | high | mitigate | Catch OSError around all telemetry and status writes; fall back to in-memory float32 numpy array transcription in Recorder and transcribe_timed (D-29, D-30) | closed |
| T-10-05 | Denial of Service / Focus Stealing | `voicemode_telemetry:classify_outlier` | medium | mitigate | Outliers operate strictly under focus-safe policy: zero desktop toasts, zero audio beeps, zero window focus interactions (D-01) | closed |
| T-10-06 | Denial of Service | `voicemode_report:probe_hardware_backend` | medium | mitigate | Wrap external command in subprocess.run(..., timeout=1.0) with TimeoutExpired catch block; use ctranslate2 zero-overhead C API first (D-11) | closed |
| T-10-07 | Information Disclosure | `voice:run_doctor`, `voice:doctor_json` | low | mitigate | Restrict path reporting to standard directory names and permission octals; avoid logging full file lists or usernames (D-12, D-13) | closed |
| T-10-08 | Tampering / XSS | `voicemode_report:render_html_report` | high | mitigate | Sanitize all dynamic strings using html.escape() before inserting into SVG title attributes or HTML template tags (D-09) | closed |
| T-10-09 | Repudiation | Stratified Evaluation Protocol | medium | mitigate | Formalize stratified evaluation protocol with clear duration buckets (Short, Med, Long) and reproducible automated reference benchmark tests (D-14, D-15) | closed |
| T-10-10 | Information Disclosure | Public Documentation | low | mitigate | Use generic environment variable references ($XDG_STATE_HOME, ~/.local/state) in documentation examples and sanitize test fixtures | closed |

*Status: all 10 threats closed (threats_open: 0)*

---

## Accepted Risks Log

No accepted risks.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-02 | 10 | 10 | 0 | orchestrator |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-02
