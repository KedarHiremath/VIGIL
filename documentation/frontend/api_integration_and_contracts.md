# VIGIL Frontend API Integration & Data Contracts

## REST API Integration

The VIGIL UI consumes the FastAPI backend exposed under `/api/v1/investigations`.

### 1. Ingestion & Case Catalog

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/investigations` | `GET` | List all registered investigations with basic metadata. |
| `/api/v1/investigations` | `POST` | Multipart upload of video footage, creating an investigation and initiating background processing. |
| `/api/v1/investigations/demo` | `POST` | Seeds a rich synthetic demo investigation with video, frames, audio, observations, and events. |
| `/api/v1/investigations/{id}` | `GET` | Fetch full domain model of an investigation. |
| `/api/v1/investigations/{id}/status` | `GET` | Poll status, completed tasks, observation counts, event counts, and report readiness. |

---

### 2. Media Streaming & Artifact Retrieval

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/investigations/{id}/media` | `GET` | List registered physical media assets for this investigation. |
| `/api/v1/investigations/{id}/media/primary/content` | `GET` | Stream primary source video footage file (`video/mp4`) for browser playback. |
| `/api/v1/investigations/{id}/media/{media_id}/content` | `GET` | Stream specific media asset file. |
| `/api/v1/investigations/{id}/artifacts` | `GET` | List extracted artifacts (JPEG frames, WAV audio, H.264 incident clips). |
| `/api/v1/investigations/{id}/artifacts/{artifact_id}/content` | `GET` | Stream or download artifact content file (image, audio, or video clip). |

---

### 3. Forensic Findings & Verification

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/investigations/{id}/observations` | `GET` | Retrieve raw model detections and acoustic findings with provenance. |
| `/api/v1/investigations/{id}/events` | `GET` | Retrieve correlated events, optionally filtered with `?status=confirmed`. |
| `/api/v1/investigations/{id}/assessments` | `GET` | Retrieve evidence quality and uncertainty assessments. |
| `/api/v1/investigations/{id}/events/{event_id}/review` | `POST` | Submit human verification (`confirmed`, `rejected`, `under_review`) with audit notes. |
| `/api/v1/investigations/{id}/events/{event_id}/clip` | `POST` | Slice an isolated H.264 incident clip around the event interval. |
| `/api/v1/investigations/{id}/audit` | `GET` | Retrieve chronological audit trail records. |

#### Event Review Payload Example
```json
{
  "status": "confirmed",
  "reviewer": "Det. Vance #402",
  "notes": "Verified against gate sensor and high-confidence frame detections.",
  "event_type": "restricted_boundary_crossing",
  "start_seconds": 1.2,
  "end_seconds": 3.5
}
```

---

### 4. Deliverables & Export

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/investigations/{id}/report` | `GET` | Retrieve structured report domain record. Query `?format=markdown` for text summary. |
| `/api/v1/investigations/{id}/report/finalize` | `POST` | Finalize report, increment version, and optionally auto-slice clips for all confirmed events. |
| `/api/v1/investigations/{id}/export/html` | `GET` | Export self-contained interactive HTML deliverable with playable embedded clips. |
| `/api/v1/investigations/{id}/export/pdf` | `GET` | Export court-ready, publication-grade PDF deliverable. |

#### Report Finalize Payload Example
```json
{
  "finalized_by": "Chief Inspector Davis",
  "title": "Official Forensic Examination Report",
  "notes": "Case concluded. All confirmed incidents verified with video clips.",
  "auto_slice_clips": true
}
```

---

## WebSocket Telemetry Protocol

### Connection URL
```text
ws://localhost:8000/api/v1/investigations/{investigation_id}/telemetry
```

### Heartbeat
To keep connection alive through proxies and firewalls:
- Client transmits: `{"type": "ping"}` or `"ping"`
- Server responds: `{"event_type": "pong"}`

### Message Payload Schema
```json
{
  "event_type": "task_started | observation_detected | event_correlated | event_reviewed | report_finalized | state_changed",
  "timestamp": "2026-10-20T23:45:00.000Z",
  "investigation_id": "inv-demo-perimeter-01",
  "data": {
    "task_type": "visual_detection",
    "message": "Visual agent extracted 6 keyframes",
    "details": {}
  }
}
```

### UI Event Mapping
The UI matches `event_type` to activate agent roster chips:

| Received `event_type` | Agent Chip Activated | UI Action Triggered |
|---|---|---|
| `plan_created` | `Planner` | Adds telemetry entry |
| `task_started` | Corresponding Agent | Highlights active worker |
| `observation_detected` | `Visual` or `Audio` | Appends observation, increments counter |
| `event_correlated` | `Temporal` | Renders new timeline marker & event card |
| `coverage_updated` | `Verifier` | Refreshes coverage & evidence assessments |
| `report_finalized` | `Reporter` | Updates deliverable status badge |
| `state_changed` | All | Full dashboard state refresh |
