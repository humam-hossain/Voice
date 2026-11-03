pragma ComponentBehavior: Bound

import qs.modules.common
import qs.modules.common.widgets
import qs.services
import QtQuick
import QtQuick.Layouts
import Quickshell

BarGroup {
    id: root

    clip: true

    property real useShortenedForm: 0

    // Internal State Tracking
    property string previousState: "idle"
    property string lastRecordedDuration: "0:00"
    property string lastTranscribedDuration: "0:00"
    property string lastTotalDuration: "0:00"
    readonly property bool inWrapUp: wrapUpTimer.running

    // Colors & Concurrent Decode Indicator (D-06, D-07, D-08)
    readonly property color skyBlue: "#38bdf8"
    readonly property color neonGreen: "#4ade80"
    readonly property bool isConcurrentlyDecoding: effectiveState === "recording" && Voice.transcribedAudioSeconds > 0

    property color pulsedColor: Appearance.colors.colPrimary

    SequentialAnimation on pulsedColor {
        running: root.isConcurrentlyDecoding
        loops: Animation.Infinite
        ColorAnimation { to: root.skyBlue; duration: 600; easing.type: Easing.InOutSine }
        ColorAnimation { to: Appearance.colors.colPrimary; duration: 600; easing.type: Easing.InOutSine }
    }

    // Public Component Aliases for Telemetry & Verification
    readonly property alias wrapUpTimer: wrapUpTimer
    readonly property alias pulseAnimation: pulseAnimation
    readonly property alias voiceIcon: voiceIcon
    readonly property alias voiceLabel: voiceLabel
    readonly property alias contentContainer: contentContainer
    readonly property alias pillMouseArea: pillMouseArea
    readonly property alias inertMouseArea: pillMouseArea
    readonly property alias hoverArea: pillMouseArea
    readonly property alias voicePopup: voicePopup

    // Effective Lifecycle State (Sequential Linear Flow)
    readonly property string effectiveState: {
        if (Voice.overallState === "recording" || Voice.overallState === "starting" || Voice.overallState === "speaking") {
            return Voice.overallState;
        }
        if (inWrapUp) return "wrapup";
        return Voice.overallState;
    }

    // Dynamic State Palette Mapping (D-05, D-06, D-07, D-08)
    readonly property color currentColor: {
        if (root.isConcurrentlyDecoding) return pulsedColor;
        switch (effectiveState) {
            case "recording": return Appearance.colors.colPrimary;
            case "transcribing": return root.skyBlue;
            case "typing": return root.neonGreen;
            case "wrapup": return root.neonGreen;
            case "speaking": return Appearance.colors.colSecondary;
            case "starting": return Appearance.colors.colPrimary;
            default: return Appearance.colors.colOnLayer1;
        }
    }

    // Dynamic Text Content Mapping (D-01, D-02, D-03, D-04)
    readonly property string displayText: {
        switch (effectiveState) {
            case "recording":
                return Voice.formattedRecordedDuration + " | " + Voice.formattedTranscribedDuration;
            case "transcribing":
            case "typing":
                return Voice.formattedRecordedDuration + " | " + Voice.formattedTranscribedDuration + " | " + Voice.formattedTotalDuration;
            case "wrapup":
                return (Voice.formattedRecordedDuration !== "0:00" ? Voice.formattedRecordedDuration : root.lastRecordedDuration)
                    + " | " + (Voice.formattedTranscribedDuration !== "0:00" ? Voice.formattedTranscribedDuration : root.lastTranscribedDuration)
                    + " | " + (Voice.formattedTotalDuration !== "0:00" ? Voice.formattedTotalDuration : root.lastTotalDuration);
            case "speaking":
                return Voice.formattedDuration !== "0:00" ? Voice.formattedDuration : root.lastRecordedDuration;
            case "starting":
                return Voice.formattedDuration;
            default:
                return "";
        }
    }

    readonly property bool isExpanded: effectiveState !== "idle" && useShortenedForm < 2 && !vertical

    // Responsive Width Binding with M3 250ms Emphasized Deceleration (D-04, VOICE-06, Pitfall 1)
    implicitWidth: vertical ? Appearance.sizes.baseVerticalBarWidth : (
        voiceIcon.implicitWidth + (isExpanded ? (voiceLabel.implicitWidth + 4) : 0) + padding * 2
    )

    resources: [
        // Completion Wrap-up Linger Timer (5s per D-01)
        Timer {
            id: wrapUpTimer
            interval: 5000
            repeat: false
        },

        // React to Voice State Shifts & Duration Caching (D-06, Pitfall 4)
        Connections {
            target: Voice

            function onOverallStateChanged() {
                if (Voice.overallState === "recording" || Voice.overallState === "starting" || Voice.overallState === "speaking") {
                    wrapUpTimer.stop();
                    root.lastRecordedDuration = "0:00";
                    root.lastTranscribedDuration = "0:00";
                    root.lastTotalDuration = "0:00";
                } else if (Voice.overallState === "idle") {
                    if (root.previousState === "typing" || root.previousState === "speaking") {
                        wrapUpTimer.restart();
                    } else {
                        wrapUpTimer.stop();
                    }
                } else {
                    wrapUpTimer.stop();
                }
                root.previousState = Voice.overallState;
            }

            function onFormattedDurationChanged() {
                if (Voice.formattedDuration !== "0:00") {
                    root.lastRecordedDuration = Voice.formattedDuration;
                }
            }

            function onFormattedRecordedDurationChanged() {
                if (Voice.formattedRecordedDuration !== "0:00") {
                    root.lastRecordedDuration = Voice.formattedRecordedDuration;
                }
            }

            function onFormattedTranscribedDurationChanged() {
                if (Voice.formattedTranscribedDuration !== "0:00") {
                    root.lastTranscribedDuration = Voice.formattedTranscribedDuration;
                }
            }

            function onFormattedTotalDurationChanged() {
                if (Voice.formattedTotalDuration !== "0:00") {
                    root.lastTotalDuration = Voice.formattedTotalDuration;
                }
            }
        }
    ]

    MouseArea {
        id: pillMouseArea
        parent: root
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        hoverEnabled: true
        cursorShape: Qt.ArrowCursor
        onPressed: event => event.accepted = true
        onClicked: event => event.accepted = true

        VoicePopup {
            id: voicePopup
            hoverTarget: pillMouseArea
        }
    }

    // Content Layout Container (Pitfall 2)
    Item {
        id: contentContainer
        implicitWidth: voiceIcon.implicitWidth + (root.isExpanded ? (voiceLabel.implicitWidth + 4) : 0)
        implicitHeight: Appearance.font.pixelSize.normal
        Layout.alignment: root.vertical ? Qt.AlignCenter : Qt.AlignVCenter

        // AI Identity Soundwave Icon (D-02, D-03)
        MaterialSymbol {
            id: voiceIcon
            anchors.left: root.vertical ? undefined : parent.left
            anchors.centerIn: root.vertical ? parent : undefined
            anchors.verticalCenter: root.vertical ? undefined : parent.verticalCenter
            text: (root.effectiveState === "typing" || root.effectiveState === "wrapup") ? "edit" : "graphic_eq"
            iconSize: Appearance.font.pixelSize.normal
            color: root.currentColor

            Behavior on color {
                ColorAnimation {
                    duration: 200
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: Appearance.animationCurves.expressiveEffects
                }
            }

            // Gentle Breathing Pulse Animation (D-08, VOICE-03, Pitfall 3)
            SequentialAnimation {
                id: pulseAnimation
                running: root.effectiveState === "recording"
                loops: Animation.Infinite

                // Pitfall 3: Guarantee opacity resets to 1.0 on stop
                onRunningChanged: {
                    if (!running) voiceIcon.opacity = 1.0;
                }

                NumberAnimation {
                    target: voiceIcon
                    property: "opacity"
                    to: 0.5
                    duration: 500
                    easing.type: Easing.InOutSine
                }
                NumberAnimation {
                    target: voiceIcon
                    property: "opacity"
                    to: 1.0
                    duration: 500
                    easing.type: Easing.InOutSine
                }
            }
        }

        // Live Telemetry Label & State Badges (D-06, VOICE-05)
        StyledText {
            id: voiceLabel
            anchors.left: voiceIcon.right
            anchors.leftMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            text: root.displayText
            font.pixelSize: Appearance.font.pixelSize.small
            font.family: Appearance.font.family.numbers
            font.features: { "tnum": 1 }
            color: root.currentColor
            visible: root.isExpanded
            opacity: root.isExpanded ? 1.0 : 0.0

            Behavior on color {
                ColorAnimation {
                    duration: 200
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: Appearance.animationCurves.expressiveEffects
                }
            }

            Behavior on opacity {
                NumberAnimation {
                    duration: 150
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: Appearance.animationCurves.expressiveEffects
                }
            }
        }
    }
}
