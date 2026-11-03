pragma ComponentBehavior: Bound

import qs
import qs.modules.common
import qs.modules.common.widgets
import qs.services
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import Quickshell.Io

StyledPopup {
    id: root

    property real popupWidth: 350

    readonly property string voiceBin: {
        const home = Quickshell.env("HOME") || "/home/pera";
        return home + "/.local/bin/voice";
    }

    function toggleRecording() {
        Quickshell.execDetached([root.voiceBin, "--toggle"]);
    }

    function cancelRecording() {
        Quickshell.execDetached([root.voiceBin, "--cancel"]);
    }

    // State Colors & Dynamic Status Banner Mapping (Matching Bar Palette)
    readonly property color skyBlue: "#38bdf8"
    readonly property color neonGreen: "#4ade80"

    readonly property color stateColor: {
        switch (Voice.overallState) {
            case "recording": return Appearance.colors.colPrimary;
            case "transcribing": return root.skyBlue;
            case "typing": return root.neonGreen;
            case "speaking": return Appearance.colors.colSecondary;
            case "starting": return Appearance.colors.colPrimary;
            default: return Appearance.colors.colOnSurfaceVariant;
        }
    }

    readonly property string stateTitle: {
        switch (Voice.overallState) {
            case "recording": return "Recording";
            case "transcribing": return "Transcribing";
            case "typing": return "Typing";
            case "speaking": return "Speaking";
            case "starting": return "Starting";
            default: return "Idle";
        }
    }

    property real pulseOpacity: 1.0
    SequentialAnimation on pulseOpacity {
        running: Voice.overallState !== "idle"
        loops: Animation.Infinite
        NumberAnimation { to: 0.35; duration: 600; easing.type: Easing.InOutSine }
        NumberAnimation { to: 1.0; duration: 600; easing.type: Easing.InOutSine }
    }

    readonly property string configPath: {
        const xdg = Quickshell.env("XDG_CONFIG_HOME");
        const base = (xdg && xdg.length > 0) ? xdg : (Quickshell.env("HOME") + "/.config");
        return base + "/voicemode/config.json";
    }

    readonly property string metricsPath: {
        const xdg = Quickshell.env("XDG_STATE_HOME");
        const base = (xdg && xdg.length > 0) ? xdg : (Quickshell.env("HOME") + "/.local/state");
        return base + "/voicemode/metrics.jsonl";
    }

    readonly property FileView configFile: FileView {
        path: root.configPath
        printErrors: false
        blockLoading: true
        onFileChanged: root.reloadConfig()
    }

    readonly property FileView metricsFile: FileView {
        path: root.metricsPath
        printErrors: false
        blockLoading: true
        onFileChanged: root.reloadMetrics()
    }

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

    property var recentRuns: []

    readonly property var modelSpecs: ({
        "tiny": { params: "39M", disk: "~75 MB", ram: "~390 MB", desc: "Fastest STT, lowest resource footprint" },
        "tiny.en": { params: "39M", disk: "~75 MB", ram: "~390 MB", desc: "Fastest English-only STT" },
        "base": { params: "74M", disk: "~145 MB", ram: "~500 MB", desc: "Fast multilingual STT, good general accuracy" },
        "base.en": { params: "74M", disk: "~145 MB", ram: "~500 MB", desc: "Fast English STT, solid balance of speed & quality" },
        "small": { params: "244M", disk: "~480 MB", ram: "~1.0 GB", desc: "High accuracy multilingual model" },
        "small.en": { params: "244M", disk: "~480 MB", ram: "~1.0 GB", desc: "High accuracy English dictation" },
        "medium": { params: "769M", disk: "~1.5 GB", ram: "~2.6 GB", desc: "Near human-level multilingual accuracy" },
        "medium.en": { params: "769M", disk: "~1.5 GB", ram: "~2.6 GB", desc: "Production English dictation benchmark" },
        "large-v2": { params: "1550M", disk: "~3.1 GB", ram: "~4.7 GB", desc: "High-capacity legacy Whisper model" },
        "large-v3": { params: "1550M", disk: "~3.1 GB", ram: "~4.7 GB", desc: "Maximum accuracy across complex accents & noisy audio" },
        "large-v3-turbo": { params: "809M", disk: "~1.6 GB", ram: "~2.8 GB", desc: "Optimized high accuracy with 8x faster decoding speed" }
    })

    property var cachedModels: ({})
    property bool isDownloadingModel: false
    property string modelDownloadFeedback: ""
    property bool modelDownloadSuccess: true

    readonly property Process checkModelsProc: Process {
        id: checkModelsProc
        command: [root.voiceBin, "--models-info", "--json"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const parsed = JSON.parse(text.trim());
                    if (parsed && parsed.stt_models) {
                        const m = {};
                        for (let i = 0; i < parsed.stt_models.length; i++) {
                            const item = parsed.stt_models[i];
                            m[item.id] = Boolean(item.cached);
                        }
                        root.cachedModels = m;
                    }
                } catch (e) {
                    // ignore
                }
            }
        }
    }

    readonly property Process downloadModelProc: Process {
        id: downloadModelProc
        property string targetModel: ""
        command: [root.voiceBin, "--download-model", targetModel]
        onExited: (exitCode, exitStatus) => {
            root.isDownloadingModel = false;
            if (exitCode === 0) {
                root.modelDownloadSuccess = true;
                root.modelDownloadFeedback = "✓ Model '" + downloadModelProc.targetModel + "' is ready.";
                checkModelsProc.running = true;
            } else {
                root.modelDownloadSuccess = false;
                root.modelDownloadFeedback = "Download failed (code " + exitCode + "). Check connection.";
            }
        }
    }

    function downloadCurrentModel() {
        const m = root.userConfig.model || "medium.en";
        root.isDownloadingModel = true;
        root.modelDownloadFeedback = "Downloading & verifying " + m + "...";
        root.modelDownloadSuccess = true;
        downloadModelProc.targetModel = m;
        downloadModelProc.running = true;
    }

    function reloadConfig() {
        try {
            const raw = configFile.text().trim();
            if (raw.length > 0) {
                const parsed = JSON.parse(raw);
                if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                    userConfig = Object.assign({}, userConfig, parsed);
                }
            }
        } catch (e) {
            console.warn("[VoicePopup] Failed to parse config.json: " + e);
        }
    }

    function saveConfigValue(key, val) {
        const updated = Object.assign({}, userConfig);
        updated[key] = val;
        userConfig = updated;
        try {
            configFile.setText(JSON.stringify(updated, null, 2) + "\n");
        } catch (e) {
            console.warn("[VoicePopup] Failed to write config.json: " + e);
        }
    }

    function reloadMetrics() {
        try {
            const raw = metricsFile.text();
            recentRuns = parseRecentRuns(raw, 10);
        } catch (e) {
            recentRuns = [];
        }
    }

    function parseRecentRuns(text, maxCount) {
        if (!text || typeof text !== "string") return [];
        if (maxCount === undefined || maxCount === null) maxCount = 10;
        const lines = text.trim().split("\n");
        const result = [];
        for (let i = lines.length - 1; i >= 0 && result.length < maxCount; i--) {
            const line = lines[i].trim();
            if (!line) continue;
            try {
                const item = JSON.parse(line);
                if (!item || typeof item !== "object") continue;

                // Time formatting (e.g. "Nov 3, 2:35 PM")
                let timeStr = "--";
                if (item.ts_start) {
                    const d = new Date(item.ts_start * 1000);
                    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
                    let h = d.getHours();
                    const ampm = h >= 12 ? "PM" : "AM";
                    h = h % 12 || 12;
                    const mm = String(d.getMinutes()).padStart(2, "0");
                    timeStr = months[d.getMonth()] + " " + d.getDate() + ", " + h + ":" + mm + " " + ampm;
                }

                // Audio duration
                const audioSec = (item.audio_s !== undefined && item.audio_s !== null) ? Number(item.audio_s) : null;
                const durationStr = audioSec !== null ? (audioSec.toFixed(1) + "s") : "--";

                // Characters: support chars_out, chars_typed, chars, characters
                const charVal = (item.chars_out !== undefined && item.chars_out !== null)
                    ? item.chars_out
                    : ((item.chars_typed !== undefined && item.chars_typed !== null)
                        ? item.chars_typed
                        : ((item.chars !== undefined && item.chars !== null)
                            ? item.chars
                            : ((item.characters !== undefined && item.characters !== null) ? item.characters : null)));
                const charsStr = charVal !== null ? String(charVal) : "--";

                // RTF calculation
                let rtfVal = null;
                if (item.rtf !== undefined && item.rtf !== null) {
                    rtfVal = Number(item.rtf);
                } else if (item.actual && item.actual.decode_ms !== null && audioSec !== null && audioSec > 0) {
                    rtfVal = (Number(item.actual.decode_ms) / 1000.0) / audioSec;
                }
                const rtfStr = rtfVal !== null ? (rtfVal.toFixed(2) + "x") : "--";

                // Outcome / Status
                const outcome = item.outcome || (item.failed ? "failed" : "success");
                const isCancelled = outcome === "cancelled";
                const isFailed = outcome === "failed" || outcome === "error" || item.failed === true || Boolean(item.failure_reason);
                const isOutlier = Boolean(item.outlier || item.is_outlier);

                result.push({
                    runId: item.run_id || "",
                    time: timeStr,
                    duration: durationStr,
                    chars: charsStr,
                    rtf: rtfStr,
                    outlier: isOutlier,
                    isCancelled: isCancelled,
                    isFailed: isFailed,
                    success: !isCancelled && !isFailed,
                    outcome: outcome
                });
            } catch (e) {
                // gracefully skip corrupted entries
            }
        }
        return result;
    }

    onActiveChanged: {
        if (active) {
            configFile.reload();
            metricsFile.reload();
            root.reloadConfig();
            root.reloadMetrics();
            Voice.poll();
            checkModelsProc.running = true;
        }
    }

    Component.onCompleted: {
        root.reloadConfig();
        root.reloadMetrics();
        checkModelsProc.running = true;
    }

    // --- Custom reusable control components ---

    // Option chip with stable background and 2px primary border on hover
    component OptionChip: Rectangle {
        id: chip
        property string text: ""
        property bool selected: false
        signal clicked()

        implicitWidth: chipLabel.implicitWidth + 20
        implicitHeight: 30
        radius: Appearance.rounding.small

        color: chip.selected ? Appearance.colors.colPrimary : Appearance.colors.colLayer2
        border.width: chipArea.containsMouse ? 2 : (chip.selected ? 0 : 1)
        border.color: chipArea.containsMouse ? Appearance.colors.colPrimary : Appearance.colors.colOutlineVariant

        StyledText {
            id: chipLabel
            anchors.centerIn: parent
            text: chip.text
            font.pixelSize: Appearance.font.pixelSize.small
            font.weight: chip.selected ? Font.DemiBold : Font.Normal
            color: chip.selected ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer2
        }

        MouseArea {
            id: chipArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chip.clicked()
        }
    }

    // Model option chip with title and concise parameter tag
    component ModelOptionChip: Rectangle {
        id: mChip
        property string text: ""
        property string subText: ""
        property bool selected: false
        signal clicked()

        implicitWidth: Math.max(76, chipCol.implicitWidth + 12)
        implicitHeight: 38
        radius: Appearance.rounding.small

        color: mChip.selected ? Appearance.colors.colPrimary : Appearance.colors.colLayer2
        border.width: chipArea.containsMouse ? 2 : (mChip.selected ? 0 : 1)
        border.color: chipArea.containsMouse ? Appearance.colors.colPrimary : Appearance.colors.colOutlineVariant

        ColumnLayout {
            id: chipCol
            anchors.centerIn: parent
            spacing: 1

            StyledText {
                text: mChip.text
                Layout.alignment: Qt.AlignHCenter
                font.pixelSize: Appearance.font.pixelSize.small
                font.weight: mChip.selected ? Font.DemiBold : Font.Normal
                color: mChip.selected ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer2
            }

            StyledText {
                visible: mChip.subText.length > 0
                text: mChip.subText
                Layout.alignment: Qt.AlignHCenter
                font.pixelSize: Appearance.font.pixelSize.smaller - 1
                font.family: Appearance.font.family.numbers
                opacity: mChip.selected ? 0.9 : 0.65
                color: mChip.selected ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer2
            }
        }

        MouseArea {
            id: chipArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: mChip.clicked()
        }
    }

    component ConfigSwitchRow: RowLayout {
        id: switchRow
        property string label: ""
        property bool checked: false
        signal toggled(bool val)
        Layout.fillWidth: true
        spacing: 12
        StyledText {
            text: switchRow.label
            font.pixelSize: Appearance.font.pixelSize.small
            font.weight: Font.Medium
            color: Appearance.colors.colOnSurface
            Layout.preferredWidth: 125
        }
        StyledSwitch {
            checked: switchRow.checked
            onToggled: switchRow.toggled(checked)
        }
        Item { Layout.fillWidth: true }
    }

    component ConfigSelectorRow: RowLayout {
        id: selRow
        property string label: ""
        property var options: []
        property var currentVal: ""
        signal selected(var val)
        Layout.fillWidth: true
        spacing: 12
        StyledText {
            text: selRow.label
            font.pixelSize: Appearance.font.pixelSize.small
            font.weight: Font.Medium
            color: Appearance.colors.colOnSurface
            Layout.preferredWidth: 125
        }
        RowLayout {
            spacing: 6
            Repeater {
                model: selRow.options
                delegate: OptionChip {
                    required property var modelData
                    text: String(modelData)
                    selected: selRow.currentVal === modelData
                    onClicked: selRow.selected(modelData)
                }
            }
        }
        Item { Layout.fillWidth: true }
    }

    // Inline 3-row grid for STT models: strictly preserves 2-column alignment
    component ConfigModelGridRow: RowLayout {
        id: modelGrid
        property string label: "STT Model"
        property var currentVal: ""
        signal selected(var val)
        Layout.fillWidth: true
        spacing: 12

        StyledText {
            text: modelGrid.label
            font.pixelSize: Appearance.font.pixelSize.small
            font.weight: Font.Medium
            color: Appearance.colors.colOnSurface
            Layout.preferredWidth: 125
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: 6
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: ["tiny", "tiny.en", "base", "base.en"]
                    delegate: ModelOptionChip {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
                        subText: (root.modelSpecs[modelData] ? root.modelSpecs[modelData].params : "")
                        selected: modelGrid.currentVal === modelData
                        onClicked: modelGrid.selected(modelData)
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: ["small", "small.en", "medium", "medium.en"]
                    delegate: ModelOptionChip {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
                        subText: (root.modelSpecs[modelData] ? root.modelSpecs[modelData].params : "")
                        selected: modelGrid.currentVal === modelData
                        onClicked: modelGrid.selected(modelData)
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: ["large-v2", "large-v3", "large-v3-turbo"]
                    delegate: ModelOptionChip {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
                        subText: (root.modelSpecs[modelData] ? root.modelSpecs[modelData].params : "")
                        selected: modelGrid.currentVal === modelData
                        onClicked: modelGrid.selected(modelData)
                    }
                }
                Item { Layout.fillWidth: true }
            }
        }
    }

    // Inline 3-row grid for TTS voices: strictly preserves 2-column alignment
    component ConfigVoiceGridRow: RowLayout {
        id: voiceGrid
        property string label: "TTS Voice"
        property var currentVal: ""
        signal selected(var val)
        Layout.fillWidth: true
        spacing: 12

        StyledText {
            text: voiceGrid.label
            font.pixelSize: Appearance.font.pixelSize.small
            font.weight: Font.Medium
            color: Appearance.colors.colOnSurface
            Layout.preferredWidth: 125
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: 6
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: ["af_heart", "af_bella", "af_nicole", "af_sky"]
                    delegate: OptionChip {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
                        selected: voiceGrid.currentVal === modelData
                        onClicked: voiceGrid.selected(modelData)
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: ["bf_emma", "bf_isabella", "am_adam", "am_michael"]
                    delegate: OptionChip {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
                        selected: voiceGrid.currentVal === modelData
                        onClicked: voiceGrid.selected(modelData)
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: ["bm_george", "bm_lewis"]
                    delegate: OptionChip {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
                        selected: voiceGrid.currentVal === modelData
                        onClicked: voiceGrid.selected(modelData)
                    }
                }
                Item { Layout.fillWidth: true }
                Item { Layout.fillWidth: true }
            }
        }
    }

    component ConfigNumberRow: RowLayout {
        id: numRow
        property string label: ""
        property real minVal: 1
        property real maxVal: 30
        property real step: 1
        property real currentVal: 1
        property string unit: ""
        signal changed(real val)
        Layout.fillWidth: true
        spacing: 12

        StyledText {
            text: numRow.label
            font.pixelSize: Appearance.font.pixelSize.small
            font.weight: Font.Medium
            color: Appearance.colors.colOnSurface
            Layout.preferredWidth: 125
        }

        RowLayout {
            spacing: 6

            Rectangle {
                implicitWidth: 32
                implicitHeight: 32
                radius: Appearance.rounding.small
                color: Appearance.colors.colLayer2
                border.width: minusArea.containsMouse ? 2 : 1
                border.color: minusArea.containsMouse ? Appearance.colors.colPrimary : Appearance.colors.colOutlineVariant

                MaterialSymbol {
                    anchors.centerIn: parent
                    text: "remove"
                    iconSize: 18
                    color: Appearance.colors.colOnLayer2
                }

                MouseArea {
                    id: minusArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        const n = Math.max(numRow.minVal, numRow.currentVal - numRow.step);
                        numRow.changed(n);
                    }
                }
            }

            Rectangle {
                implicitWidth: 54
                implicitHeight: 32
                radius: Appearance.rounding.small
                color: Appearance.colors.colLayer1
                border.width: 1
                border.color: Appearance.colors.colOutlineVariant

                StyledText {
                    anchors.centerIn: parent
                    text: String(numRow.currentVal) + (numRow.unit.length > 0 ? numRow.unit : "")
                    font.pixelSize: Appearance.font.pixelSize.small
                    font.family: Appearance.font.family.numbers
                    font.weight: Font.DemiBold
                    color: Appearance.colors.colOnLayer1
                }
            }

            Rectangle {
                implicitWidth: 32
                implicitHeight: 32
                radius: Appearance.rounding.small
                color: Appearance.colors.colLayer2
                border.width: plusArea.containsMouse ? 2 : 1
                border.color: plusArea.containsMouse ? Appearance.colors.colPrimary : Appearance.colors.colOutlineVariant

                MaterialSymbol {
                    anchors.centerIn: parent
                    text: "add"
                    iconSize: 18
                    color: Appearance.colors.colOnLayer2
                }

                MouseArea {
                    id: plusArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        const n = Math.min(numRow.maxVal, numRow.currentVal + numRow.step);
                        numRow.changed(n);
                    }
                }
            }
        }
        Item { Layout.fillWidth: true }
    }

    component TelemetryRow: RowLayout {
        id: tRow
        property string label: ""
        property string value: ""
        Layout.fillWidth: true
        StyledText {
            text: tRow.label
            font.pixelSize: Appearance.font.pixelSize.small
            font.weight: Font.Medium
            color: Appearance.colors.colOnSurface
        }
        Item { Layout.fillWidth: true }
        StyledText {
            text: tRow.value
            font.pixelSize: Appearance.font.pixelSize.small
            font.family: Appearance.font.family.numbers
            font.weight: Font.DemiBold
            color: Appearance.colors.colPrimary
        }
    }

    contentItem: Item {
        id: contentRoot
        anchors.centerIn: parent

        readonly property var popupScreen: contentRoot.QsWindow?.window?.screen ?? root.hoverTarget?.QsWindow?.window?.screen ?? null
        readonly property real sw: (popupScreen && popupScreen.width > 0) ? popupScreen.width : 1920
        readonly property real calculatedWidth: Math.min(1060, Math.max(840, Math.round(sw * 0.50)))

        implicitWidth: calculatedWidth
        implicitHeight: mainLayout.implicitHeight

        ColumnLayout {
            id: mainLayout
            anchors.fill: parent
            spacing: 12

            // Top Status Banner: Concise 1-word status with matching bar color and breathing pulse
            Rectangle {
                id: statusBanner
                Layout.fillWidth: true
                radius: Appearance.rounding.small
                color: Appearance.m3colors.m3surfaceContainerHigh
                border.width: 1
                border.color: Appearance.colors.colLayer0Border
                implicitHeight: 46

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 10

                    MaterialSymbol {
                        iconSize: 22
                        text: (Voice.overallState === "typing") ? "edit" :
                              (Voice.overallState === "speaking" ? "volume_up" :
                              (Voice.overallState === "transcribing" ? "hourglass_top" : "graphic_eq"))
                        color: root.stateColor
                        opacity: (Voice.overallState !== "idle") ? root.pulseOpacity : 1.0
                    }

                    StyledText {
                        text: root.stateTitle
                        font.pixelSize: Appearance.font.pixelSize.normal
                        font.weight: Font.DemiBold
                        color: root.stateColor
                    }

                    Item { Layout.fillWidth: true }

                    // Pure duration display without 5-minute cap or verbose prefixes
                    StyledText {
                        visible: Voice.overallState !== "idle"
                        text: Voice.overallState === "recording"
                            ? Voice.formattedRecordedDuration
                            : (Voice.overallState === "transcribing"
                                ? Voice.formattedTranscribedDuration
                                : (Voice.overallState === "typing"
                                    ? Voice.formattedRecordedDuration
                                    : Voice.formattedTotalDuration))
                        font.pixelSize: Appearance.font.pixelSize.small
                        font.family: Appearance.font.family.numbers
                        font.weight: Font.DemiBold
                        color: root.stateColor
                    }
                }
            }

            // Action Buttons Row (Unified Toggle Button + Cancel Button)
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                readonly property bool isRecording: Voice.overallState === "recording" || Voice.overallState === "starting"
                readonly property bool isBusy: Voice.overallState === "transcribing" || Voice.overallState === "typing" || Voice.overallState === "speaking"

                RippleButtonWithIcon {
                    id: toggleBtn
                    Layout.fillWidth: true
                    mainText: parent.isRecording ? "Stop" : "Start"
                    materialIcon: parent.isRecording ? "stop" : "mic"
                    colBackground: parent.isRecording ? Appearance.colors.colPrimaryContainer : (parent.isBusy ? Appearance.colors.colLayer2 : "#1e3a29")
                    enabled: !parent.isBusy && (parent.isRecording || Voice.overallState === "idle")
                    opacity: enabled ? 1.0 : 0.5
                    mainContentComponent: Component {
                        StyledText {
                            text: toggleBtn.parent.isRecording ? "Stop" : "Start"
                            font.pixelSize: Appearance.font.pixelSize.small
                            font.weight: Font.DemiBold
                            color: toggleBtn.parent.isRecording ? Appearance.colors.colPrimary : (toggleBtn.parent.isBusy ? Appearance.colors.colOnSurfaceVariant : "#4ade80")
                        }
                    }
                    onClicked: {
                        if (parent.isRecording || Voice.overallState === "idle") {
                            root.toggleRecording();
                        }
                    }
                }

                RippleButtonWithIcon {
                    id: cancelBtn
                    Layout.preferredWidth: 140
                    mainText: "Cancel"
                    materialIcon: "close"
                    colBackground: "#3e1820"
                    enabled: parent.isRecording
                    opacity: enabled ? 1.0 : 0.4
                    mainContentComponent: Component {
                        StyledText {
                            text: "Cancel"
                            font.pixelSize: Appearance.font.pixelSize.small
                            font.weight: Font.Medium
                            color: "#f43f5e"
                        }
                    }
                    onClicked: {
                        root.cancelRecording();
                    }
                }
            }

            // Body: Side-by-Side Two Column Layout
            RowLayout {
                Layout.fillWidth: true
                spacing: 14

                // Left Column: Live Telemetry + Recent Dictations + Open Full Report
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 400
                    Layout.alignment: Qt.AlignTop
                    spacing: 12

                    // Card: Live State Display
                    Rectangle {
                        id: liveCard
                        Layout.fillWidth: true
                        radius: Appearance.rounding.small
                        color: Appearance.m3colors.m3surfaceContainerHigh
                        border.width: 1
                        border.color: Appearance.colors.colLayer0Border
                        implicitHeight: liveCol.implicitHeight + 20

                        ColumnLayout {
                            id: liveCol
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                MaterialSymbol {
                                    text: "analytics"
                                    iconSize: 18
                                    color: Appearance.colors.colPrimary
                                }
                                StyledText {
                                    text: "Live Telemetry"
                                    font.pixelSize: Appearance.font.pixelSize.normal
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colPrimary
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: Appearance.colors.colLayer0Border
                                }
                            }

                            TelemetryRow {
                                label: "Recorded Duration"
                                value: Voice.formattedRecordedDuration
                            }

                            TelemetryRow {
                                label: "Transcribed Audio"
                                value: Voice.formattedTranscribedDuration
                            }

                            TelemetryRow {
                                label: "Total Duration"
                                value: Voice.formattedTotalDuration
                            }

                            TelemetryRow {
                                label: "Characters"
                                value: {
                                    if (Voice.overallState !== "idle") {
                                        return Voice.liveCharsOut > 0 ? String(Voice.liveCharsOut) : "0";
                                    }
                                    if (root.recentRuns.length > 0 && root.recentRuns[0].chars !== "--") {
                                        return root.recentRuns[0].chars;
                                    }
                                    return "--";
                                }
                            }
                        }
                    }

                    // Card: Recent Dictations & Report Section
                    Rectangle {
                        id: recentCard
                        Layout.fillWidth: true
                        radius: Appearance.rounding.small
                        color: Appearance.m3colors.m3surfaceContainerHigh
                        border.width: 1
                        border.color: Appearance.colors.colLayer0Border
                        implicitHeight: recentCol.implicitHeight + 20

                        ColumnLayout {
                            id: recentCol
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                MaterialSymbol {
                                    text: "history"
                                    iconSize: 18
                                    color: Appearance.colors.colPrimary
                                }
                                StyledText {
                                    text: "Recent Dictations"
                                    font.pixelSize: Appearance.font.pixelSize.normal
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colPrimary
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: Appearance.colors.colLayer0Border
                                }
                            }

                            // Table Column Headers
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Layout.topMargin: 2

                                StyledText {
                                    text: "Time"
                                    font.pixelSize: Appearance.font.pixelSize.small
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colOnSurfaceVariant
                                    Layout.preferredWidth: 125
                                }
                                StyledText {
                                    text: "Audio"
                                    font.pixelSize: Appearance.font.pixelSize.small
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colOnSurfaceVariant
                                    Layout.preferredWidth: 54
                                }
                                StyledText {
                                    text: "Chars"
                                    font.pixelSize: Appearance.font.pixelSize.small
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colOnSurfaceVariant
                                    Layout.preferredWidth: 52
                                }
                                StyledText {
                                    text: "RTF"
                                    font.pixelSize: Appearance.font.pixelSize.small
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colOnSurfaceVariant
                                    Layout.preferredWidth: 52
                                }
                                Item { Layout.fillWidth: true }
                                StyledText {
                                    text: "Status"
                                    font.pixelSize: Appearance.font.pixelSize.small
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colOnSurfaceVariant
                                    Layout.preferredWidth: 70
                                    horizontalAlignment: Text.AlignRight
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                height: 1
                                color: Appearance.colors.colLayer0Border
                            }

                            StyledFlickable {
                                id: recentFlickable
                                Layout.fillWidth: true
                                clip: true
                                Layout.maximumHeight: 320
                                implicitHeight: Math.min(320, Math.max(80, recentListCol.implicitHeight))
                                contentWidth: width
                                contentHeight: recentListCol.implicitHeight

                                ColumnLayout {
                                    id: recentListCol
                                    width: parent.width
                                    spacing: 6

                                    StyledText {
                                        visible: root.recentRuns.length === 0
                                        text: "No recent runs found."
                                        font.pixelSize: Appearance.font.pixelSize.small
                                        color: Appearance.colors.colSubtext
                                        Layout.alignment: Qt.AlignHCenter
                                    }

                                    Repeater {
                                        model: root.recentRuns
                                        delegate: RowLayout {
                                            id: runRow
                                            required property var modelData
                                            Layout.fillWidth: true
                                            spacing: 8

                                            // Time
                                            StyledText {
                                                text: runRow.modelData.time
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                font.family: Appearance.font.family.numbers
                                                color: Appearance.colors.colOnSurface
                                                Layout.preferredWidth: 125
                                            }

                                            // Audio Duration
                                            StyledText {
                                                text: runRow.modelData.duration
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                font.family: Appearance.font.family.numbers
                                                font.weight: Font.Medium
                                                color: Appearance.colors.colOnSurface
                                                Layout.preferredWidth: 54
                                            }

                                            // Chars
                                            StyledText {
                                                text: runRow.modelData.chars
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                font.family: Appearance.font.family.numbers
                                                color: Appearance.colors.colOnSurface
                                                Layout.preferredWidth: 52
                                            }

                                            // RTF
                                            StyledText {
                                                text: runRow.modelData.rtf
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                font.family: Appearance.font.family.numbers
                                                font.weight: Font.Medium
                                                color: runRow.modelData.outlier ? "#f59e0b" : Appearance.colors.colOnSurface
                                                Layout.preferredWidth: 52
                                            }

                                            Item { Layout.fillWidth: true }

                                            // Status with Icon and Text
                                            RowLayout {
                                                Layout.preferredWidth: 70
                                                spacing: 4
                                                Layout.alignment: Qt.AlignRight

                                                MaterialSymbol {
                                                    iconSize: 15
                                                    text: runRow.modelData.isCancelled ? "close" :
                                                          (runRow.modelData.isFailed ? "error" :
                                                          (runRow.modelData.outlier ? "warning" : "check"))
                                                    color: runRow.modelData.isCancelled ? "#f43f5e" :
                                                           (runRow.modelData.isFailed ? "#f43f5e" :
                                                           (runRow.modelData.outlier ? "#f59e0b" : "#4ade80"))
                                                }

                                                StyledText {
                                                    text: runRow.modelData.isCancelled ? "cancelled" :
                                                          (runRow.modelData.isFailed ? "error" :
                                                          (runRow.modelData.outlier ? "outlier" : "ok"))
                                                    font.pixelSize: Appearance.font.pixelSize.smaller
                                                    font.weight: Font.Medium
                                                    color: runRow.modelData.isCancelled ? "#f43f5e" :
                                                           (runRow.modelData.isFailed ? "#f43f5e" :
                                                           (runRow.modelData.outlier ? "#f59e0b" : "#4ade80"))
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            RippleButtonWithIcon {
                                id: openReportBtn
                                Layout.fillWidth: true
                                mainText: "Open Full Report"
                                materialIcon: "open_in_new"
                                colBackground: Appearance.colors.colPrimaryContainer
                                mainContentComponent: Component {
                                    StyledText {
                                        text: openReportBtn.mainText
                                        font.pixelSize: Appearance.font.pixelSize.small
                                        font.weight: Font.DemiBold
                                        color: Appearance.colors.colPrimary
                                    }
                                }
                                onClicked: {
                                    Voice.openReport();
                                }
                            }
                        }
                    }
                }

                // Right Column: Categorized Configuration (3 Distinct Boxes: General, STT, TTS)
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 540
                    Layout.alignment: Qt.AlignTop
                    spacing: 12

                    // --- Box 1: General / Audio (Top) ---
                    Rectangle {
                        id: generalCard
                        Layout.fillWidth: true
                        radius: Appearance.rounding.small
                        color: Appearance.m3colors.m3surfaceContainerHigh
                        border.width: 1
                        border.color: Appearance.colors.colLayer0Border
                        implicitHeight: generalCol.implicitHeight + 20

                        ColumnLayout {
                            id: generalCol
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                MaterialSymbol {
                                    text: "tune"
                                    iconSize: 18
                                    color: Appearance.colors.colPrimary
                                }
                                StyledText {
                                    text: "General / Audio"
                                    font.pixelSize: Appearance.font.pixelSize.normal
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colPrimary
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: Appearance.colors.colLayer0Border
                                }
                            }

                            ConfigSwitchRow {
                                label: "Audio Cues"
                                checked: root.userConfig.beep !== false
                                onToggled: val => root.saveConfigValue("beep", val)
                            }

                            ConfigSelectorRow {
                                label: "Corpus Capture"
                                options: ["none", "outliers", "all"]
                                currentVal: root.userConfig.capture_corpus || "none"
                                onSelected: val => root.saveConfigValue("capture_corpus", val)
                            }
                        }
                    }

                    // --- Box 2: Speech-to-Text (STT) (Middle) ---
                    Rectangle {
                        id: sttCard
                        Layout.fillWidth: true
                        radius: Appearance.rounding.small
                        color: Appearance.m3colors.m3surfaceContainerHigh
                        border.width: 1
                        border.color: Appearance.colors.colLayer0Border
                        implicitHeight: sttCol.implicitHeight + 20

                        ColumnLayout {
                            id: sttCol
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                MaterialSymbol {
                                    text: "mic"
                                    iconSize: 18
                                    color: Appearance.colors.colPrimary
                                }
                                StyledText {
                                    text: "Speech-to-Text (STT)"
                                    font.pixelSize: Appearance.font.pixelSize.normal
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colPrimary
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: Appearance.colors.colLayer0Border
                                }
                            }

                            ConfigModelGridRow {
                                currentVal: root.userConfig.model
                                onSelected: val => root.saveConfigValue("model", val)
                            }

                            // Selected Model Information & Download/Update Card
                            Rectangle {
                                id: modelInfoBox
                                Layout.fillWidth: true
                                radius: Appearance.rounding.small
                                color: Appearance.colors.colLayer1
                                border.width: 1
                                border.color: Appearance.colors.colOutlineVariant
                                implicitHeight: modelInfoCol.implicitHeight + 16

                                readonly property string curModel: String(root.userConfig.model || "medium.en")
                                readonly property var curSpec: root.modelSpecs[curModel] || ({
                                    params: "--", disk: "--", ram: "--", desc: ""
                                })
                                readonly property bool isCached: Boolean(root.cachedModels[curModel])

                                ColumnLayout {
                                    id: modelInfoCol
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 8

                                    // Top Row: Model title & Cache status badge
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        MaterialSymbol {
                                            iconSize: 18
                                            text: modelInfoBox.isCached ? "check_circle" : "cloud_download"
                                            color: modelInfoBox.isCached ? "#4ade80" : "#f59e0b"
                                        }

                                        StyledText {
                                            text: modelInfoBox.curModel
                                            font.pixelSize: Appearance.font.pixelSize.normal
                                            font.weight: Font.DemiBold
                                            color: Appearance.colors.colOnSurface
                                        }

                                        Item { Layout.fillWidth: true }

                                        Rectangle {
                                            radius: Appearance.rounding.small
                                            color: modelInfoBox.isCached ? "#133520" : "#3b2a14"
                                            border.width: 1
                                            border.color: modelInfoBox.isCached ? "#4ade80" : "#f59e0b"
                                            implicitHeight: 22
                                            implicitWidth: statusBadgeText.implicitWidth + 14

                                            StyledText {
                                                id: statusBadgeText
                                                anchors.centerIn: parent
                                                text: modelInfoBox.isCached ? "Ready (Cached)" : "Not Cached"
                                                font.pixelSize: Appearance.font.pixelSize.smaller
                                                font.weight: Font.Medium
                                                color: modelInfoBox.isCached ? "#4ade80" : "#f59e0b"
                                            }
                                        }
                                    }

                                    // Metrics Row: Parameters | Disk Size | RAM/VRAM Required
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            StyledText {
                                                text: "Parameters"
                                                font.pixelSize: Appearance.font.pixelSize.smaller
                                                color: Appearance.colors.colOnSurfaceVariant
                                            }
                                            StyledText {
                                                text: modelInfoBox.curSpec.params
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                font.family: Appearance.font.family.numbers
                                                font.weight: Font.DemiBold
                                                color: Appearance.colors.colOnSurface
                                            }
                                        }

                                        Rectangle { width: 1; height: 26; color: Appearance.colors.colOutlineVariant }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            StyledText {
                                                text: "Download / Disk"
                                                font.pixelSize: Appearance.font.pixelSize.smaller
                                                color: Appearance.colors.colOnSurfaceVariant
                                            }
                                            StyledText {
                                                text: modelInfoBox.curSpec.disk
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                font.family: Appearance.font.family.numbers
                                                font.weight: Font.DemiBold
                                                color: Appearance.colors.colOnSurface
                                            }
                                        }

                                        Rectangle { width: 1; height: 26; color: Appearance.colors.colOutlineVariant }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            StyledText {
                                                text: "Memory (RAM)"
                                                font.pixelSize: Appearance.font.pixelSize.smaller
                                                color: Appearance.colors.colOnSurfaceVariant
                                            }
                                            StyledText {
                                                text: modelInfoBox.curSpec.ram
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                font.family: Appearance.font.family.numbers
                                                font.weight: Font.DemiBold
                                                color: Appearance.colors.colPrimary
                                            }
                                        }
                                    }

                                    // Action Button: Download or Check/Update
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        RippleButtonWithIcon {
                                            id: updateModelBtn
                                            Layout.fillWidth: true
                                            enabled: !root.isDownloadingModel
                                            opacity: enabled ? 1.0 : 0.6
                                            mainText: root.isDownloadingModel ? "Downloading & Verifying..." : (modelInfoBox.isCached ? "Check / Update Model" : ("Download Model (" + modelInfoBox.curSpec.disk + ")"))
                                            materialIcon: root.isDownloadingModel ? "hourglass_top" : (modelInfoBox.isCached ? "sync" : "cloud_download")
                                            colBackground: root.isDownloadingModel ? Appearance.colors.colLayer2 : (modelInfoBox.isCached ? Appearance.colors.colLayer2 : "#1e3a29")

                                            mainContentComponent: Component {
                                                RowLayout {
                                                    spacing: 6
                                                    MaterialSymbol {
                                                        iconSize: 16
                                                        text: updateModelBtn.materialIcon
                                                        color: modelInfoBox.isCached ? Appearance.colors.colOnSurface : "#4ade80"
                                                    }
                                                    StyledText {
                                                        text: updateModelBtn.mainText
                                                        font.pixelSize: Appearance.font.pixelSize.small
                                                        font.weight: Font.DemiBold
                                                        color: modelInfoBox.isCached ? Appearance.colors.colOnSurface : "#4ade80"
                                                    }
                                                }
                                            }
                                            onClicked: {
                                                root.downloadCurrentModel();
                                            }
                                        }
                                    }

                                    // Status Feedback / Error line if active
                                    StyledText {
                                        visible: root.modelDownloadFeedback.length > 0
                                        text: root.modelDownloadFeedback
                                        font.pixelSize: Appearance.font.pixelSize.smaller
                                        font.weight: Font.Medium
                                        color: root.modelDownloadSuccess ? "#4ade80" : "#f43f5e"
                                        Layout.fillWidth: true
                                    }
                                }
                            }

                            ConfigSelectorRow {
                                label: "Device"
                                options: ["cpu", "cuda"]
                                currentVal: root.userConfig.device
                                onSelected: val => root.saveConfigValue("device", val)
                            }

                            ConfigSelectorRow {
                                label: "Compute Type"
                                options: ["int8", "float16", "float32"]
                                currentVal: root.userConfig.compute_type
                                onSelected: val => root.saveConfigValue("compute_type", val)
                            }

                            ConfigSelectorRow {
                                label: "Language"
                                options: ["en", "auto"]
                                currentVal: root.userConfig.language || "en"
                                onSelected: val => root.saveConfigValue("language", val)
                            }

                            ConfigNumberRow {
                                label: "Chunk Duration"
                                minVal: 1.0
                                maxVal: 30.0
                                step: 1.0
                                unit: "s"
                                currentVal: root.userConfig.chunk_duration || 5.0
                                onChanged: val => root.saveConfigValue("chunk_duration", val)
                            }

                            ConfigNumberRow {
                                label: "Beam Size"
                                minVal: 1
                                maxVal: 5
                                step: 1
                                currentVal: root.userConfig.beam_size || 1
                                onChanged: val => root.saveConfigValue("beam_size", Math.round(val))
                            }

                            ConfigSwitchRow {
                                label: "VAD Filter"
                                checked: root.userConfig.vad_filter !== false
                                onToggled: val => root.saveConfigValue("vad_filter", val)
                            }

                            ConfigSwitchRow {
                                label: "Auto-Type"
                                checked: root.userConfig.output_method !== "clipboard"
                                onToggled: val => root.saveConfigValue("output_method", val ? "type" : "clipboard")
                            }
                        }
                    }

                    // --- Box 3: Text-to-Speech (TTS) (Bottom) ---
                    Rectangle {
                        id: ttsCard
                        Layout.fillWidth: true
                        radius: Appearance.rounding.small
                        color: Appearance.m3colors.m3surfaceContainerHigh
                        border.width: 1
                        border.color: Appearance.colors.colLayer0Border
                        implicitHeight: ttsCol.implicitHeight + 20

                        ColumnLayout {
                            id: ttsCol
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                MaterialSymbol {
                                    text: "volume_up"
                                    iconSize: 18
                                    color: Appearance.colors.colPrimary
                                }
                                StyledText {
                                    text: "Text-to-Speech (TTS)"
                                    font.pixelSize: Appearance.font.pixelSize.normal
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colPrimary
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: Appearance.colors.colLayer0Border
                                }
                            }

                            ConfigSelectorRow {
                                label: "TTS Backend"
                                options: ["kokoro", "edge"]
                                currentVal: root.userConfig.tts_backend || "kokoro"
                                onSelected: val => root.saveConfigValue("tts_backend", val)
                            }

                            // TTS Backend Details Card
                            Rectangle {
                                id: ttsDetailsBox
                                Layout.fillWidth: true
                                radius: Appearance.rounding.small
                                color: Appearance.colors.colLayer1
                                border.width: 1
                                border.color: Appearance.colors.colOutlineVariant
                                implicitHeight: ttsDetailsCol.implicitHeight + 14

                                readonly property string backend: root.userConfig.tts_backend || "kokoro"
                                readonly property bool isKokoro: backend === "kokoro"

                                ColumnLayout {
                                    id: ttsDetailsCol
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 6

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        MaterialSymbol {
                                            iconSize: 18
                                            text: ttsDetailsBox.isKokoro ? "memory" : "cloud"
                                            color: Appearance.colors.colPrimary
                                        }

                                        StyledText {
                                            text: ttsDetailsBox.isKokoro ? "Kokoro (Local Neural ONNX)" : "Microsoft Edge (Cloud Streaming)"
                                            font.pixelSize: Appearance.font.pixelSize.small
                                            font.weight: Font.DemiBold
                                            color: Appearance.colors.colOnSurface
                                        }
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 12

                                        StyledText {
                                            text: ttsDetailsBox.isKokoro ? "Params: 82M" : "Params: Cloud API"
                                            font.pixelSize: Appearance.font.pixelSize.smaller
                                            color: Appearance.colors.colOnSurfaceVariant
                                        }

                                        StyledText {
                                            text: ttsDetailsBox.isKokoro ? "Disk: 338 MB" : "Disk: 0 MB"
                                            font.pixelSize: Appearance.font.pixelSize.smaller
                                            color: Appearance.colors.colOnSurfaceVariant
                                        }

                                        StyledText {
                                            text: ttsDetailsBox.isKokoro ? "Memory: ~500 MB RAM" : "Memory: 0 MB local RAM"
                                            font.pixelSize: Appearance.font.pixelSize.smaller
                                            color: Appearance.colors.colPrimary
                                        }
                                    }
                                }
                            }

                            ConfigVoiceGridRow {
                                currentVal: root.userConfig.tts_voice || "af_heart"
                                onSelected: val => root.saveConfigValue("tts_voice", val)
                            }
                        }
                    }
                }
            }
        }
    }
}
