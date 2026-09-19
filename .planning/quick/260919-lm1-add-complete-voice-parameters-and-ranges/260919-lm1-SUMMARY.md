---
id: "260919-lm1"
slug: "add-complete-voice-parameters-and-ranges"
status: complete
date: "2026-09-19"
description: "Add complete voice parameters and ranges list to README.md"
---

# Quick Task Summary: Add complete voice parameters and ranges list to README.md

## Accomplishments

1. **Parameters & Configuration Reference**:
   - Added a comprehensive parameters and ranges section at the very top of `README.md` right after the project summary and guide links.
   - Organized parameters across 6 distinct categories:
     - **Speech-to-Text (Whisper STT)**: model, device, compute type, language, beam size, VAD filter, allow download, max recording seconds.
     - **Text-to-Speech (TTS)**: backend, voice, speed, model path, voices path, language, trim, max characters, Hermes config.
     - **Audio Capture & Hardware**: input device, sample rate, save dir, list devices.
     - **Text Injection & Keystroke Typing**: output method, Wayland backend, type delay, pre-type delay, keep newlines, paste.
     - **Auditory Cues & Desktop Notifications**: beep toggle, volume, reminder interval, output device, notify, test beep.
     - **Control Commands & Operational Modes**: toggle, speak selection, speak text, stop TTS, status, kill, doctor, verify, JSON, export markdown, check, tts-check, list TTS voices, download assets, terminal mode, watch log, hotkey installers.
2. **Ranges & Defaults**:
   - Explicitly documented CLI flags, environment variables, default values, and valid input ranges / constraints (e.g., speed clamped to `[0.5, 2.0]`, volume in `[0.0, 1.0]`, non-negative millisecond delays, valid enums).
3. **Quick Reference Synchronization**:
   - Updated the quick reference section in `README.md` to link directly to the comprehensive table at the top.
