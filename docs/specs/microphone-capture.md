# Microphone Capture Specification

## Overview

Audio from the system microphone is recorded **only when the microphone is actively in use by another application** (e.g., during a voice call in Zoom, WeChat, FaceTime, or voice input in dictation apps). This captures the user's spoken input as part of the activity log.

## Trigger Rules

### Start Recording

Recording begins when the system microphone device transitions from **idle to active** — i.e., when any application starts an audio input session on the device.

Detection is based on the Core Audio property `kAudioDevicePropertyDeviceIsRunningSomewhere`, which indicates whether any process has an active I/O cycle on the microphone device. A property listener monitors this value for changes.

### Stop Recording

Recording stops when the microphone device transitions from **active to idle** — i.e., when all applications have stopped their audio input sessions.

The current audio segment is finalized and saved upon this transition.

### Debounce

To avoid excessive file fragmentation from brief microphone activations (e.g., permission checks, app initialization probes):

- **Start debounce**: Recording only begins if the microphone remains active for at least `mic_start_debounce_ms` (default: 500ms)
- **Stop debounce**: Recording only stops if the microphone remains idle for at least `mic_stop_debounce_ms` (default: 2000ms). This prevents splitting a single conversation into multiple files due to brief pauses between voice segments

## Audio Format

| Property | Value |
|----------|-------|
| **Sample rate** | 16000 Hz |
| **Channels** | 1 (mono) |
| **Bit depth** | 16-bit signed integer (PCM) |
| **File format** | WAV |

The sample rate of 16 kHz is chosen as the standard for speech. Mono recording is sufficient since the microphone captures a single input source.

> **Future consideration**: Audio files may be post-processed to a compressed format (e.g., Opus/OGG) to reduce storage. This is not part of the initial specification.

## Application Context

The application context is determined by identifying **which process(es) actually hold an active audio input session on the microphone device**, not by checking which application is in the foreground. This is critical because users typically multitask — a Zoom call runs in the background while the user works in VSCode or a browser.

### Identifying the Microphone-Owning Process

When `kAudioDevicePropertyDeviceIsRunningSomewhere` transitions to active, the system queries which process(es) have an active I/O cycle on the microphone. Detection methods (in order of preference):

1. **Core Audio HAL client list** — query the audio device for its active client PIDs
2. **System log (TCC)** — parse recent `kTCCServiceMicrophone` entries from the unified log as a fallback

The resolved PID is mapped to an application name and bundle ID.

### Multiple Concurrent Consumers

Multiple applications may use the microphone simultaneously (e.g., a meeting app and a voice assistant). In this case:

- **All** consuming applications are recorded in the `mic_start` log entry
- The **first** application (alphabetically by app name) is used in the filename
- If a new application starts using the microphone during an existing recording session, a `mic_join` entry is logged
- If an application releases the microphone while others still hold it, a `mic_leave` entry is logged

### Unresolvable Process

If the consuming process cannot be identified (e.g., due to permission limitations), the app field falls back to `unknown`.

## File Naming

Format: `mic_{HHmmss}_{ms}_{app}_dur{seconds}.wav`

| Component | Description |
|-----------|-------------|
| `mic` | Fixed prefix identifying microphone recordings |
| `HHmmss` | Recording start time (hours, minutes, seconds) |
| `ms` | Milliseconds (3 digits) |
| `app` | Sanitized name of the primary application (lowercase, spaces replaced with `-`) |
| `dur{seconds}` | Recording duration in whole seconds |

Examples:
```
mic_143052_789_facetime_dur45.wav
mic_160012_001_zoom_dur1803.wav
mic_091530_234_wechat_dur120.wav
mic_103015_567_safari_dur3.wav
```

## Storage

- **Location**: `{output_dir}/{YYYY-MM-DD}/{filename}`
- Same date-based directory structure as screenshots and keyboard logs
- The date directory is created automatically if it does not exist

## Log Entries

Microphone events are written to the same daily log file as keyboard and screenshot events (`{YYYY-MM-DD}.log`). This keeps all user activity in a single chronological stream.

### Recording Start — `mic_start`

When recording begins (after start debounce), a `mic_start` entry is written listing the application(s) that hold an active microphone session:

```
[HH:MM:SS] 🎤 mic_start | FaceTime (com.apple.FaceTime)
[HH:MM:SS] 🎤 mic_start | WeChat (com.tencent.xinWeChat)
[HH:MM:SS] 🎤 mic_start | Zoom (us.zoom.xos), Slack (com.tinyspeck.slackmacgap)
```

Format: `[HH:MM:SS] 🎤 mic_start | {AppName} ({bundle_id})[, {AppName2} ({bundle_id2})]`

### App Joins Microphone — `mic_join`

If a new application starts using the microphone while a recording is already in progress:

```
[HH:MM:SS] 🎤 mic_join | Siri (com.apple.siri)
```

### App Leaves Microphone — `mic_leave`

If an application releases the microphone while at least one other application still holds it (recording continues):

```
[HH:MM:SS] 🎤 mic_leave | Siri (com.apple.siri)
```

### Recording Stop — `mic_stop`

When all applications release the microphone (after stop debounce), the recording ends:

```
[HH:MM:SS] 🎤 mic_stop (45s) mic_143052_789_facetime_dur45.wav
```

Format: `[HH:MM:SS] 🎤 mic_stop ({duration}s) {filename}`

### Full Log Example

A typical day with voice dictation, a FaceTime call, and a Zoom meeting — interleaved with keyboard and screenshot entries:

```
[09:15:30] 🎤 mic_start | Dictation (com.apple.SpeechRecognitionCore)
[09:15:33] 🎤 mic_stop (3s) mic_091530_234_dictation_dur3.wav

[10:30:15] 🎤 mic_start | FaceTime (com.apple.FaceTime)
[10:45:12] 🎤 mic_stop (897s) mic_103015_567_facetime_dur897.wav

[14:20:00] 🎤 mic_start | Zoom (us.zoom.xos)
[14:35:10] 🎤 mic_join | Siri (com.apple.siri)
[14:35:14] 🎤 mic_leave | Siri (com.apple.siri)
[14:50:30] 🎤 mic_stop (1830s) mic_142000_123_zoom_dur1830.wav

[16:00:00] 🎤 mic_start | WeChat (com.tencent.xinWeChat)
[16:12:45] 🎤 mic_stop (765s) mic_160000_001_wechat_dur765.wav
```

## Scope

### What Is Captured

- Audio from the **default system input device** (built-in microphone, external microphone, or headset microphone)
- Only the user's own microphone input — what the user speaks into the mic

### What Is NOT Captured

- **System output audio** (sound from other participants in a call, media playback, notifications) — this would require virtual audio device routing, which is out of scope
- **Audio from non-default input devices** — only the default input device is monitored
- **Audio when no other application is using the microphone** — the system does not perform always-on recording

## Default Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `mic_enabled` | `false` | Whether microphone capture is enabled |
| `mic_sample_rate` | `16000` | Audio sample rate in Hz |
| `mic_channels` | `1` | Number of audio channels |
| `mic_start_debounce_ms` | `500` | Minimum active duration before recording starts |
| `mic_stop_debounce_ms` | `2000` | Minimum idle duration before recording stops |

## macOS Requirements

- **Microphone permission**: Required. macOS will prompt for consent on first access. Must be granted in System Settings > Privacy & Security > Microphone.
- **Orange indicator dot**: The system status bar will display an orange dot while the microphone is being accessed. This is a system-level privacy indicator and cannot be suppressed.
- **Shared access**: macOS allows multiple applications to access the microphone simultaneously. This capture does not interfere with the application that triggered the microphone usage.

## Privacy Considerations

- Microphone capture is **disabled by default** and must be explicitly enabled by the user
- All audio data is stored locally — no audio is transmitted to external services
