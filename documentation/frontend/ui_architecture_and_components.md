# VIGIL UI Architecture & Component Specification

## Architectural Philosophy

The VIGIL UI is built around an **Investigator-Centric Mission Control** paradigm. Recognizing that machine learning detections represent *hypotheses* rather than courtroom-ready *conclusions*, the user interface emphasizes:

1. **Traceability**: Every event links back to source time intervals and supporting observations.
2. **Immutability & Audit**: Human interventions are timestamped, attributed to investigator badges, and recorded into an immutable audit trail.
3. **Multimodal Parity**: Visual detections (objects, motion, boundary crosses) and acoustic events (speech, transients, frequency anomalies) are presented on an equal temporal footing.
4. **Zero-Latency Telemetry**: Live agent updates stream directly through WebSockets without manual polling.

```
+---------------------------------------------------------------------------------------+
|                                    TOP NAVIGATION BAR                                 |
| [Brand Radar] [Case Selector] [✨ Demo] | [Status Badge] [WS Dot] | [Keys] [+ Ingest] [Export v] |
+-------------------------------+---------------------------------------+---------------+
|     LEFT: MISSION CONTROL     |         CENTER: MEDIA STATION         | RIGHT: REVIEW |
|                               |                                       |               |
| * Agent Roster Chips          | * Primary / Sub-clips Tabs            | * Filter Pills|
|   (Planner, Visual, Audio,    | * Main Video Player + HUD Overlay     |   (All, Prop, |
|    Temporal, Verifier, Rep)   | * Playback Toolbar (-2s, Step, +2s,   |    Conf, Rej) |
| * Case Metrics HUD            |   Speed, Cut Clip)                    | * Search Bar  |
|   (Frames, Obs, Evts, Clips)  | * Multi-Track Forensic Timeline Bar   | * Event Cards |
| * Live Telemetry Stream       |   (Confirmed, Proposed, Rej Markers)  |   - Interval  |
|                               | * Incident Clips Gallery Grid         |   - Notes     |
|                               |                                       |   - Actions   |
+-------------------------------+---------------------------------------+---------------+
|                           BOTTOM DRAWER: EVIDENCE INTELLIGENCE                        |
| [Frames Gallery] | [Raw Observations] | [Evidence Assessments] | [Audit Trail] | [Report] |
+---------------------------------------------------------------------------------------+
```

---

## Component Breakdown

### 1. Top Navigation Bar
- **Branding & Radar Pulse**: Glowing pulse indicator denoting active forensic monitor state.
- **Active Case Picker**: Dynamic dropdown populated from `GET /api/v1/investigations`. Allows instantaneous switching between active investigations.
- **Demo Case Seeder (`✨ Demo Case`)**: Triggers `POST /api/v1/investigations/demo`, populating a full multi-modal security breach case with video, extracted frames, observations, events, and reports.
- **Case Status Badge**: Displays current pipeline state (`CREATED`, `RUNNING`, `COMPLETED`, `FAILED`).
- **WebSocket Telemetry Pill**: Indicates live stream connection status (`WS: CONNECTED` in neon green with pulse, or `WS: DISCONNECTED` in crimson).
- **Export Deliverables Menu**: Dropdown providing instant access to:
  - Court-ready PDF export (`/export/pdf`).
  - Self-contained interactive HTML export with embedded video clips (`/export/html`).
  - Markdown summary view (`/report?format=markdown`).
  - Finalize & Sign Case modal.

### 2. Left Column: Agent Mission Control
- **Agent Status Roster**:
  - `Planner`: Visualizes objective decomposition and task graphs.
  - `Visual`: Extracted frames inspection and object detection.
  - `Audio`: Demuxing and acoustic transcription.
  - `Temporal`: Multi-modal timeline correlation.
  - `Verifier`: Evidence quality, support level, and coverage analysis.
  - `Reporter`: Synthesis of forensic findings.
  - *Active State Animation*: Agent chips glow and pulse when relevant WebSocket telemetry messages are received.
- **Case Quick Metrics Bar**:
  - Displays instant counts of extracted frames, raw observations, correlated events, and sliced incident clips.
- **Live Telemetry Feed**:
  - Monospaced, chronological feed of agent state transitions, detections, and task completions.
  - Color-coded severity borders (cyan for actions, green for success/confirmations, red for errors).
  - Clear log action button.

### 3. Center Column: Media & Forensic Station
- **Media Tabs**: Toggle between full **Primary Footage** and isolated **Incident Sub-clips**.
- **Cyber Video HUD Overlay**:
  - In-screen camera identifier badge (`CAM: NORTH-04`).
  - Frame-accurate millisecond counter.
- **Playback Controls**:
  - Frame stepping forward/backward by 0.1s (<kbd>J</kbd> / <kbd>L</kbd>).
  - Speed selector: `0.25x`, `0.5x`, `1.0x`, `1.5x`, `2.0x`.
  - Quick Cut Clip (<kbd>X</kbd>): Slices an incident clip around the active playhead with 1-second padding.
- **Multi-Track Forensic Timeline**:
  - Scrub bar with dynamic progress fill and scrub-on-click/drag.
  - Color-coded event markers:
    - `Confirmed`: Neon Emerald (`#10b981`)
    - `Proposed`: Amber (`#f59e0b`)
    - `Under Review`: Sky Cyan (`#06b6d4`)
    - `Rejected`: Crimson (`#ef4444`)
  - Interactive hover tooltip displaying the precise timecode and event summary.

### 4. Right Column: Human Review Station (Phase 5)
- **Review Filters**: Quick toggles for `All`, `Proposed`, `Confirmed`, and `Rejected` events.
- **Keyword Search**: Real-time filtering by category, description, or reviewer badge.
- **Interactive Event Cards**:
  - Category tag and status badge.
  - Footage time interval (`start_seconds – end_seconds`).
  - Evidence description and prior investigator review notes.
  - Action buttons:
    - `✔ Confirm`: Confirms incident.
    - `✖ Reject`: Dismisses as false positive.
    - `✎ Edit`: Opens review modal to edit interval, category, or notes.
    - `▶ Seek`: Instantly sets video playhead to event start.
    - `✂ Cut Clip`: Extracts an isolated, reviewable H.264 video sub-clip.

### 5. Bottom Drawer: Evidence Intelligence & Audit Repository
An expandable multi-tab panel that slides up from the base:
- **Tab 1: Extracted Frames**:
  - Horizontal gallery of visual keyframes.
  - Hover reveals timestamp and frame ID; clicking immediately jumps video player to that exact moment.
- **Tab 2: Observations**:
  - Comprehensive table of raw model findings.
  - Modality badges (`video`, `audio`, `image`), finding type, timecode interval, confidence score bar, and model provenance.
- **Tab 3: Evidence Assessments**:
  - Quality, support level, and uncertainty assessments.
  - Colored ratings (`high`, `moderate`, `low`, `insufficient`).
  - Rationale and assessor entity.
- **Tab 4: Audit Trail**:
  - Tamper-evident chronological table of all investigator decisions.
  - Displays timestamp (UTC), actor badge, action, target record, state delta (old -> new), and justification notes.
- **Tab 5: Forensic Report**:
  - Executive summary preview with version tracking and direct PDF/HTML download links.
