# Phase 11: Voice Desktop Pop-up UI - Context

**Gathered:** 2026-11-02
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers a rich interactive Quickshell overlay popup for the voicemode desktop bar pill. The popup opens on hover (matching existing `StyledPopup` patterns from `CpuGpuPopup` and `MemoryStoragePopup`) and provides three integrated sections: a live state display showing real-time recording/transcription progress, an interactive configuration panel that persists settings to `~/.config/voicemode/config.json`, and a recent runs telemetry list with an "Open Full Report" button. Action buttons (Start Recording, Stop Recording, Cancel Recording) are always visible at the top. The popup is themed consistently with Material You tokens and the Phase 9 voice pill color identity (Sky Blue for STT, Neon Green for typing, Crimson for cancel/outliers). All content fits in a single window with only the recent runs section scrollable if needed.
</domain>

<decisions>
## Implementation Decisions

### Trigger & Invocation
- **D-01:** Popup opens on hover with 1000ms `StyledPopup` intent delay, matching the existing `CpuGpuPopup` and `MemoryStoragePopup` hover pattern. New hover triggers are blocked during active recording to prevent accidental mic disruption or focus loss. If the popup is already open when recording starts (via hotkey or Start button), it stays open showing live state updates. Closes on hover-out with the standard 200ms grace period. — **Reversibility:** reversible.
- **D-02:** Left-click on the pill no longer opens `report.html` directly (Phase 9 D-12 is superseded for click). The full HTML report is instead accessible via a prominent "Open Full Report" button inside the popup. — **Reversibility:** reversible.

### Action Buttons
- **D-03:** Three action buttons always visible at the top of the popup: Start Recording (green mic icon, invokes `voice --toggle`), Stop Recording, and Cancel Recording (invokes `voice --cancel`). Buttons are grayed/disabled when not applicable (Start grayed during recording, Stop/Cancel grayed when idle). — **Reversibility:** reversible.
- **D-04:** Button colors: Start Recording = Neon Green (`#4ade80`), Cancel Recording = Crimson (`#f43f5e`), Stop Recording = `colPrimary`. — **Reversibility:** reversible.

### Configuration Panel (Interactive, Persistent)
- **D-05:** Settings are written to `~/.config/voicemode/config.json` immediately on change. The new values are applied on the next `voice --toggle` (each toggle spawns a fresh detached worker process that reads config on startup). No restart or reload action needed. — **Reversibility:** costly — introduces a new persistent config file contract that `voice.py` must read and merge with CLI args and env vars.
- **D-06:** 12 configuration settings exposed in the popup:
  1. **STT Model** — Whisper model selector (tiny, tiny.en, base, base.en, small, small.en, medium, medium.en, large-v2, large-v3). Default: `medium.en`.
  2. **Device** — CPU / CUDA toggle. Default: `cpu`.
  3. **Compute Type** — int8 / float16 / float32. Default: `int8`.
  4. **Language** — `en` (forced English, faster) or auto-detect (empty/None, multilingual). Default: `en`.
  5. **Chunk Duration** — Audio chunk size in seconds for parallel processing. Default: `5` seconds.
  6. **Output Method** — Toggle between `type` (letter-by-letter keystroke injection) and `paste` (instant clipboard paste). Default: `type`.
  7. **Beam Size** — Whisper beam search width (1–5). Higher = better quality, slower. Default: `1`.
  8. **VAD Filter** — Silero Voice Activity Detection on/off. Trims silence before Whisper processing. Default: on.
  9. **Audio Cues (Beep)** — Recording start/stop/reminder tones on/off. Default: on.
  10. **TTS Voice** — Kokoro voice selector (af_heart, etc.). Default: `af_heart`.
  11. **TTS Backend** — kokoro / edge. Default: `kokoro`.
  12. **Corpus Capture** — none / outliers / all. Default: `none`.
  — **Reversibility:** reversible.

### Live State Display
- **D-07:** Top section shows real-time state during active recording/transcribing/typing: recorded duration, transcribed audio duration, total elapsed time, and character count. Updates live via `status.json` polling (existing `Voice.qml` FileView mechanism). When idle, shows data from the last completed run. — **Reversibility:** reversible.

### Recent Runs & Report
- **D-08:** Recent runs section displays up to 10 rows from `metrics.jsonl`. Each row shows: duration, character count, RTF (Real-Time Factor), and outcome indicator (✓ success, ✕ error, ⚠ outlier). Rows are purely informational (no click action). Full per-stage breakdown is available in the HTML report. — **Reversibility:** reversible.
- **D-09:** "Open Full Report" button at the bottom of the recent runs section opens `report.html` via `Qt.openUrlExternally`. — **Reversibility:** reversible.

### Layout & Scrolling
- **D-10:** Single popup window. Config section and live state display are fixed (never scroll). Only the recent runs section is scrollable if content overflows the available vertical space. No tabs. — **Reversibility:** reversible.

### Color Palette
- **D-11:** State colors carry forward from Phase 9: Sky Blue (`#38bdf8`) for STT/transcribing, Neon Green (`#4ade80`) for typing and Start button, Crimson (`#f43f5e`) for Cancel button and outlier markers, `colPrimary` for recording state and Stop button. Popup chrome (background, borders, text) matches existing `StyledPopup` style: dark surface container background (`m3surfaceContainerHigh`), `colOnSurface` text, subtle `colLayer0Border` borders. — **Reversibility:** reversible.

### The Agent's Discretion
- Exact popup width (likely 320px matching existing popups, or wider for the config panel).
- Config JSON schema structure and key naming in `~/.config/voicemode/config.json`.
- Config file merge priority (config.json vs env vars vs CLI args — recommend CLI > env > config file).
- How `voice.py` discovers and reads the config file (e.g., early in `parse_args()` as defaults).
- Recent runs row layout density and exact font sizing.
- Whether the Start/Stop/Cancel buttons are icon-only or icon+label.
- Exact scrollable area height threshold for the recent runs section.
- Reading `metrics.jsonl` from QML — whether via a helper script, `voice --report --json --last 10`, or direct FileView parsing.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone & Phase Scope
- `.planning/ROADMAP.md` — Phase 11 goal, requirements (POP-01, POP-02), and success criteria
- `.planning/REQUIREMENTS.md` — POP-01 and POP-02 specification (popup window and theme integration)

### Prior Phase Context (Critical)
- `.planning/phases/09-quickshell-status-pill-integration/09-CONTEXT.md` — VoicePill architecture, state colors (Sky Blue, Neon Green), timer display format, click-through report opener (D-12, now superseded by popup), FileView observer pattern
- `.planning/phases/10-accuracy-loop-portability-hardening/10-CONTEXT.md` — Outlier detection, corpus capture, doctor diagnostics, degraded fallback, `--doctor --json` contract for scripting and popup consumption

### Quickshell Live Components (Authoritative)
- `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml` — Voice singleton: state machine, FileView observers, poll(), formatDuration(), openReport()
- `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml` — Bar pill component: state colors, glyphs, click handling, pulse animation
- `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/StyledPopup.qml` — Popup base component: 1000ms hover intent, close grace period, LazyLoader, PopupWindow anchoring
- `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/CpuGpuPopup.qml` — Reference popup: fast-polling lifecycle, two-column layout, 320px sections
- `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/MemoryStoragePopup.qml` — Reference popup: memory tiers, storage drives, alert thresholds, progress bars

### Codebase & Telemetry Contracts
- `voice.py` — CLI argument definitions (lines 3998–4217), `parse_args()`, `toggle_background_recording()`, `cancel_recording()`, `run_background_recording()`, `load_model()`
- `voicemode_telemetry.py` — `read_ledger_rows()`, `build_record()`, `STATUS_V1_KEYS`, `ledger_health()`, metrics.jsonl schema
- `voicemode_report.py` — `render_json()` for structured report data, `report.html` generation

### Hyprland Keybindings
- `/home/pera/github_repo/.dotfiles/stow/hypr/.config/hypr/custom/keybinds.lua` — Voice hotkeys: SUPER+SHIFT+M (toggle), SUPER+CTRL+M (cancel), SUPER+T (speak selection)

### Vendored Integration References
- `integrations/quickshell/Voice.qml` — Vendored reference copy of Voice singleton
- `integrations/quickshell/VoicePill.qml` — Vendored reference copy of bar pill
- `integrations/quickshell/README.md` — Integration documentation
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `StyledPopup.qml`: Fully reusable popup base with 1000ms hover intent, 200ms close grace period, `LazyLoader`, `PopupWindow` anchoring, and background chrome. Voice popup extends this directly (same as CpuGpu and MemoryStorage).
- `Voice.qml` singleton: Already provides `overallState`, `sttState`, `formattedRecordedDuration`, `formattedTranscribedDuration`, `formattedTotalDuration`, `openReport()`, and `poll()`. Popup binds directly to these properties.
- `VoicePill.qml`: Contains `currentColor`, `displayText`, `effectiveState`, and the hover/click `MouseArea`. Needs wiring to host `VoicePopup` as a child (same pattern as `CpuGpuPill` → `CpuGpuPopup`).
- `CpuGpuPopup.qml` and `MemoryStoragePopup.qml`: Reference implementations for fast-polling lifecycle boost (`activeInspectorCount`), `ColumnLayout` with section cards, progress bars, and formatted metric rows.

### Established Patterns
- **Pill → Popup wiring:** `CpuGpuPill.qml` hosts `CpuGpuPopup { hoverTarget: root.hoverArea }` inside its `MouseArea`. Voice popup follows the same pattern.
- **Fast-polling lifecycle:** Popups increment `GlobalStates.activeInspectorCount` and service-specific fast-polling counters on `onActiveChanged`. Voice popup should increment Voice polling frequency when active.
- **Atomic file operations:** `voicemode_telemetry.py` uses `.tmp_*` + `os.replace()` for all JSON writes. Config file writes should follow the same pattern.
- **Process invocation from QML:** `Quickshell.Io.Process` can spawn `voice --toggle` and `voice --cancel` for action buttons.

### Integration Points
- `$XDG_RUNTIME_DIR/voice-stt/status.json` — Real-time state data read by `Voice.qml` FileView.
- `$XDG_STATE_HOME/voicemode/metrics.jsonl` — Telemetry ledger for recent runs data.
- `$XDG_RUNTIME_DIR/voice-stt/report.html` — Pre-rendered HTML report opened via button.
- `~/.config/voicemode/config.json` — New persistent config file (to be created by this phase).
- `voice.py:parse_args()` — Must be extended to read and merge config.json values as defaults.
</code_context>

<specifics>
## Specific Ideas
- Popup layout: Action buttons at top, live state card below, configuration panel in the middle, recent runs at the bottom with "Open Full Report" button.
- Chunk duration default changed to 5 seconds (from 180s code default).
- Output method presented as a clear type/paste toggle (the most frequently changed setting).
- Start button uses Neon Green with mic icon, Cancel uses Crimson — strong visual distinction.
- Config file location: `~/.config/voicemode/config.json` (XDG compliant).
- Recent runs show RTF and outlier markers using Crimson accent from Phase 10.
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---

*Phase: 11-Voice Desktop Pop-up UI*
*Context gathered: 2026-11-02*
