# Phase 11: Voice Desktop Pop-up UI - Pattern Mapping

**Phase:** 11 — Voice Desktop Pop-up UI  
**Status:** Completed  
**Author:** GSD Pattern Mapper  
**Target Delivery:** Rich interactive Quickshell overlay popup for voice recording history, settings, and telemetry.  
**Requirement IDs:** POP-01, POP-02  

---

## 1. File Classification & Data Flow

| File | Path / Destination | Role | Classification | Data Flow (Inputs & Outputs) |
|---|---|---|---|---|
| **VoicePopup.qml** *(New)* | • `.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePopup.qml`<br>• `Voice/integrations/quickshell/VoicePopup.qml` | Desktop overlay popup component | UI Presentation / IPC Controller | **Inputs:** `Voice.qml` telemetry properties, `config.json` via `FileView`, `metrics.jsonl` via `FileView`, `Appearance` system tokens.<br>**Outputs:** `Quickshell.execDetached` for `voice --toggle` and `voice --cancel`, atomic `FileView.setText()` to `config.json`, `Voice.openReport()`. |
| **VoicePill.qml** *(Modified)* | • `.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/VoicePill.qml`<br>• `Voice/integrations/quickshell/VoicePill.qml` | Bar pill component | Bar UI Component / Popup Host | **Inputs:** `Voice.overallState`, user hover/click interactions.<br>**Outputs:** Hosts `VoicePopup` with conditional `hoverTarget` (gating hover when recording per D-01). Pill click no longer calls `Voice.openReport()` directly (D-02). |
| **voice.py** *(Modified)* | `Voice/voice.py` | CLI Argument Parser & Process Orchestrator | Core Python Engine / Daemon Runner | **Inputs:** `~/.config/voicemode/config.json`, environment variables (`VOICE_*`, `VOICEMODE_*`), CLI `argv`.<br>**Outputs:** Merged `argparse.Namespace` (`CLI > ENV > JSON > default`), `background_argv` worker flags, atomic `save_user_config()`. |
| **test_config.py** *(New)* | `Voice/tests/test_config.py` | Unit Test Suite | Hermetic Testing | **Inputs:** Mocked XDG environment, test JSON configurations.<br>**Outputs:** Pytest assertions on config paths, loading, saving, permissions (`0700`/`0600`), and precedence resolution. |
| **test_pill_integration_simulation.py** *(Modified)* | `Voice/tests/test_pill_integration_simulation.py` | Integration & Simulation Test Suite | Structural & Behavioral Testing | **Inputs:** QML source files (dotfiles and vendored), mock telemetry records.<br>**Outputs:** Pytest assertions verifying QML AST/regex rules, hover gating during recording, recent runs reverse JSONL parsing, and parity. |

---

## 2. Analog Matrix

| Target File | Closest Codebase Analog | File Path / Source Location | Why It Is the Closest Analog |
|---|---|---|---|
| **VoicePopup.qml** *(Structure & Lifecycle)* | `CpuGpuPopup.qml` & `MemoryStoragePopup.qml` | `restow/quickshell/.config/quickshell/ii/modules/ii/bar/CpuGpuPopup.qml`<br>`restow/quickshell/.config/quickshell/ii/modules/ii/bar/MemoryStoragePopup.qml` | Extends `StyledPopup`, uses `onActiveChanged` lifecycle hooks, fixed width `ColumnLayout` with header rows and value rows, Material You theming. |
| **VoicePopup.qml** *(Base Container)* | `StyledPopup.qml` | `restow/quickshell/.config/quickshell/ii/modules/ii/bar/StyledPopup.qml` | Foundational popup container with `LazyLoader`, `PanelWindow`, `WlrLayershell.layer: Overlay`, `margins` screen clamping math, `HoverHandler`, and entrance animations. |
| **VoicePopup.qml** *(Action Buttons)* | `RippleButtonWithIcon.qml` | `dots/.config/quickshell/ii/modules/common/widgets/RippleButtonWithIcon.qml` | Material-style interactive action button with icon, label, and ripple feedback. Perfect for Start, Stop, and Cancel buttons. |
| **VoicePopup.qml** *(Scrolling Runs List)* | `StyledFlickable.qml` & `StyledScrollBar.qml` | `dots/.config/quickshell/ii/modules/common/widgets/StyledFlickable.qml` | Smooth mouse wheel and touchpad scrollable container with dots-hyprland scrollbar styling. Enforces D-10 fixed layout with scrollable recent runs. |
| **VoicePopup.qml** *(Config Controls)* | `ConfigSelectionArray.qml`, `ConfigSwitch.qml`, `StyledComboBox.qml`, `StyledSpinBox.qml` | `dots/.config/quickshell/ii/modules/common/widgets/` | Standard dotfiles widgets for segmented selectors, boolean switches, dropdowns, and numeric spinners. |
| **VoicePill.qml** *(Popup Hosting)* | `CpuGpuPill.qml` | `restow/quickshell/.config/quickshell/ii/modules/ii/bar/CpuGpuPill.qml` | Lines 38–52 demonstrate how `MouseArea` hosts the popup and binds `hoverTarget` to `root.hoverArea`. |
| **voice.py** *(Config Management & Atomic I/O)* | `voicemode_telemetry.py` | `Voice/voicemode_telemetry.py` | Lines 24–50 (`get_state_dir`, `get_metrics_dir`) and lines 519–544 (`atomic_write_text`, `atomic_write_json`) provide robust XDG path resolution, permissions (`0700`/`0600`), and atomic replace semantics. |
| **tests/test_config.py** | `_hermetic.py` & `test_status_contract.py` | `Voice/tests/_hermetic.py`<br>`Voice/tests/test_status_contract.py` | Provides `TempXdgTestCase` for isolated environment testing, schema verification, and atomic file assertion patterns. |
| **tests/test_pill_integration_simulation.py** | `test_pill_integration_simulation.py` | `Voice/tests/test_pill_integration_simulation.py` | Existing test suite already contains QML AST/regex structural inspection, duration logic simulation, and process dispatch mocking. |

---

## 3. Per-File Pattern Assignments & Concrete Excerpts

### 3.1. `VoicePopup.qml` (New Component)

#### A. Imports & Base Declaration
Copy from `CpuGpuPopup.qml` [lines 1–10](file:///home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/CpuGpuPopup.qml#L1-L10):

```qml
pragma ComponentBehavior: Bound

import qs.modules.common
import qs.modules.common.widgets
import qs.services
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

StyledPopup {
    id: root

    // Fixed popup width (350px provides ample room for two-column labels and action buttons)
    property real popupWidth: 350
```

#### B. Dynamic Path Resolution & FileView Observers
Copy pattern from `Voice.qml` [lines 13–20, lines 69–89](file:///home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/services/Voice.qml#L13-L20):

```qml
    // Config & Metrics Paths (XDG-compliant with fallback)
    readonly property string configPath: {
        const xdg = Quickshell.env("XDG_CONFIG_HOME");
        const home = Quickshell.env("HOME") || "/home/pera";
        return (xdg && xdg.length > 0) ? (xdg + "/voicemode/config.json") : (home + "/.config/voicemode/config.json");
    }
    readonly property string metricsPath: {
        const xdg = Quickshell.env("XDG_STATE_HOME");
        const home = Quickshell.env("HOME") || "/home/pera";
        return (xdg && xdg.length > 0) ? (xdg + "/voicemode/metrics.jsonl") : (home + "/.local/state/voicemode/metrics.jsonl");
    }

    FileView {
        id: configFile
        path: root.configPath
        printErrors: false
        blockLoading: false
        onFileChanged: root.reloadConfig()
    }

    FileView {
        id: metricsFile
        path: root.metricsPath
        printErrors: false
        blockLoading: false
        onFileChanged: root.reloadMetrics()
    }
```

#### C. In-Memory Configuration State & Atomic Save
Follow Quickshell `FileViewWriter::write` pattern using `configFile.setText()`:

```qml
    property var userConfig: ({
        model: "medium.en",
        device: "cpu",
        compute_type: "int8",
        language: "en",
        chunk_duration: 5.0,
        output_method: "type",
        beam_size: 1,
        vad_filter: true,
        beep: true,
        tts_voice: "af_heart",
        tts_backend: "kokoro",
        capture_corpus: "none"
    })

    function reloadConfig() {
        try {
            const raw = configFile.text().trim();
            if (raw.length > 0) {
                const parsed = JSON.parse(raw);
                if (parsed && typeof parsed === "object") {
                    userConfig = Object.assign({}, userConfig, parsed);
                }
            }
        } catch (e) {
            console.warn("[VoicePopup] Failed to parse config.json: " + e);
        }
    }

    function saveConfigValue(key, val) {
        userConfig[key] = val;
        try {
            // Quickshell FileView.setText uses QSaveFile (atomic write + rename)
            configFile.setText(JSON.stringify(userConfig, null, 2));
        } catch (e) {
            console.warn("[VoicePopup] Failed to persist config: " + e);
        }
    }
```

#### D. Fast Reverse JSONL Parser (No Subprocess Overhead)
Copy reverse scanning pattern from RESEARCH.md:

```qml
    property list<var> recentRuns: []

    function reloadMetrics() {
        recentRuns = parseRecentRuns(metricsFile.text(), 10);
    }

    function parseRecentRuns(text, maxCount = 10) {
        if (!text || text.length === 0) return [];
        let runs = [];
        let end = text.length;
        while (end > 0 && runs.length < maxCount) {
            let start = text.lastIndexOf('\n', end - 1);
            let line = (start === -1 ? text.substring(0, end) : text.substring(start + 1, end)).trim();
            if (line.length > 0) {
                try {
                    let obj = JSON.parse(line);
                    if (obj && obj.schema === 1) {
                        const audioS = obj.audio_s || 0.0;
                        const decMs = (obj.actual && obj.actual.decode_ms) || 0.0;
                        const rtf = audioS > 0 ? (decMs / 1000.0 / audioS) : 0.0;
                        runs.push({
                            runId: obj.run_id || "",
                            duration: audioS.toFixed(1) + "s",
                            chars: (obj.chars_typed || obj.chars_out || 0) + " ch",
                            rtf: rtf.toFixed(2) + "x",
                            outlier: Boolean(obj.outlier),
                            outcome: obj.outcome || "unknown",
                            success: obj.outcome === "success"
                        });
                    }
                } catch (e) {}
            }
            if (start === -1) break;
            end = start;
        }
        return runs;
    }
```

#### E. Lifecycle Hook (Fresh Data on Popup Open)
Copy from `CpuGpuPopup.qml` [lines 16–24](file:///home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/CpuGpuPopup.qml#L16-L24):

```qml
    onActiveChanged: {
        if (active) {
            configFile.reload();
            metricsFile.reload();
            reloadConfig();
            reloadMetrics();
            Voice.poll();
        }
    }
```

#### F. Action Buttons Row (D-03, D-04)
Copy button structure from `RippleButtonWithIcon.qml` [lines 6–24](file:///home/pera/github_repo/.dotfiles/vendor/dots-hyprland/dots/.config/quickshell/ii/modules/common/widgets/RippleButtonWithIcon.qml#L6-L24):

```qml
    ColumnLayout {
        id: popupContent
        Layout.preferredWidth: root.popupWidth
        spacing: 10

        // 1. Action Buttons Row (Always Visible)
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            // Start Recording Button (Neon Green #4ade80)
            RippleButtonWithIcon {
                Layout.fillWidth: true
                materialIcon: "mic"
                mainText: "Start"
                enabled: Voice.overallState === "idle"
                colBackground: "#1e3a29"
                onClicked: Quickshell.execDetached(["voice", "--toggle"])
            }

            // Stop Recording Button (colPrimary)
            RippleButtonWithIcon {
                Layout.fillWidth: true
                materialIcon: "stop"
                mainText: "Stop"
                enabled: Voice.overallState === "recording"
                colBackground: Appearance.colors.colPrimaryContainer
                onClicked: Quickshell.execDetached(["voice", "--toggle"])
            }

            // Cancel Recording Button (Crimson #f43f5e)
            RippleButtonWithIcon {
                Layout.fillWidth: true
                materialIcon: "close"
                mainText: "Cancel"
                enabled: Voice.overallState === "recording" || Voice.overallState === "starting"
                colBackground: "#3e1820"
                onClicked: Quickshell.execDetached(["voice", "--cancel"])
            }
        }
```

#### G. Live State Display (D-07)
Copy row structure from `StyledPopupValueRow.qml` [lines 6–30](file:///home/pera/github_repo/.dotfiles/vendor/dots-hyprland/dots/.config/quickshell/ii/modules/ii/bar/StyledPopupValueRow.qml#L6-L30):

```qml
        // 2. Live State Card
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: liveCol.implicitHeight + 16
            radius: Appearance.rounding.small
            color: Appearance.m3colors.m3surfaceContainerHigh
            border.width: 1
            border.color: Appearance.colors.colLayer0Border

            ColumnLayout {
                id: liveCol
                anchors {
                    fill: parent
                    margins: 8
                }
                spacing: 4

                StyledPopupHeaderRow {
                    icon: "graphic_eq"
                    label: "Live Telemetry (" + Voice.overallState.toUpperCase() + ")"
                }

                StyledPopupValueRow {
                    Layout.fillWidth: true
                    icon: "timer"
                    label: "Recorded Duration:"
                    value: Voice.formattedRecordedDuration
                }

                StyledPopupValueRow {
                    Layout.fillWidth: true
                    icon: "speed"
                    label: "Transcribed Audio:"
                    value: Voice.formattedTranscribedDuration
                }

                StyledPopupValueRow {
                    Layout.fillWidth: true
                    icon: "schedule"
                    label: "Total Duration:"
                    value: Voice.formattedTotalDuration
                }

                StyledPopupValueRow {
                    Layout.fillWidth: true
                    icon: "notes"
                    label: "Characters:"
                    value: (root.recentRuns.length > 0 && Voice.overallState === "idle")
                           ? root.recentRuns[0].chars
                           : (Voice.overallState === "typing" ? "Typing..." : "--")
                }
            }
        }
```

#### H. Recent Runs Section with Scrollable Flickable & Report Button (D-08, D-09, D-10)
Copy from `StyledFlickable.qml` [lines 5–17](file:///home/pera/github_repo/.dotfiles/vendor/dots-hyprland/dots/.config/quickshell/ii/modules/common/widgets/StyledFlickable.qml#L5-L17):

```qml
        // 4. Recent Runs Section (Fixed Card with Scrollable Viewport)
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: runsCol.implicitHeight + 16
            radius: Appearance.rounding.small
            color: Appearance.m3colors.m3surfaceContainerHigh
            border.width: 1
            border.color: Appearance.colors.colLayer0Border

            ColumnLayout {
                id: runsCol
                anchors {
                    fill: parent
                    margins: 8
                }
                spacing: 6

                StyledPopupHeaderRow {
                    icon: "history"
                    label: "Recent Dictations"
                }

                // Scrollable container constrained to max 180px
                StyledFlickable {
                    Layout.fillWidth: true
                    Layout.maximumHeight: 180
                    implicitHeight: runsListView.contentHeight
                    clip: true
                    contentWidth: width
                    contentHeight: runsListView.implicitHeight

                    ColumnLayout {
                        id: runsListView
                        width: parent.width
                        spacing: 4

                        Repeater {
                            model: root.recentRuns
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 6

                                MaterialSymbol {
                                    text: modelData.success ? (modelData.outlier ? "warning" : "check_circle") : "error"
                                    iconSize: Appearance.font.pixelSize.small
                                    color: !modelData.success ? "#f43f5e" : (modelData.outlier ? "#f59e0b" : "#4ade80")
                                }

                                StyledText {
                                    text: modelData.duration
                                    font.pixelSize: Appearance.font.pixelSize.smaller
                                    color: Appearance.colors.colOnSurface
                                }

                                StyledText {
                                    text: modelData.chars
                                    font.pixelSize: Appearance.font.pixelSize.smaller
                                    color: Appearance.colors.colOnSurfaceVariant
                                }

                                Item { Layout.fillWidth: true }

                                StyledText {
                                    text: "RTF " + modelData.rtf
                                    font.pixelSize: Appearance.font.pixelSize.smaller
                                    font.family: Appearance.font.family.numbers
                                    color: modelData.outlier ? "#f43f5e" : Appearance.colors.colSubtext
                                }
                            }
                        }
                    }
                }

                // Open Full Report Button (D-02, D-09)
                RippleButtonWithIcon {
                    Layout.fillWidth: true
                    materialIcon: "open_in_new"
                    mainText: "Open Full Report"
                    colBackground: Appearance.colors.colLayer2
                    onClicked: Voice.openReport()
                }
            }
        }
```

---

### 3.2. `VoicePill.qml` (Modifications)

#### A. Anchor `VoicePopup` Inside `MouseArea`
Copy pattern from `CpuGpuPill.qml` [lines 39–52](file:///home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar/CpuGpuPill.qml#L39-L52):

```qml
    // Export hoverArea alias for popup anchoring
    readonly property alias hoverArea: pillMouseArea

    MouseArea {
        id: pillMouseArea
        parent: root
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true
        cursorShape: Qt.ArrowCursor

        // D-01: Gated popup anchoring.
        // Blocks new hover openings during active recording.
        // Stays open if already active when recording starts.
        VoicePopup {
            id: voicePopup
            hoverTarget: (Voice.overallState !== "recording" || active) ? pillMouseArea : null
        }
    }
```

#### B. Remove Direct Report Opening on Pill Click (D-02)
Replace old `pillMouseArea.onClicked` which called `Voice.openReport()` with inert click absorption or toggle:
```qml
        // D-02: Left click no longer opens report directly.
        // Report is opened via the "Open Full Report" button inside VoicePopup.
        onClicked: event => event.accepted = true
```

---

### 3.3. `voice.py` (Modifications)

#### A. Configuration Path Resolution & Atomic File I/O
Copy pattern from `voicemode_telemetry.py` [lines 24–50, lines 519–544](file:///home/pera/github_repo/Voice/voicemode_telemetry.py#L24-L50):

```python
def get_config_dir() -> Path:
    xdg = os.getenv("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    cfg_dir = base / "voicemode"
    try:
        cfg_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(cfg_dir, 0o700)
    except OSError:
        pass
    return cfg_dir


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def load_user_config() -> dict[str, Any]:
    cfg_path = get_config_path()
    if cfg_path.is_file():
        try:
            with cfg_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning(f"Failed to read user config from {cfg_path}: {e}")
    return {}


def save_user_config(data: dict[str, Any]) -> None:
    cfg_dir = get_config_dir()
    cfg_path = get_config_path()
    content = json.dumps(data, indent=2)
    # Reuse atomic_write_text pattern
    fd, tmp_path = tempfile.mkstemp(dir=cfg_dir, prefix=".tmp_config_")
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, cfg_path)
        tmp_path = None
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
```

#### B. Precedence Merging in `parse_args()`
Copy and extend `voice.py:parse_args()` [lines 4036–4215](file:///home/pera/github_repo/Voice/voice.py#L4036-L4215):

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    cfg = load_user_config()
    tts_defaults = load_hermes_tts_defaults()

    # Hierarchy: CLI argument > Environment Variable > config.json > Code Default

    # 1. STT Model
    model_default = os.getenv("VOICE_STT_MODEL") or cfg.get("model") or "medium.en"
    # 2. Device
    device_default = os.getenv("VOICE_STT_DEVICE") or cfg.get("device") or "cpu"
    # 3. Compute Type
    compute_default = os.getenv("VOICE_STT_COMPUTE_TYPE") or cfg.get("compute_type") or "int8"
    # 4. Language
    cfg_lang = cfg.get("language")
    if cfg_lang in ("auto", "", None):
        cfg_lang = None
    lang_default = os.getenv("VOICE_STT_LANGUAGE") if "VOICE_STT_LANGUAGE" in os.environ else (cfg_lang if "language" in cfg else "en")
    # 5. Chunk Duration (default 5.0 per D-06)
    cfg_chunk = cfg.get("chunk_duration", cfg.get("chunk_seconds", 5.0))
    chunk_default = float(os.getenv("VOICE_CHUNK_SECONDS", str(cfg_chunk)))
    # 6. Output Method
    output_default = os.getenv("VOICE_OUTPUT_METHOD") or cfg.get("output_method") or "type"
    # 7. Beam Size
    beam_default = int(os.getenv("VOICE_STT_BEAM_SIZE", str(cfg.get("beam_size", 1))))
    # 8. VAD Filter
    cfg_vad = cfg.get("vad_filter", True)
    vad_default = env_bool("VOICE_VAD_FILTER", cfg_vad)
    # 9. Audio Cues (Beep)
    cfg_beep = cfg.get("beep", True)
    beep_default = env_bool("VOICE_BEEP", cfg_beep)
    # 10. TTS Voice
    tts_voice_default = os.getenv("VOICE_TTS_VOICE") or cfg.get("tts_voice")
    # 11. TTS Backend
    tts_backend_default = os.getenv("VOICE_TTS_BACKEND") or cfg.get("tts_backend") or DEFAULT_TTS_BACKEND
    # 12. Corpus Capture
    cfg_corpus = cfg.get("capture_corpus", cfg.get("corpus_capture", "none"))
    corpus_default = os.getenv("VOICEMODE_CORPUS_CAPTURE", cfg_corpus)

    parser = argparse.ArgumentParser(...)
    ...
```

#### C. Argument Forwarding in `background_argv()`
Ensure all 12 settings are preserved when spawning the worker subprocess in `voice.py:background_argv()` [lines 2126–2161](file:///home/pera/github_repo/Voice/voice.py#L2126-L2161):

```python
def background_argv(args: argparse.Namespace) -> list[str]:
    argv = [sys.executable, str(Path(__file__).resolve()), "--record-background"]
    argv += ["--model", args.model]
    argv += ["--device", args.device]
    argv += ["--compute-type", args.compute_type]
    argv += ["--beam-size", str(args.beam_size)]
    if args.language:
        argv += ["--language", args.language]
    # Forward VAD filter
    argv.append("--vad-filter" if getattr(args, "vad_filter", True) else "--no-vad-filter")
    # Forward chunk seconds
    if getattr(args, "chunk_seconds", None) is not None:
        argv += ["--chunk-seconds", str(args.chunk_seconds)]
    # Forward corpus capture
    if getattr(args, "capture_corpus", None):
        argv += ["--capture-corpus", args.capture_corpus]
    # ...
    return argv
```

---

### 3.4. `tests/test_config.py` (New Test Suite)

#### Hermetic Configuration & Precedence Tests
Copy from `tests/_hermetic.py` [lines 19–54](file:///home/pera/github_repo/Voice/tests/_hermetic.py#L19-L54):

```python
from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from _hermetic import TempXdgTestCase
import voice


class TestUserConfig(TempXdgTestCase):
    def setUp(self):
        super().setUp()
        self.config_dir = self.xdg_root / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._cfg_patch = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config_dir)})
        self._cfg_patch.start()
        self.addCleanup(self._cfg_patch.stop)

    def test_get_config_path_respects_xdg_config_home(self):
        path = voice.get_config_path()
        self.assertEqual(path, self.config_dir / "voicemode" / "config.json")
        self.assertTrue(path.parent.is_dir())

    def test_save_and_load_user_config(self):
        cfg_data = {
            "model": "base.en",
            "device": "cpu",
            "compute_type": "int8",
            "chunk_duration": 5.0,
            "output_method": "paste",
        }
        voice.save_user_config(cfg_data)
        loaded = voice.load_user_config()
        self.assertEqual(loaded["model"], "base.en")
        self.assertEqual(loaded["output_method"], "paste")
        
        # Verify file permissions
        path = voice.get_config_path()
        mode = path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_precedence_hierarchy(self):
        # 1. Config file has "small.en"
        voice.save_user_config({"model": "small.en"})
        args = voice.parse_args([])
        self.assertEqual(args.model, "small.en")

        # 2. Env var overrides config file
        with patch.dict(os.environ, {"VOICE_STT_MODEL": "large-v3"}):
            args = voice.parse_args([])
            self.assertEqual(args.model, "large-v3")

        # 3. CLI flag overrides both
        with patch.dict(os.environ, {"VOICE_STT_MODEL": "large-v3"}):
            args = voice.parse_args(["--model", "tiny.en"])
            self.assertEqual(args.model, "tiny.en")
```

---

### 3.5. `tests/test_pill_integration_simulation.py` (Modifications)

#### A. Dotfiles and Vendored QML Parity
Copy from `test_pill_integration_simulation.py` [lines 366–375](file:///home/pera/github_repo/Voice/tests/test_pill_integration_simulation.py#L366-L375):

```python
    def test_voice_popup_and_pill_dotfiles_parity(self):
        """Verify VoicePopup.qml and VoicePill.qml match identically between .dotfiles and integrations."""
        files = ["VoicePopup.qml", "VoicePill.qml"]
        for fname in files:
            dotfiles_path = Path("/home/pera/github_repo/.dotfiles/restow/quickshell/.config/quickshell/ii/modules/ii/bar") / fname
            vendored_path = Path("integrations/quickshell") / fname
            self.assertTrue(dotfiles_path.is_file(), f"Missing dotfiles {dotfiles_path}")
            self.assertTrue(vendored_path.is_file(), f"Missing vendored {vendored_path}")
            dot_text = dotfiles_path.read_text(encoding="utf-8")
            ven_text = vendored_path.read_text(encoding="utf-8")
            self.assertEqual(dot_text, ven_text, f"{fname} differs between .dotfiles and integrations/quickshell")
```

#### B. Hover Gating During Active Recording (D-01)
Verify via regex/AST that `VoicePill.qml` contains the guarded `hoverTarget`:

```python
    def test_voice_pill_guards_hover_target_during_recording(self):
        """Verify VoicePill.qml blocks popup hover when overallState === 'recording' (D-01)."""
        pill_text = Path("integrations/quickshell/VoicePill.qml").read_text(encoding="utf-8")
        self.assertIn("VoicePopup", pill_text)
        self.assertTrue(
            re.search(r'hoverTarget:\s*\(Voice\.overallState\s*!==\s*"recording"\s*\|\|\s*active\)', pill_text) or
            re.search(r'hoverTarget:\s*\(Voice\.overallState\s*!==\s*"recording"\s*\|\|\s*voicePopup\.active\)', pill_text),
            "VoicePill must conditionally bind hoverTarget to block hover during active recording"
        )
```

#### C. Reverse JSONL Parser Python Simulation
Ensure the reverse reading logic correctly parses trailing records matching QML:

```python
    def test_recent_runs_reverse_jsonl_parsing_simulation(self):
        """Verify reverse JSONL parsing extracts last 10 runs without reading whole file."""
        lines = []
        for i in range(25):
            rec = {
                "schema": 1,
                "run_id": f"run_{i}",
                "audio_s": 4.0 + (i * 0.1),
                "actual": {"decode_ms": 800.0},
                "chars_typed": 50 + i,
                "outlier": (i % 7 == 0),
                "outcome": "success" if i % 10 != 0 else "error",
            }
            lines.append(json.dumps(rec))
        text = "\n".join(lines) + "\n"

        # Simulate reverse scan
        runs = []
        end = len(text)
        while end > 0 and len(runs) < 10:
            start = text.rfind('\n', 0, end - 1)
            line = text[start + 1:end].strip() if start != -1 else text[:end].strip()
            if line:
                obj = json.parse_like(line) # or json.loads
                runs.append(obj)
            if start == -1:
                break
            end = start

        self.assertEqual(len(runs), 10)
        self.assertEqual(runs[0]["run_id"], "run_24")
        self.assertEqual(runs[9]["run_id"], "run_15")
```

---

## 4. Pitfalls & Anti-Patterns to Avoid

| Pitfall | Warning Signs | Mitigation Strategy |
|---|---|---|
| **Altering `status.json` Schema** | Adding `chars_count` to `STATUS_V1_KEYS` fails `test_status_contract.py:34` (`tuple(s.keys()) == tuple(STATUS_V1_KEYS)`). | Keep `status.json` schema v1 strictly untouched. Display `"--"` or `"Typing..."` while active, and draw completed character counts from `metrics.jsonl` or last run. |
| **Spawning Subprocesses on Hover** | Calling `voice --report --json --last 10` adds 60–100ms lag on every popup opening. | Use Quickshell's asynchronous `FileView` and parse the trailing 10 lines in QML JavaScript via reverse string index search. |
| **Hover Theft During Recording** | Accidental cursor drift over the pill triggers popup window, causing focus flicker while user is dictating. | Bind `hoverTarget: (Voice.overallState !== "recording" || active) ? pillMouseArea : null` in `VoicePill.qml`. |
| **Dotfiles Drift** | Modifying only `integrations/quickshell/` or only `~/.dotfiles/` breaks live system or repository parity. | Always update both live dotfiles and vendored copies, and verify with `test_voice_popup_and_pill_dotfiles_parity`. |
| **Unsafe Command Execution** | Using `sh -c "voice --toggle"` opens shell injection vulnerabilities. | Always invoke via array parameters: `Quickshell.execDetached(["voice", "--toggle"])`. |
| **Oversized Popup Clipping** | Exceeding 700px in height causes clipping on 1080p displays. | Keep fixed sections compact and constrain the recent runs list to a `StyledFlickable` with `Layout.maximumHeight: 180` and `clip: true`. |

---

## 5. Verification Checklist

1. [ ] `VoicePopup.qml` created in `.dotfiles` and `integrations/quickshell/`.
2. [ ] `VoicePill.qml` updated in `.dotfiles` and `integrations/quickshell/` to host `VoicePopup` with hover gating.
3. [ ] `voice.py` implements `load_user_config()`, `save_user_config()`, and merges config in `parse_args()`.
4. [ ] `voice.py` forwards `--vad-filter`, `--chunk-seconds`, and `--capture-corpus` in `background_argv()`.
5. [ ] `tests/test_config.py` passes all unit tests for precedence hierarchy, permissions, and atomic I/O.
6. [ ] `tests/test_pill_integration_simulation.py` passes all QML structural checks and parity tests.
7. [ ] Entire test suite (`uv run pytest`) passes with 0 failures.
