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
                const audioSec = (item.audio_s !== undefined && item.audio_s !== null) ? Number(item.audio_s) : null;
                const rtfVal = (item.rtf !== undefined && item.rtf !== null) ? Number(item.rtf) : null;
                const isFailed = item.failed === true || (item.failure_reason && item.failure_reason !== "");
                const isOutlier = Boolean(item.is_outlier);
                result.push({
                    runId: item.run_id || "",
                    duration: audioSec !== null ? (audioSec.toFixed(1) + "s") : "--",
                    chars: item.characters !== undefined && item.characters !== null ? String(item.characters) : "--",
                    rtf: rtfVal !== null ? (rtfVal.toFixed(2) + "x") : "--",
                    outlier: isOutlier,
                    success: !isFailed,
                    outcome: item.outcome || (isFailed ? "failed" : "success")
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
        }
    }

    Component.onCompleted: {
        root.reloadConfig();
        root.reloadMetrics();
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
            color: Appearance.colors.colOnSurfaceVariant
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
            color: Appearance.colors.colOnSurfaceVariant
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
            color: Appearance.colors.colOnSurfaceVariant
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
                    delegate: OptionChip {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
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
                    delegate: OptionChip {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
                        selected: modelGrid.currentVal === modelData
                        onClicked: modelGrid.selected(modelData)
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: ["large-v2", "large-v3"]
                    delegate: OptionChip {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData
                        selected: modelGrid.currentVal === modelData
                        onClicked: modelGrid.selected(modelData)
                    }
                }
                Item { Layout.fillWidth: true }
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
            color: Appearance.colors.colOnSurfaceVariant
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
            color: Appearance.colors.colOnSurfaceVariant
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
            color: Appearance.colors.colOnSurfaceVariant
        }
        Item { Layout.fillWidth: true }
        StyledText {
            text: tRow.value
            font.pixelSize: Appearance.font.pixelSize.small
            font.family: Appearance.font.family.numbers
            font.weight: Font.DemiBold
            color: Appearance.colors.colOnLayer1
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
                    Layout.preferredWidth: 380
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
                            anchors.margins: 10
                            spacing: 8

                            StyledText {
                                text: "Live Telemetry"
                                font.pixelSize: Appearance.font.pixelSize.normal
                                font.weight: Font.DemiBold
                                color: Appearance.colors.colPrimary
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
                                value: (root.recentRuns.length > 0 && Voice.overallState === "idle")
                                    ? root.recentRuns[0].chars
                                    : (Voice.overallState === "typing" ? "Typing..." : "--")
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
                            anchors.margins: 10
                            spacing: 8

                            StyledText {
                                text: "Recent Dictations"
                                font.pixelSize: Appearance.font.pixelSize.normal
                                font.weight: Font.DemiBold
                                color: Appearance.colors.colPrimary
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
                                            spacing: 6

                                            MaterialSymbol {
                                                iconSize: Appearance.font.pixelSize.normal
                                                text: !runRow.modelData.success ? "close" : (runRow.modelData.outlier ? "warning" : "check")
                                                color: !runRow.modelData.success ? "#f43f5e" : (runRow.modelData.outlier ? "#f59e0b" : "#4ade80")
                                            }

                                            StyledText {
                                                text: runRow.modelData.duration
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                font.family: Appearance.font.family.numbers
                                                font.weight: Font.DemiBold
                                                color: Appearance.colors.colOnLayer1
                                            }

                                            StyledText {
                                                text: runRow.modelData.chars + " chars"
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                color: Appearance.colors.colOnSurfaceVariant
                                            }

                                            Item { Layout.fillWidth: true }

                                            StyledText {
                                                text: runRow.modelData.rtf
                                                font.pixelSize: Appearance.font.pixelSize.small
                                                font.family: Appearance.font.family.numbers
                                                font.weight: Font.DemiBold
                                                color: runRow.modelData.outlier ? "#f59e0b" : Appearance.colors.colOnLayer1
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
                                colBackground: Appearance.colors.colLayer2
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
                                    color: root.skyBlue
                                }
                                StyledText {
                                    text: "Speech-to-Text (STT)"
                                    font.pixelSize: Appearance.font.pixelSize.normal
                                    font.weight: Font.DemiBold
                                    color: root.skyBlue
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
                                    color: Appearance.colors.colSecondary
                                }
                                StyledText {
                                    text: "Text-to-Speech (TTS)"
                                    font.pixelSize: Appearance.font.pixelSize.normal
                                    font.weight: Font.DemiBold
                                    color: Appearance.colors.colSecondary
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
