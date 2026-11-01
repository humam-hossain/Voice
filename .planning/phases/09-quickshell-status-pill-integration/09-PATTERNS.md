# Phase 09: Quickshell Status Pill Integration — Pattern Map

## Files to Create / Modify

### Summary Table

| # | File | Role | Action | Closest Analog |
|---|------|------|--------|----------------|
| 1 | `.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml` | Service singleton — ingests `status.json`, computes multi-bar timers, exposes `openReport()` | **Modify** | Self (existing) + `MemoryStoragePill.qml` (pulse animation pattern) |
| 2 | `.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml` | Bar pill — renders glyphs, colors, timers, click interaction | **Modify** | Self (existing) + `NetworkPingPill.qml` (click-through) + `MemoryStoragePill.qml` (color-pulse) |
| 3 | `voice.py` | STT worker — fix `transcribed_audio_s` publishing during tail decode and typing states | **Modify** | Self (existing `_publish_status` pattern at L2326-2331) |
| 4 | `integrations/quickshell/Voice.qml` | Vendored reference copy | **Create** | `.dotfiles/restow/quickshell/.../Voice.qml` (direct mirror) |
| 5 | `integrations/quickshell/VoicePill.qml` | Vendored reference copy | **Create** | `.dotfiles/restow/quickshell/.../VoicePill.qml` (direct mirror) |
| 6 | `integrations/quickshell/README.md` | Documentation marking dotfiles as authoritative | **Create** | Other `README.md` in project (simple doc pattern) |

---

## File 1: `Voice.qml` (Service Singleton) — MODIFY

**Path:** `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml`
**Role:** Reactive data layer — reads filesystem state, computes derived properties, exposes API to pill
**Data flow:** `status.json` → `FileView` → `poll()` → reactive properties → `VoicePill.qml`

### Analog: Self (existing patterns to extend)

**Pattern 1: Duration Properties & `formatDuration()` helper** — Copy and extend for multi-bar timers.

```qml
// EXISTING (Voice.qml:42-61) — Pattern for property + formatting pairs
property int elapsedSeconds: 0
property real elapsedMs: 0
property string formattedDuration: "0:00"
property real startTime: 0
property real transcribedAudioSeconds: 0.0
property string formattedTranscribedDuration: "0:00"

function formatDuration(sec) {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
}
```

**Extend with:** `recordedAudioSeconds`, `formattedRecordedDuration`, `totalElapsedSeconds`, `formattedTotalDuration`. Follow the exact `property real X: 0.0` + `property string formattedX: "0:00"` pair pattern.

**Pattern 2: `updateDuration()` state branching** — Extend for frozen/ticking timer phases.

```qml
// EXISTING (Voice.qml:163-179)
function updateDuration() {
    if (overallState === "recording" || overallState === "speaking") {
        if (startTime <= 0) {
            const activePid = (overallState === "recording") ? sttPid : ttsPid;
            startTime = Math.min(Date.now(), recoverStartTime(activePid));
        }
        const diff = Math.max(0, Date.now() - startTime);
        elapsedMs = diff;
        const sec = Math.floor(diff / 1000);
        elapsedSeconds = sec;
        formattedDuration = formatDuration(sec);
    } else if (overallState === "transcribing" || overallState === "typing") {
        // Frozen at final recorded value
    } else if (overallState === "idle" && !typingLingerTimer.running) {
        resetDuration();
    }
}
```

**Extend with:** In `recording` branch, also update `formattedRecordedDuration = formattedDuration` and `totalElapsedSeconds`. In `transcribing`/`typing` branch, keep recorded frozen but tick `totalElapsedSeconds` via `Date.now() - startTime`.

**Pattern 3: `poll()` status payload parsing** — Extend to extract `report_path` and `audio_s`.

```qml
// EXISTING (Voice.qml:253-275) — Status JSON property extraction
if (st) {
    if (st.transcribed_audio_s !== undefined && st.transcribed_audio_s !== null && st.transcribed_audio_s > 0) {
        root.transcribedAudioSeconds = st.transcribed_audio_s;
        root.formattedTranscribedDuration = formatDuration(Math.floor(st.transcribed_audio_s));
    }
    // ... more property extractions
}
```

**Extend with:** Extract `st.audio_s` → `recordedAudioSeconds`; extract `st.report_path` → `statusReportPath`.

**Pattern 4: `resetDuration()` cleanup** — Extend to reset new properties.

```qml
// EXISTING (Voice.qml:127-138)
function resetDuration() {
    startTime = 0;
    elapsedMs = 0;
    elapsedSeconds = 0;
    formattedDuration = "0:00";
    transcribedAudioSeconds = 0.0;
    formattedTranscribedDuration = "0:00";
    // ...
}
```

**Pattern 5: `openReport()` function** — NEW function; follows `xdg-open` fallback from `NetworkPingPill.qml`.

### Analog: `NetworkPingPill.qml` (URL opening pattern)

```qml
// FROM NetworkPingPill.qml:43-46 — Click-to-open-URL pattern
onClicked: (mouse) => {
    if (mouse.button === Qt.LeftButton) {
        Quickshell.execDetached(["xdg-open", "http://127.0.0.1:8765/"]);
    }
}
```

### Analog: `NotificationItem.qml:71` — `Qt.openUrlExternally` pattern

```qml
// FROM NotificationItem.qml:71
Qt.openUrlExternally(extractedUrl);
```

**Combine into `openReport()` with path validation:**
```qml
function openReport() {
    const target = statusReportPath.length > 0 ? statusReportPath : defaultReportPath;
    if (target.startsWith(runtimeDir) && target.endsWith("report.html")) {
        const opened = Qt.openUrlExternally("file://" + target);
        if (!opened) {
            Quickshell.execDetached(["xdg-open", target]);
        }
    }
}
```

### Properties to Remove (ETA cleanup)

Remove: `etaRemainingSeconds`, `etaSource`, `etaOverrun`, `etaPillLabel` and all their usages in `poll()` and `resetDuration()`. These are replaced by the multi-bar timer system.

---

## File 2: `VoicePill.qml` (Bar Pill Component) — MODIFY

**Path:** `/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml`
**Role:** Visual presentation — renders state-dependent glyphs, colors, animations, click interaction
**Data flow:** `Voice.qml` properties → `VoicePill.qml` bindings → visual output

### Analog: Self (existing patterns to rewrite)

**Pattern 1: `currentColor` state switch** — Replace `Appearance.colors.colTertiary`/`colSecondary` with explicit hex constants.

```qml
// EXISTING (VoicePill.qml:37-47)
readonly property color currentColor: {
    switch (effectiveState) {
        case "recording": return Appearance.colors.colPrimary;
        case "transcribing": return Appearance.colors.colTertiary;
        case "typing": return Appearance.colors.colSecondary;
        case "speaking": return Appearance.colors.colSecondary;
        case "wrapup": return Appearance.colors.colSecondary;
        case "starting": return Appearance.colors.colPrimary;
        default: return Appearance.colors.colOnLayer1;
    }
}
```

**Replace with:** Sky Blue `#38bdf8` for transcribing, Neon Green `#4ade80` for typing/wrapup, and dual pulse color for concurrent decode during recording.

**Pattern 2: `displayText` state switch** — Replace static strings with multi-bar timer format.

```qml
// EXISTING (VoicePill.qml:50-66)
readonly property string displayText: {
    switch (effectiveState) {
        case "recording":
            return (Voice.transcribedAudioSeconds > 0)
                ? (Voice.formattedDuration + " | " + Voice.formattedTranscribedDuration)
                : Voice.formattedDuration;
        case "transcribing":
            return (Voice.etaPillLabel.length > 0)
                ? Voice.etaPillLabel
                : Translation.tr("Transcribing...");
        case "typing": return Translation.tr("Typing...");
        // ...
    }
}
```

**Replace with:** Dual timer for recording (`recorded | transcribed`), triple timer for transcribing/typing/wrapup (`recorded | transcribed | total`). No static strings.

**Pattern 3: `voiceIcon.text` glyph binding** — Currently hardcoded `"graphic_eq"`.

```qml
// EXISTING (VoicePill.qml:133)
text: "graphic_eq"
```

**Replace with:** State-dependent binding: `"graphic_eq"` for recording/transcribing, `"edit"` for typing/wrapup.

### Analog: `MemoryStoragePill.qml` — Color breathing pulse animation

```qml
// FROM MemoryStoragePill.qml:77-99 — Breathing pulse with opacity reset guard
SequentialAnimation {
    id: storagePulseAnimation
    running: root.storageCritical
    loops: 3
    onRunningChanged: {
        if (!running) {
            storageIcon.opacity = 1.0;
            storageCircProg.opacity = 1.0;
            storageText.opacity = 1.0;
        }
    }
    ParallelAnimation {
        NumberAnimation { target: storageIcon; property: "opacity"; to: 0.4; duration: 600; easing.type: Easing.InOutSine }
        // ...
    }
    ParallelAnimation {
        NumberAnimation { target: storageIcon; property: "opacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
        // ...
    }
}
```

**Adapt for:** Color pulse (not opacity pulse) alternating between `colPrimary` and Sky Blue `#38bdf8` during concurrent recording+transcribing. Use `SequentialAnimation on pulsedColor` with `ColorAnimation` instead of `NumberAnimation` on opacity.

### Analog: `NetworkPingPill.qml` — Interactive MouseArea with conditional click

```qml
// FROM NetworkPingPill.qml:34-51 — Interactive click-through pill
MouseArea {
    id: pillMouseArea
    parent: root
    anchors.fill: parent
    acceptedButtons: Qt.AllButtons
    cursorShape: Qt.PointingHandCursor
    hoverEnabled: true
    onClicked: (mouse) => {
        if (mouse.button === Qt.LeftButton) {
            Quickshell.execDetached(["xdg-open", "http://127.0.0.1:8765/"]);
        }
    }
}
```

**Adapt for:** Replace `inertMouseArea` with interactive `MouseArea`. Add conditional `cursorShape` based on `isClickable` state. Call `Voice.openReport()` on click.

### Analog: `StyledText.qml` — Number font auto-selection

```qml
// FROM StyledText.qml:12-20 — Number font conditional binding
property bool shouldUseNumberFont: /^\d+$/.test(root.text)
property var defaultFont: shouldUseNumberFont ? Appearance.font.family.numbers : Appearance.font.family.main

font {
    hintingPreference: Font.PreferDefaultHinting
    family: defaultFont
    pixelSize: Appearance?.font.pixelSize.small ?? 15
    variableAxes: shouldUseNumberFont ? ({}) : Appearance.font.variableAxes.main
}
```

**Note:** `StyledText` only detects all-digit strings via `/^\d+$/`. Timer strings like `0:08 | 0:05` fail this regex. The `voiceLabel` must explicitly override `font.family: Appearance.font.family.numbers` and set `font.features: { "tnum": 1 }` for tabular numeral rendering to prevent jitter.

### Layout Stability Analog: Existing `Behavior on implicitWidth`

```qml
// EXISTING (VoicePill.qml:70-73) — Width calculation
implicitWidth: vertical ? Appearance.sizes.baseVerticalBarWidth : (
    voiceIcon.implicitWidth + (isExpanded ? (voiceLabel.implicitWidth + 4) : 0) + padding * 2
)
```

The `Behavior on implicitWidth` with M3 easing already exists in the BarGroup base type (referenced at VoicePill.qml:141 in research). Stable width is ensured by tabular figures keeping digit widths constant.

---

## File 3: `voice.py` (STT Worker Status Publishing) — MODIFY

**Path:** `/home/pera/github_repo/Voice/voice.py`
**Role:** Backend worker — emits status telemetry during recording, transcription, and typing
**Data flow:** Worker thread → `_publish_status()` → `status.json` → Quickshell `FileView`

### Analog: Self — existing `_publish_status` call pattern

**Pattern 1: Tail decode missing `transcribed_audio_s`** — The `else` branch computes it but `if capture_closed.is_set()` does not.

```python
# EXISTING (voice.py:2314-2331) — BUG: transcribed_audio_s only in else branch
with results_lock:
    done = len(results)
if capture_closed.is_set():
    tot = total_chunks_holder["n"] or max(done, 1)
    _publish_status("transcribing", "decode", segments=tot, segments_done=done)
    #                                         ^^^ MISSING transcribed_audio_s!
else:
    with results_lock:
        transcribed_s = sum(
            r.audio_s for r in results.values()
            if r and getattr(r, "audio_s", None)
        )
    _publish_status(
        "recording", "capture",
        segments_done=done,
        transcribed_audio_s=transcribed_s,
    )
```

**Fix:** Hoist `transcribed_s` computation above the `if/else` branch so both paths pass `transcribed_audio_s=transcribed_s`.

**Pattern 2: Typing state missing `transcribed_audio_s` and `audio_s`**

```python
# EXISTING (voice.py:2499-2500) — Missing audio duration fields
write_pid_state(pid, "typing")
_publish_status("typing", "insert")
#                                  ^^^ MISSING transcribed_audio_s=d, audio_s=d
```

**Fix:** Pass `transcribed_audio_s=d, audio_s=d` where `d` is the total recorded audio duration, ensuring `transcribed_audio_s == audio_s` during typing (all audio fully decoded).

### Analog: `voicemode_telemetry.build_status()` contract

```python
# FROM voicemode_telemetry.py:513-515 — Status builder signature
def build_status(*, pid, run_id, state, phase, started_at, updated_at=None, expires_at=None,
                  audio_s=0.0, segments=0, segments_done=0, transcribed_audio_s=None,
                  report_path=None, **kwargs):
```

All fields already supported in the contract — no schema changes needed.

---

## File 4: `integrations/quickshell/Voice.qml` — CREATE

**Path:** `/home/pera/github_repo/Voice/integrations/quickshell/Voice.qml`
**Role:** Vendored reference copy
**Pattern:** Direct mirror of live dotfiles copy. No original code.

### Instructions
1. Create `integrations/quickshell/` directory
2. Copy final `Voice.qml` from `.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml`

---

## File 5: `integrations/quickshell/VoicePill.qml` — CREATE

**Path:** `/home/pera/github_repo/Voice/integrations/quickshell/VoicePill.qml`
**Role:** Vendored reference copy
**Pattern:** Direct mirror of live dotfiles copy. No original code.

### Instructions
1. Copy final `VoicePill.qml` from `.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml`

---

## File 6: `integrations/quickshell/README.md` — CREATE

**Path:** `/home/pera/github_repo/Voice/integrations/quickshell/README.md`
**Role:** Documentation marking the dotfiles as authoritative source

### Analog: Standard project README pattern

Brief markdown doc explaining:
- These are vendored reference copies
- The authoritative source is `~/.config/quickshell/` (symlinked from `/home/pera/github_repo/.dotfiles/restow/quickshell/`)
- Edit in dotfiles first, then copy here for version tracking

---

## Cross-Cutting Patterns

### QML Color Animation (used across multiple pills)

```qml
// FROM VoicePill.qml:137-143, MemoryStoragePill.qml:69-75
Behavior on color {
    ColorAnimation {
        duration: 200
        easing.type: Easing.BezierSpline
        easing.bezierCurve: Appearance.animationCurves.expressiveEffects
    }
}
```

### QML `onRunningChanged` Animation Safety Guard

```qml
// FROM MemoryStoragePill.qml:82-88, VoicePill.qml:152-154
onRunningChanged: {
    if (!running) voiceIcon.opacity = 1.0;
}
```

### Python `_publish_status()` Call Pattern

```python
# FROM voice.py:2171-2186 — Atomic status publishing wrapper
def _publish_status(state, phase, **deltas):
    try:
        if run_state.get("finalized"):
            return
        if not voicemode_telemetry.get_metrics_enabled():
            return
        with status_lock:
            s = dict(status_state)
            s.update(deltas)
            status_state.update(deltas)
        try:
            voicemode_telemetry.publish_status(voicemode_telemetry.build_status(**s, state=state, phase=phase))
        except Exception:
            pass
    except Exception:
        pass
```

### Python Test Pattern (for extending `test_status_contract.py`)

```python
# FROM tests/test_status_contract.py:29-48 — Status contract test pattern
class TestStatusContract(TempXdgTestCase):
    def test_schema_is_closed_and_sized(self):
        s = voicemode_telemetry.build_status(pid=123, run_id='r1', state='transcribing', phase='load',
                                            started_at=1.0, updated_at=1000.0, audio_s=1.0, segments=1,
                                            segments_done=0)
        self.assertEqual(tuple(s.keys()), tuple(voicemode_telemetry.STATUS_V1_KEYS))
```

### Font Configuration Tokens (from Quickshell Config)

```qml
// FROM Config.qml:112,115 — Available font families
property string numbers: "Google Sans Flex"
property string monospace: "JetBrains Mono NF"
```

Access via: `Appearance.font.family.numbers` or `Appearance.font.family.monospace`.

---

## Dependency Graph

```
voice.py (_publish_status fix)
    ↓ writes
status.json
    ↓ read by
Voice.qml (multi-bar timer computation, openReport)
    ↓ consumed by
VoicePill.qml (visual rendering, click handler)
    ↓ mirrored to
integrations/quickshell/ (vendored copies + README)
```

`voice.py` changes are upstream prerequisites — the QML timer display depends on correct `transcribed_audio_s` values being present in `status.json` across all states.
