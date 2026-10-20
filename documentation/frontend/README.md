# VIGIL Video Forensics Frontend & Mission Control Suite

## Overview

The **VIGIL Frontend Mission Control** is a mission-critical web application designed for human forensic investigators to collaborate with autonomous, multimodal video-and-audio analysis agents.

Grounded in the requirements defined in [`documentation/architectures/VIGIL_vison_modelContext.txt`](../architectures/VIGIL_vison_modelContext.txt), the UI bridges raw footage, automated agentic observations, temporal correlation, human verification, and tamper-evident deliverable generation.

---

## Key System Capabilities

| Capability | Frontend Component | Forensic Value |
|---|---|---|
| **Autonomous Telemetry** | Agent Mission Control Panel | Real-time observation of Planner, Visual, Audio, Temporal, Verifier, and Reporter agent execution states via WebSockets. |
| **Multimodal Synchronized Player** | Center Media Station | Frame-accurate playback of primary surveillance video and sliced incident clips with SHA-256 integrity metadata. |
| **Multi-Track Forensic Timeline** | Interactive Scrubber & Marker Track | Interactive timecode scrub bar with color-coded event intervals (`confirmed`, `proposed`, `under_review`, `rejected`) and hover inspection. |
| **Human Review Station** | Verification & Triage Panel | One-click event verification, rejection (false positives), interval adjustment, reviewer badge assignment, and audit notes logging. |
| **On-Demand Clip Slicing** | Instant Incident Slicer | Direct H.264 video sub-clip extraction around event boundaries or playhead with configurable temporal padding. |
| **Evidence Intelligence Drawer** | Bottom Expandable Repository | Tabbed views for Extracted JPEG Frames (click-to-seek), Raw Model Observations, Evidence Quality/Uncertainty Assessments, Immutable Audit Logs, and Report Summary. |
| **Cryptographic Deliverables** | Deliverables Export Menu | One-click export of publication-grade PDF documents, interactive standalone HTML packages with embedded sub-clips, and Markdown summaries. |
| **Rapid Evaluation Seeder** | Demo Case Generator | 1-click synthetic case generation (`✨ Demo Case`) to immediately inspect the full end-to-end pipeline without uploading massive video files. |

---

## Directory Structure

```text
documentation/frontend/
├── README.md                               # This documentation index
├── ui_architecture_and_components.md       # Architectural breakdown of UI layers and state
├── user_guide_and_workflows.md             # Investigator operational guide & hotkeys
└── api_integration_and_contracts.md        # REST & WebSocket integration specifications

src/vigil/ui/
├── index.html                              # Mission control HTML layout
├── style.css                               # Cyber-forensic dark HUD styling
└── app.js                                  # Application state, video player HUD, & API bindings
```

---

## Quick Start: Launching the Frontend

### 1. Start the VIGIL API Server
From the project root:
```powershell
uv run uvicorn vigil.api.app:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Access the Forensic Mission Control
Open your browser to:
```text
http://localhost:8000/
# or
http://localhost:8000/dashboard
```

### 3. Load or Ingest Footage
- Click **`✨ Demo Case`** (or press <kbd>D</kbd>) to instantly load a pre-configured multi-modal forensic investigation with synthetic footage, frames, observations, and verified events.
- Or click **`+ Ingest Footage`** (or press <kbd>N</kbd>) to upload local MP4/MKV video footage.
