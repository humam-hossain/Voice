pragma Singleton
pragma ComponentBehavior: Bound

import qs.modules.common
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    // Paths
    readonly property string runtimeDir: {
        const xdg = Quickshell.env("XDG_RUNTIME_DIR");
        return (xdg && xdg.length > 0) ? (xdg + "/voice-stt") : "/run/user/1000/voice-stt";
    }
    readonly property string recorderPidPath: runtimeDir + "/recorder.pid"
    readonly property string ttsPidPath: runtimeDir + "/tts.pid"
    readonly property string statusPath: runtimeDir + "/status.json"

    // Reactive State Properties
    property string sttState: "idle"
    property string ttsState: "idle"
    readonly property string overallState: {
        if (sttState === "recording") return "recording";
        if (sttState === "transcribing") return "transcribing";
        if (ttsState === "speaking") return "speaking";
        if (sttState === "typing") return "typing";
        if (sttState === "starting") return "starting";
        return "idle";
    }

    // Process Tracking
    property int sttPid: 0
    property int ttsPid: 0

    // TTS Metadata
    property string ttsVoice: "af_heart"
    property string ttsBackend: "kokoro"

    // Telemetry & Metrics (Strictly Controlled by voice.py)
    property int elapsedSeconds: 0
    property real elapsedMs: 0
    property string formattedDuration: "0:00"
    readonly property int maxDurationSeconds: 300
    property real startTime: 0

    // Multi-bar Progress & Report Properties
    property real recordedAudioSeconds: 0.0
    property string formattedRecordedDuration: "0:00"
    property real transcribedAudioSeconds: 0.0
    property string formattedTranscribedDuration: "0:00"
    property int totalElapsedSeconds: 0
    property string formattedTotalDuration: "0:00"
    property bool typingDurationCaptured: false
    property int liveCharsOut: 0
    readonly property string defaultReportPath: runtimeDir + "/report.html"
    property string statusReportPath: ""

    // Formatting Helper
    function formatDuration(sec) {
        if (sec === undefined || sec === null || isNaN(sec)) return "0:00";
        const sInt = Math.max(0, Math.floor(sec));
        const m = Math.floor(sInt / 60);
        const s = sInt % 60;
        return m + ":" + (s < 10 ? "0" : "") + s;
    }

    // State File Observers
    FileView {
        id: recorderFile
        path: root.recorderPidPath
        printErrors: false
        blockLoading: true
    }

    FileView {
        id: ttsFile
        path: root.ttsPidPath
        printErrors: false
        blockLoading: true
    }

    FileView {
        id: statusFile
        path: root.statusPath
        printErrors: false
        blockLoading: true
    }

    // Procfs Observers
    FileView {
        id: sttCmdlineFile
        path: root.sttPid > 0 ? ("/proc/" + root.sttPid + "/cmdline") : ""
        printErrors: false
        blockLoading: true
    }

    FileView {
        id: ttsCmdlineFile
        path: root.ttsPid > 0 ? ("/proc/" + root.ttsPid + "/cmdline") : ""
        printErrors: false
        blockLoading: true
    }

    FileView {
        id: sttStatFile
        path: root.sttPid > 0 ? ("/proc/" + root.sttPid + "/stat") : ""
        printErrors: false
        blockLoading: true
    }

    // Visual Linger Timer for Rapid Typing (5000ms)
    Timer {
        id: typingLingerTimer
        interval: 5000
        repeat: false
        onTriggered: {
            if (root.sttState === "typing") {
                root.sttState = "idle";
                root.resetDuration();
            }
        }
    }

    function resetDuration() {
        startTime = 0;
        typingDurationCaptured = false;
        elapsedMs = 0;
        elapsedSeconds = 0;
        formattedDuration = "0:00";
        recordedAudioSeconds = 0.0;
        formattedRecordedDuration = "0:00";
        transcribedAudioSeconds = 0.0;
        formattedTranscribedDuration = "0:00";
        totalElapsedSeconds = 0;
        formattedTotalDuration = "0:00";
        liveCharsOut = 0;
        statusReportPath = "";
    }

    function openReport() {
        const target = statusReportPath.length > 0 ? statusReportPath : defaultReportPath;
        if (target.startsWith(runtimeDir) && target.endsWith("report.html")) {
            Qt.openUrlExternally("file://" + target);
        } else {
            console.warn("[Voice] Refusing to open untrusted report target: " + target);
        }
    }

    function poll() {
        recorderFile.reload();
        ttsFile.reload();
        statusFile.reload();

        // 0. Parse status.json safely
        let st = null;
        try {
            const raw = statusFile.text().trim();
            if (raw.length > 0) {
                const parsed = JSON.parse(raw);
                if (parsed && parsed.schema === 1) {
                    st = parsed;
                }
            }
        } catch (e) {
            st = null;
        }

        const nowSec = Date.now() / 1000.0;
        const isExpired = Boolean(st && st.expires_at && (nowSec > (st.expires_at + 1.0)));

        const recText = recorderFile.text().trim();
        const ttsText = ttsFile.text().trim();

        // 1. STT State Evaluation (Passive Observer - Never Deletes PID Files)
        if (recText.length > 0) {
            const parts = recText.split(/\s+/);
            const pid = parseInt(parts[0]);
            let rawState = parts[1] || "recording";

            if (!isNaN(pid) && pid > 0) {
                // If a new session has started, immediately cut short any active linger timer
                if (rawState === "recording" || rawState === "starting") {
                    if (typingLingerTimer.running) {
                        typingLingerTimer.stop();
                        root.resetDuration();
                    }
                }

                // Check process liveness safely via procfs
                if (root.sttPid === pid) {
                    sttStatFile.reload();
                    const procAlive = sttStatFile.text().trim().length > 0;
                    if (!procAlive) {
                        root.sttPid = 0;
                        if (root.sttState === "transcribing") {
                            root.sttState = "typing";
                            typingLingerTimer.restart();
                        } else if (!typingLingerTimer.running) {
                            root.sttState = "idle";
                        }
                    }
                } else {
                    root.sttPid = pid;
                    root.resetDuration();
                }

                if (root.sttPid > 0) {
                    if (st && !isExpired && st.pid === pid) {
                        rawState = st.state;
                    }
                    if (rawState === "recording" || rawState === "starting") {
                        if (typingLingerTimer.running) {
                            typingLingerTimer.stop();
                            root.resetDuration();
                        }
                        root.sttState = rawState;
                    } else if (rawState === "typing") {
                        root.sttState = "typing";
                        if (!typingLingerTimer.running) {
                            typingLingerTimer.restart();
                        }
                    } else if (root.sttState !== "typing" || !typingLingerTimer.running) {
                        root.sttState = rawState;
                    }
                }
            } else {
                if (!typingLingerTimer.running) {
                    root.sttState = "idle";
                    root.sttPid = 0;
                }
            }
        } else {
            if (st && !isExpired && typeof st.state === "string" && st.state !== "idle") {
                if (st.state === "recording" || st.state === "starting") {
                    if (typingLingerTimer.running) {
                        typingLingerTimer.stop();
                        root.resetDuration();
                    }
                    root.sttState = st.state;
                } else if (st.state === "typing") {
                    root.sttState = "typing";
                    if (!typingLingerTimer.running) {
                        typingLingerTimer.restart();
                    }
                } else if (root.sttState !== "typing" || !typingLingerTimer.running) {
                    root.sttState = st.state;
                }
                if (st.pid && st.pid > 0) {
                    root.sttPid = st.pid;
                }
            } else if (root.sttState === "transcribing") {
                root.sttState = "typing";
                typingLingerTimer.restart();
            } else if (!typingLingerTimer.running) {
                root.sttState = "idle";
                root.sttPid = 0;
            }
        }

        // 2. Process status.json payload properties (100% telemetry-driven by voice.py)
        if (st && !isExpired && (root.sttState !== "idle" || typingLingerTimer.running)) {
            // Guard: Ignore stale status from a previous run while a new PID is starting/recording
            if (root.sttPid > 0 && st.pid && st.pid !== root.sttPid && (root.sttState === "recording" || root.sttState === "starting")) {
                root.recordedAudioSeconds = 0.0;
                root.formattedRecordedDuration = "0:00";
                root.transcribedAudioSeconds = 0.0;
                root.formattedTranscribedDuration = "0:00";
                root.totalElapsedSeconds = 0;
                root.formattedTotalDuration = "0:00";
                root.formattedDuration = "0:00";
                root.liveCharsOut = 0;
            } else {
                if (st.audio_s !== undefined && st.audio_s !== null && st.audio_s >= 0) {
                    root.recordedAudioSeconds = st.audio_s;
                    root.formattedRecordedDuration = formatDuration(st.audio_s);
                }
                if (st.transcribed_audio_s !== undefined && st.transcribed_audio_s !== null && st.transcribed_audio_s >= 0) {
                    root.transcribedAudioSeconds = st.transcribed_audio_s;
                    root.formattedTranscribedDuration = formatDuration(st.transcribed_audio_s);
                }
                if (st.total_duration_s !== undefined && st.total_duration_s !== null && st.total_duration_s >= 0) {
                    root.totalElapsedSeconds = Math.floor(st.total_duration_s);
                    root.formattedTotalDuration = formatDuration(st.total_duration_s);
                } else {
                    root.formattedTotalDuration = root.formattedRecordedDuration;
                }
                root.formattedDuration = root.formattedRecordedDuration;
                if (st.report_path !== undefined && st.report_path !== null && typeof st.report_path === "string") {
                    root.statusReportPath = st.report_path;
                }
                if (st.chars_out !== undefined && st.chars_out !== null && st.chars_out >= 0) {
                    root.liveCharsOut = st.chars_out;
                }
            }
        }

        // 3. TTS State Evaluation
        if (ttsText.length > 0) {
            const parts = ttsText.split(/\s+/);
            const pid = parseInt(parts[0]);

            if (!isNaN(pid) && pid > 0) {
                root.ttsPid = pid;
                if (root.ttsPid === pid) {
                    ttsCmdlineFile.reload();
                    const cmdline = ttsCmdlineFile.text();
                    if (cmdline && (cmdline.toLowerCase().includes("voice") || cmdline.toLowerCase().includes("voicemode"))) {
                        root.ttsState = "speaking";
                        const args = cmdline.split("\0");
                        let voice = "af_heart";
                        let backend = "kokoro";
                        for (let i = 0; i < args.length; i++) {
                            if (args[i] === "--tts-voice" && i + 1 < args.length) {
                                voice = args[i + 1];
                            } else if (args[i] === "--tts-backend" && i + 1 < args.length) {
                                backend = args[i + 1];
                            }
                        }
                        root.ttsVoice = voice;
                        root.ttsBackend = backend;
                    } else {
                        root.ttsState = "speaking";
                    }
                }
            } else {
                root.ttsState = "idle";
                root.ttsPid = 0;
            }
        } else {
            root.ttsState = "idle";
            root.ttsPid = 0;
        }

        // Reset durations when idle and not lingering
        if (root.sttState === "idle" && root.ttsState === "idle" && !typingLingerTimer.running) {
            root.resetDuration();
        }
    }

    Timer {
        id: pollTimer
        interval: (root.overallState === "idle" && !typingLingerTimer.running) ? 2500 : 100
        repeat: true
        running: true
        onTriggered: root.poll()
    }

    Component.onCompleted: {
        root.poll();
    }
}
