# VIGIL — Autonomous Video Forensics System: Complete Code Walkthrough

> **Reading Guide:** This document follows a **top-down approach** — starting from the project entry points, then diving into every module they depend on, layer by layer. Think of it like peeling an onion: we start at the outermost shell (how you *run* VIGIL) and work our way to the inner core (how data is shaped and stored).

---

## Table of Contents

1. [What is VIGIL?](#1-what-is-vigil)
2. [Project Folder Structure](#2-project-folder-structure)
3. [Entry Points — How to Start VIGIL](#3-entry-points--how-to-start-vigil)
   - 3.1 [`cli.py` — The Command-Line Interface](#31-clipy--the-command-line-interface)
   - 3.2 [`api/app.py` — The FastAPI Web Server](#32-apiapppy--the-fastapi-web-server)
4. [Configuration — `config.py`](#4-configuration--configpy)
5. [Logging — `logging_config.py`](#5-logging--logging_configpy)
6. [The API Layer (`src/vigil/api/`)](#6-the-api-layer-srcvigilapi)
   - 6.1 [`api/dependencies.py` — Singleton Services](#61-apidependenciespy--singleton-services)
   - 6.2 [`api/schemas.py` — Request & Response Shapes](#62-apischemaspy--request--response-shapes)
   - 6.3 [`api/routes/investigations.py` — All HTTP Endpoints](#63-apiroutesinvestigationspy--all-http-endpoints)
   - 6.4 [`api/routes/websocket.py` — Real-time Telemetry](#64-apirouteswebsocketpy--real-time-telemetry)
7. [Services Layer (`src/vigil/services/`)](#7-services-layer-srcvigilservices)
   - 7.1 [`services/investigation_service.py` — The Heart of VIGIL](#71-servicesinvestigation_servicepy--the-heart-of-vigil)
   - 7.2 [`services/telemetry.py` — Live Event Broadcasting](#72-servicestelemetrypy--live-event-broadcasting)
   - 7.3 [`services/exporter.py` — Report Export Engine](#73-servicesexporterpy--report-export-engine)
8. [The Agent Layer (`src/vigil/agent/`)](#8-the-agent-layer-srcvigilagent)
   - 8.1 [`agent/investigator.py` — The Orchestrator Brain](#81-agentinvestigatorpy--the-orchestrator-brain)
   - 8.2 [`agent/planner.py` — Investigation Planning](#82-agentplannerpy--investigation-planning)
   - 8.3 [`agent/registry.py` — Wiring up Tools to the Executor](#83-agentregistrypy--wiring-up-tools-to-the-executor)
   - 8.4 [Specialized Agents (`agent/specialized/`)](#84-specialized-agents-agentspecialized)
9. [Orchestration Layer (`src/vigil/orchestration/`)](#9-orchestration-layer-srcvigilorchestration)
   - 9.1 [`orchestration/executor.py` — Task Routing](#91-orchestrationexecutorpy--task-routing)
   - 9.2 [`orchestration/service.py` — Orchestration Service](#92-orchestrationservicepy--orchestration-service)
   - 9.3 [`orchestration/investigation_state.py` — Tracking Progress](#93-orchestrationinvestigation_statepy--tracking-progress)
   - 9.4 [`orchestration/task_types.py` — Task Contracts](#94-orchestrationtask_typespy--task-contracts)
   - 9.5 [`orchestration/transitions.py` — Lifecycle Rules](#95-orchestrationtransitionspy--lifecycle-rules)
10. [Tools Layer (`src/vigil/tools/`)](#10-tools-layer-srcvigiltools)
    - 10.1 [`tools/base.py` — Shared Helpers](#101-toolsbasepy--shared-helpers)
    - 10.2 [`tools/frame_extractor.py`](#102-toolsframe_extractorpy)
    - 10.3 [`tools/visual_detector.py`](#103-toolsvisual_detectorpy)
    - 10.4 [`tools/audio_transcriber.py`](#104-toolsaudio_transcriberpy)
    - 10.5 [`tools/event_correlator.py`](#105-toolsevent_correlatorpy)
    - 10.6 [`tools/evidence_assessor.py`](#106-toolsevidence_assessorpy)
    - 10.7 [`tools/coverage_tracker.py`](#107-toolscoverage_trackerpy)
    - 10.8 [`tools/report_generator.py`](#108-toolsreport_generatorpy)
    - 10.9 [`tools/clip_slicer.py`](#109-toolsclip_slicerpy)
    - 10.10 [`tools/media_ingestion.py`](#1010-toolsmedia_ingestionpy)
11. [Media Processing Layer (`src/vigil/media/`)](#11-media-processing-layer-srcvigilmedia)
    - 11.1 [`media/metadata.py` — Probing Video Files](#111-mediametadatapy--probing-video-files)
    - 11.2 [`media/decoder.py` — Extracting Frames & Audio](#112-mediadecoderpy--extracting-frames--audio)
    - 11.3 [`media/ingestion.py` — Full Ingestion Pipeline](#113-mediaingestionpy--full-ingestion-pipeline)
    - 11.4 [`media/slicer.py` — Cutting Video Clips](#114-mediaslicerpy--cutting-video-clips)
12. [LLM Models Layer (`src/vigil/models/`)](#12-llm-models-layer-srcvigilmodels)
    - 12.1 [`models/base.py` — The Common Interface](#121-modelsbasepy--the-common-interface)
    - 12.2 [`models/factory.py` — Choosing the Right AI Provider](#122-modelsfactorypy--choosing-the-right-ai-provider)
    - 12.3 [`models/gemini.py` — Google Gemini Client](#123-modelsgeminipy--google-gemini-client)
    - 12.4 [`models/nvidia_nim.py` — NVIDIA NIM Client](#124-modelsnvidia_nimpy--nvidia-nim-client)
    - 12.5 [`models/groq.py` — Groq Client](#125-modelsgroqpy--groq-client)
    - 12.6 [`models/local.py` — OpenAI-Compatible (Ollama/OpenRouter)](#126-modelslocalpy--openai-compatible-ollamaor-openrouter)
    - 12.7 [`models/mock.py` — Offline Testing Mock](#127-modelsmockpy--offline-testing-mock)
13. [Storage Layer (`src/vigil/storage/`)](#13-storage-layer-srcvigilstorage)
    - 13.1 [`storage/repository.py` — In-Memory Repository](#131-storagerepositorypy--in-memory-repository)
    - 13.2 [`storage/sqlite_repository.py` — Persistent SQLite Database](#132-storagesqlite_repositorypy--persistent-sqlite-database)
14. [Domain Layer (`src/vigil/domain/`)](#14-domain-layer-srcvigildomain)
15. [The Frontend UI (`src/vigil/ui/`)](#15-the-frontend-ui-srcvigilui)
16. [End-to-End Flow Summary](#16-end-to-end-flow-summary)

---

## 1. What is VIGIL?

**VIGIL** stands for **Autonomous Video Forensics System**. Imagine a highly trained digital detective that:

1. 🎥 **Takes a surveillance video** as input (e.g., a CCTV recording of a parking lot)
2. 🤖 **Automatically analyzes it** using multiple specialized AI agents working in sequence
3. 🔍 **Detects people, vehicles, anomalies**, and sounds
4. 📋 **Generates a detailed forensic report** with events, evidence quality ratings, and video clips
5. 👩‍💼 **Lets a human investigator review** the AI's findings, confirm or reject events, and finalize the report as a PDF or HTML document

VIGIL is built as a **Python web application** (FastAPI) with a REST API, WebSocket for live updates, and a browser-based dashboard.

---

## 2. Project Folder Structure

```
VIGIL/
├── src/
│   └── vigil/                  ← Main Python package
│       ├── __init__.py          ← Package entry point (exports everything)
│       ├── cli.py               ← Command-line interface (vigil serve, vigil review...)
│       ├── config.py            ← Configuration (API keys, storage paths, LLM providers)
│       ├── logging_config.py    ← Colorful, timestamped logging setup
│       │
│       ├── api/                 ← FastAPI web server & REST endpoints
│       │   ├── app.py           ← Creates and configures the FastAPI app
│       │   ├── dependencies.py  ← Singleton service providers
│       │   ├── schemas.py       ← API request/response data shapes (Pydantic)
│       │   └── routes/
│       │       ├── investigations.py ← All /api/v1/investigations/ endpoints
│       │       └── websocket.py      ← WebSocket telemetry endpoint
│       │
│       ├── agent/               ← AI agent layer (the brain)
│       │   ├── investigator.py  ← Main orchestrator (runs the full investigation)
│       │   ├── planner.py       ← Creates the step-by-step investigation plan
│       │   ├── registry.py      ← Registers all tool workers with the executor
│       │   └── specialized/     ← Individual specialized agents
│       │       ├── visual_agent.py       ← Handles frame extraction & visual analysis
│       │       ├── audio_agent.py        ← Handles audio transcription
│       │       ├── correlation_agent.py  ← Correlates observations into events
│       │       ├── verification_agent.py ← Assesses evidence quality
│       │       └── report_writer_agent.py ← Writes the forensic report
│       │
│       ├── orchestration/       ← Task execution and state management
│       │   ├── executor.py      ← Routes tasks to the right worker
│       │   ├── service.py       ← Orchestration service (state transitions + execution)
│       │   ├── investigation_state.py ← Tracks what's been done (running/completed)
│       │   ├── task_types.py    ← Data shapes for TaskRequest and TaskResult
│       │   └── transitions.py   ← Rules for valid state changes (CREATED → RUNNING etc.)
│       │
│       ├── tools/               ← Individual tool workers (do the actual work)
│       │   ├── base.py              ← Shared utilities for all tools
│       │   ├── frame_extractor.py   ← Extracts JPEG frames from video
│       │   ├── visual_detector.py   ← Sends frames to AI for visual analysis
│       │   ├── audio_transcriber.py ← Sends audio to AI for transcription
│       │   ├── event_correlator.py  ← Groups observations into timeline events
│       │   ├── evidence_assessor.py ← Rates evidence quality
│       │   ├── coverage_tracker.py  ← Records what parts of footage were examined
│       │   ├── report_generator.py  ← Creates the final investigation report
│       │   ├── clip_slicer.py       ← Cuts short video clips around incidents
│       │   └── media_ingestion.py   ← Ingests a media file into the repository
│       │
│       ├── media/               ← Physical video/audio file processing
│       │   ├── metadata.py      ← Probes file for duration, resolution, FPS, etc.
│       │   ├── decoder.py       ← Extracts JPEG frames and WAV audio
│       │   ├── ingestion.py     ← Coordinates metadata + decode + storage
│       │   └── slicer.py        ← Cuts video sub-clips using PyAV or OpenCV
│       │
│       ├── models/              ← AI/LLM provider clients
│       │   ├── base.py          ← Common interface (Protocol) all models must follow
│       │   ├── factory.py       ← Picks the right AI client based on config
│       │   ├── gemini.py        ← Google Gemini API client
│       │   ├── nvidia_nim.py    ← NVIDIA NIM API client (VLM + LLM)
│       │   ├── groq.py          ← Groq Cloud API client
│       │   ├── local.py         ← OpenAI-compatible client (Ollama, OpenRouter)
│       │   └── mock.py          ← Offline deterministic mock for testing
│       │
│       ├── domain/              ← Data schemas (what things *look like*)
│       │   ├── base.py              ← Base Pydantic model (strict validation)
│       │   ├── common.py            ← Shared types: Identifier, Timestamp, etc.
│       │   ├── investigation.py     ← The investigation record
│       │   ├── media_asset.py       ← Original video/audio file metadata
│       │   ├── artifact.py          ← Derived files (frames, clips, audio)
│       │   ├── observation.py       ← A single AI finding (e.g., "person detected")
│       │   ├── event.py             ← A confirmed/proposed incident (e.g., "intruder entered")
│       │   ├── event_link.py        ← Relationship between two events
│       │   ├── evidence_assessment.py ← Quality rating of evidence
│       │   ├── coverage.py          ← Which parts of footage were examined
│       │   ├── report.py            ← The final forensic report
│       │   ├── audit.py             ← Immutable log of human review actions
│       │   ├── camera.py            ← Camera metadata (location, timezone)
│       │   ├── entity.py            ← Detected entity (person, vehicle)
│       │   ├── provenance.py        ← Tracks how an observation was produced
│       │   └── source_reference.py  ← Precise timestamp pointer in a media file
│       │
│       ├── services/            ← Application-level services
│       │   ├── investigation_service.py ← Main coordinator (ingestion + orchestration)
│       │   ├── telemetry.py             ← WebSocket live event broadcaster
│       │   └── exporter.py              ← Generates HTML & PDF reports
│       │
│       ├── storage/             ← Data persistence
│       │   ├── repository.py           ← In-memory store (base interface + default impl)
│       │   └── sqlite_repository.py    ← SQLite-backed persistent store
│       │
│       └── ui/                  ← Browser-based dashboard (HTML/JS/CSS)
│           ├── index.html
│           ├── app.js
│           └── style.css
│
├── tests/                       ← All automated tests
├── .env                         ← Your API keys (not committed to git)
├── .env.example                 ← Template showing what keys are needed
├── pyproject.toml               ← Project metadata and dependencies
└── requirements.txt             ← Python package dependencies
```

---

## 3. Entry Points — How to Start VIGIL

There are **two ways** to interact with VIGIL:

### 3.1 `cli.py` — The Command-Line Interface

**File:** `src/vigil/cli.py`

This is the file that runs when you type `vigil` in your terminal. It provides a text-based menu system.

**Available commands:**

| Command | What it does |
|---|---|
| `vigil serve` | Starts the web server (FastAPI) so you can use the REST API and browser UI |
| `vigil review event <inv_id> <event_id> --status confirmed --reviewer Alice` | Confirms or rejects a specific event in the investigation |
| `vigil review list-events <inv_id>` | Lists all events and their review status |
| `vigil audit <inv_id>` | Shows the complete audit trail (who did what and when) |
| `vigil finalize-report <inv_id> --finalized-by Alice` | Officially locks the report as final |
| `vigil export <inv_id> --format pdf` | Downloads the report as a PDF or HTML file |

**How it works:**
```
main()
  └── build_parser()       ← Sets up all the command/subcommand options
  └── args.func(args)      ← Calls the right handler (e.g., handle_serve, handle_review_event)
```

**Key function: `handle_serve(args)`**
This calls `uvicorn.run("vigil.api.app:app", ...)` — which boots up the FastAPI web server.

---

### 3.2 `api/app.py` — The FastAPI Web Server

**File:** `src/vigil/api/app.py`

When you run `vigil serve`, this file is what actually becomes the running server. It is built using **FastAPI** — a modern Python web framework.

**What `create_app()` does step by step:**

1. **Creates the FastAPI app** with a title and description
2. **Sets up CORS** — allows the browser dashboard to talk to the API from any origin
3. **Adds a logging middleware** — logs every HTTP request with timing and color-coded status codes
4. **Registers an error handler** — if something isn't found (404), returns a clean JSON error
5. **Adds health check endpoints** at `/health` and `/api/v1/health`
6. **Mounts the UI** — serves the `src/vigil/ui/` folder as static files at `/ui`
7. **Includes two routers:**
   - `investigations_router` — all the investigation endpoints (`/api/v1/investigations/...`)
   - `websocket_router` — the live telemetry WebSocket

**Lifespan (startup/shutdown):**
```python
@asynccontextmanager
async def lifespan(app):
    # On startup: register the event loop with TelemetryManager
    yield
    # On shutdown: cleanly stop background investigation workers
```

---

## 4. Configuration — `config.py`

**File:** `src/vigil/config.py`

This is the **settings hub** of VIGIL. It reads your `.env` file and environment variables to figure out which AI provider to use, where to store data, etc.

**`VigilConfig` dataclass fields:**

| Field | What it controls |
|---|---|
| `llm_provider` | Which AI to use: `"gemini"`, `"groq"`, `"nvidia_nim"`, `"ollama"`, `"openrouter"`, or `"mock"` |
| `gemini_api_key` | Your Google Gemini API key |
| `gemini_model` | Which Gemini model (default: `"gemini-2.0-flash"`) |
| `groq_api_key` | Your Groq Cloud API key |
| `nvidia_api_key` | Your NVIDIA NIM API key |
| `storage_root` | Folder where SQLite database and extracted frames are saved (default: `./storage_data`) |
| `log_level` | Logging verbosity (default: `"INFO"`) |

**Provider auto-detection:**
```python
# If no provider is set explicitly, VIGIL checks which API keys are available:
if nvidia_key:   → use "nvidia_nim"
elif gemini_key: → use "gemini"
elif groq_key:   → use "groq"
else:            → use "mock" (offline testing mode)
```

**Usage everywhere:** The module-level `config = VigilConfig.from_env()` is imported by other modules so there's always one global config object.

---

## 5. Logging — `logging_config.py`

**File:** `src/vigil/logging_config.py`

This sets up beautiful, color-coded terminal output for the entire application.

**What it does:**
- **Colorizes log levels**: DEBUG=cyan, INFO=green, WARNING=yellow, ERROR=red, CRITICAL=white-on-red
- **Colorizes HTTP status codes**: 200 OK=bright green, 404 NOT FOUND=bright yellow, 500=bright red
- **Uses a custom formatter** `VigilColorizedFormatter` that produces lines like:
  ```
  2026-10-22 16:05:00 +0530 | INFO     | vigil.api.app | VIGIL API services initialized.
  ```
- **On Windows**, enables ANSI escape codes (for terminal colors) using the Windows Console API

**`configure_logging()`** — called once at startup from `api/app.py` to install this configuration globally.

---

## 6. The API Layer (`src/vigil/api/`)

### 6.1 `api/dependencies.py` — Singleton Services

**File:** `src/vigil/api/dependencies.py`

This is a **dependency injection** file. FastAPI calls these functions whenever a route needs a service. The `@functools.lru_cache(maxsize=1)` decorator ensures each service is **only created once** (singleton pattern).

```python
get_telemetry_manager() → TelemetryManager   # One instance for live WebSocket events
get_investigation_service() → InvestigationService  # One instance for all investigation work
```

`get_investigation_service()` creates:
- A `SqliteInvestigationRepository` backed by `vigil.db` in the storage directory
- A `TelemetryManager` (for WebSocket broadcasting)
- Returns an `InvestigationService` wiring them together

---

### 6.2 `api/schemas.py` — Request & Response Shapes

**File:** `src/vigil/api/schemas.py`

These are **Pydantic models** — they define the exact shape of data that the API accepts from clients (requests) and sends back (responses). Think of them as "contracts" for the API.

| Schema | Purpose |
|---|---|
| `InvestigationCreateResponse` | Returned after starting a new investigation (includes `investigation_id`, `status`, `frame_count`) |
| `InvestigationStatusResponse` | Returned when polling investigation progress |
| `InvestigationSummaryResponse` | Short summary for listing all investigations |
| `TelemetryEventMessage` | WebSocket message format for live events |
| `EventReviewRequest` | Input from a human reviewer (confirm/reject + notes) |
| `EventReviewResponse` | Response after reviewing an event (updated event + audit log) |
| `EventEditRequest` | Input for directly editing event fields |
| `ReportFinalizeRequest` | Input to lock and finalize the report |
| `ReportFinalizeResponse` | Response after finalizing (includes version, clip count) |
| `IncidentClipSliceRequest` | Input to cut a video clip around an event (padding seconds) |

---

### 6.3 `api/routes/investigations.py` — All HTTP Endpoints

**File:** `src/vigil/api/routes/investigations.py`

This is the **main router** — all URLs starting with `/api/v1/investigations/` are handled here.

**Complete API Endpoint Reference:**

| Method | URL | What it does |
|---|---|---|
| `POST` | `/api/v1/investigations` | Upload a video file, ingest it, and start the investigation |
| `GET` | `/api/v1/investigations` | List all investigations |
| `GET` | `/api/v1/investigations/{id}` | Get full details of one investigation |
| `GET` | `/api/v1/investigations/{id}/status` | Poll investigation progress (running/completed?) |
| `GET` | `/api/v1/investigations/{id}/report` | Get the forensic report (can also return Markdown, HTML, or PDF) |
| `GET` | `/api/v1/investigations/{id}/observations` | Get all AI-detected observations |
| `GET` | `/api/v1/investigations/{id}/events` | Get all correlated events (filterable by status) |
| `GET` | `/api/v1/investigations/{id}/coverage` | Get coverage records (what portions of footage were examined) |
| `GET` | `/api/v1/investigations/{id}/artifacts` | Get extracted frames, audio segments, and clips |
| `GET` | `/api/v1/investigations/{id}/events/{event_id}` | Get one specific event |
| `POST` | `/api/v1/investigations/{id}/events/{event_id}/review` | Human review: confirm or reject an event |
| `PATCH` | `/api/v1/investigations/{id}/events/{event_id}` | Directly edit event fields (description, timestamps) |
| `POST` | `/api/v1/investigations/{id}/events/{event_id}/clip` | Cut a playable video clip around an event |
| `GET` | `/api/v1/investigations/{id}/audit` | Get the full audit trail |
| `POST` | `/api/v1/investigations/{id}/report/finalize` | Finalize the report |
| `GET` | `/api/v1/investigations/{id}/export/html` | Download report as interactive HTML |
| `GET` | `/api/v1/investigations/{id}/export/pdf` | Download report as PDF |
| `GET` | `/api/v1/investigations/{id}/artifacts/{artifact_id}/content` | Stream/download a frame image, audio, or clip |
| `GET` | `/api/v1/investigations/{id}/media` | Get media assets for investigation |
| `GET` | `/api/v1/investigations/{id}/media/primary/content` | Stream the primary video file |
| `GET` | `/api/v1/investigations/{id}/media/{media_asset_id}/content` | Stream a specific media file |
| `GET` | `/api/v1/investigations/{id}/assessments` | Get evidence quality assessments |
| `POST` | `/api/v1/investigations/demo` | Create a pre-filled demo investigation (no video file needed) |

**Key flow for creating an investigation (POST `/api/v1/investigations`):**
```
1. Save uploaded file to disk (or use file_path)
2. Call service.create_and_ingest_investigation() → extracts frames, audio
3. Call service.run_investigation() → starts the AI pipeline (async by default)
4. Return investigation_id so client can poll for status
```

---

### 6.4 `api/routes/websocket.py` — Real-time Telemetry

**File:** `src/vigil/api/routes/websocket.py`

Provides **live streaming updates** via WebSocket so a dashboard can show real-time progress.

**Two WebSocket URLs:**
- `/api/v1/investigations/{id}/telemetry` — primary
- `/ws/investigations/{id}` — convenience alias

**How it works:**
1. Browser connects to the WebSocket URL
2. Server accepts and registers the connection via `telemetry.connect()`
3. Any past events (buffered) are immediately replayed to the new client
4. While the investigation runs, new events are pushed in real-time
5. The browser sends `"ping"` → server responds `{"event_type": "pong"}` to keep the connection alive
6. When the browser disconnects, the connection is removed via `telemetry.disconnect()`

---

## 7. Services Layer (`src/vigil/services/`)

### 7.1 `services/investigation_service.py` — The Heart of VIGIL

**File:** `src/vigil/services/investigation_service.py`

This is the **central coordinator** that connects all the pieces. It's like the operations director who tells everyone what to do.

**What it manages:**
- Creating and ingesting investigations (media files → database)
- Running investigations (kicking off the AI agent pipeline)
- Human review workflows (confirm/reject events, edit data)
- Report finalization and export
- Background job tracking via `ThreadPoolExecutor`

**Key methods explained:**

#### `create_and_ingest_investigation(file_path, ...)`
```
1. Creates a unique investigation ID (e.g., "inv-3a7b9f12")
2. Calls media_service.ingest_file() to extract frames and audio from the video
3. Creates an Investigation domain object and saves it to the database
4. Saves initial state (status: CREATED)
5. Broadcasts "investigation_created" event to any connected WebSocket clients
```

#### `run_investigation(investigation_id, run_async=True)`
```
1. Retrieves the investigation from the database
2. Creates a telemetry callback function (for live event broadcasting)
3. If run_async=True: submits orchestrator.run_investigation() to a thread pool → returns immediately
4. If run_async=False: runs it directly and waits for it to finish
```

#### `review_event(investigation_id, event_id, status, reviewer, ...)`
```
1. Fetches the event from the database
2. Validates the new status ("confirmed", "rejected", "under_review", "proposed")
3. Creates an updated Event with the new status, reviewer, and notes
4. Saves the updated event back to the database
5. Creates an AuditLog entry recording who made the decision
6. Broadcasts "event_reviewed" to WebSocket clients
7. Returns the updated event and audit log
```

#### `finalize_report(investigation_id, finalized_by, ...)`
```
1. Counts confirmed, rejected, and pending events
2. Auto-cuts video clips for confirmed events (if auto_slice_clips=True)
3. Builds a final summary text with review statistics
4. Creates a new Report with version number incremented
5. Saves to database and creates audit log
6. Broadcasts "report_finalized" to WebSocket clients
```

---

### 7.2 `services/telemetry.py` — Live Event Broadcasting

**File:** `src/vigil/services/telemetry.py`

Manages **WebSocket connections** and broadcasts events to all connected dashboard clients.

**How it works:**
- Maintains a dictionary of `{investigation_id: [list of WebSocket connections]}`
- When an event happens (e.g., new observation detected), `broadcast()` is called
- It pushes the event JSON to every connected WebSocket client watching that investigation
- It also **buffers recent events** so that a new client connecting after the investigation started gets caught up immediately
- Thread-safe: uses `asyncio` event loops for pushing messages from background threads

**Events that get broadcast:**
- `investigation_created` — when a new investigation is registered
- `state_changed` — when status changes (CREATED → RUNNING → COMPLETED)
- `plan_created` — when the task plan is ready
- `task_started` / `task_completed` — for each investigation phase
- `observation_detected` — when AI finds something in a frame
- `event_correlated` — when observations are grouped into an event
- `coverage_updated` — when a footage interval is marked as examined
- `investigation_completed` / `investigation_failed` — at the end
- `event_reviewed` — when a human reviews an event

---

### 7.3 `services/exporter.py` — Report Export Engine

**File:** `src/vigil/services/exporter.py`

Generates polished **HTML and PDF forensic reports** from investigation data.

#### `ReportExporter.export_html(...)`
Produces a **dark-themed, responsive HTML document** containing:
- A styled header with report metadata and media SHA-256 hash
- Statistics bar: total observations, events, confirmed count, rejected count
- Executive summary with the AI-generated text
- Cards for each event with:
  - Status badge (confirmed=green, rejected=red, proposed=yellow)
  - Timeline info (start/end seconds)
  - Human reviewer's notes
  - Embedded `<video>` player for incident clips
- Evidence assessments table
- Coverage records table
- Observations list
- Audit trail table

#### `ReportExporter.export_pdf(...)`
Uses **ReportLab** (a PDF generation library) to create a court-ready PDF with:
- Styled title page with report metadata
- Event table with status color coding
- Incident video clip chain of custody table (clip ID, interval, SHA-256 hash)
- Investigator audit trail table
- Numbered pages

---

## 8. The Agent Layer (`src/vigil/agent/`)

This is the **AI decision-making layer** — it coordinates the investigation plan and delegates work to specialized sub-agents.

### 8.1 `agent/investigator.py` — The Orchestrator Brain

**File:** `src/vigil/agent/investigator.py`

**`AgenticOrchestrator`** is the top-level coordinator. It:
- Holds references to all 5 specialized agents
- Runs the complete investigation lifecycle from start to finish

**`InvestigationOutcome`** — the final result object containing:
- The Investigation record
- The final InvestigationState
- The generated Report
- All TaskResults, Observations, Events, Evidence Assessments, and Coverage Records

#### `run_investigation(investigation, event_callback)` — Step-by-step walkthrough:

```
1. Save investigation to repository
2. Initialize state (status=CREATED), save it
3. Generate the investigation plan (list of PlannedTasks) via planner
4. Emit "state_changed" and "plan_created" events

For each planned task (frame_sampling → visual_analysis → audio_transcription → ...):
  a. Convert PlannedTask into a TaskRequest
  b. Emit "task_started" event
  c. Call self.step(state, task_request) → executes the task
  d. Update state with new observation/event IDs
  e. Emit "observation_detected" for each new observation
  f. Emit "event_correlated" for each new event
  g. Emit "task_completed" event
  h. If task FAILED → emit "investigation_failed" and STOP the loop

5. If all tasks succeed → mark investigation as COMPLETED
6. Retrieve the final report from repository
7. Emit "investigation_completed"
8. Collect all observations, events, assessments, coverage records
9. Return InvestigationOutcome
```

#### `step(state, request)` — Executes one task:
```
1. Calls service.execute_task() → runs the appropriate tool worker
2. Extracts new observation IDs and event IDs from the task result
3. Merges them into the investigation state
4. Saves updated state to repository
5. Returns the updated state and task result
```

> **Note:** `LeadInvestigatorAgent = AgenticOrchestrator` — just a backward-compatible alias name.

---

### 8.2 `agent/planner.py` — Investigation Planning

**File:** `src/vigil/agent/planner.py`

`InvestigationPlanner` decomposes an investigation into **7 sequential phases**:

| Phase | Task Type | What happens |
|---|---|---|
| 1 | `frame_sampling` | Extract JPEG frames every 2 seconds (up to 8 frames) |
| 2 | `visual_analysis` | Analyze extracted frames with AI (detect people, vehicles, objects) |
| 3 | `audio_transcription` | Transcribe speech and identify acoustic events (alarms, sirens) |
| 4 | `event_correlation` | Group related observations into chronological Events |
| 5 | `evidence_assessment` | Rate each event's evidence quality (high/moderate/low/insufficient) |
| 6 | `coverage_evaluation` | Record which parts of the footage were actually examined |
| 7 | `report_generation` | Synthesize everything into a final forensic Report |

**`PlannedTask`** — a simple container with `task_type`, `description`, `input_refs`, and `parameters`. Its `.to_task_request()` method generates a `TaskRequest` with a unique ID.

---

### 8.3 `agent/registry.py` — Wiring up Tools to the Executor

**File:** `src/vigil/agent/registry.py`

`create_default_executor()` creates a `TaskExecutor` and registers **all 10 tool workers** with their task type names:

```
"media_ingestion"          → MediaIngestionWorker
"frame_sampling"           → FrameExtractorWorker
"clip_extraction"          → FrameExtractorWorker (same worker, different name)
"clip_slicing"             → ClipSlicerWorker
"incident_clip_extraction" → ClipSlicerWorker
"visual_analysis"          → VisualDetectorWorker
"audio_transcription"      → AudioTranscriberWorker
"event_correlation"        → EventCorrelatorWorker
"evidence_assessment"      → EvidenceAssessorWorker
"coverage_evaluation"      → CoverageTrackerWorker
"report_generation"        → ReportGeneratorWorker
```

---

### 8.4 Specialized Agents (`agent/specialized/`)

These are thin wrapper agents that each know how to call **one specific type of task** via the orchestration service. They exist so other code can call `visual_agent.analyze_frames(...)` instead of building a raw `TaskRequest`.

| Agent | File | What it can do |
|---|---|---|
| `VisualAgent` | `visual_agent.py` | `extract_frames()` and `analyze_frames()` |
| `AudioAgent` | `audio_agent.py` | `analyze_audio()` — transcription + acoustic detection |
| `TemporalCorrelationAgent` | `correlation_agent.py` | `correlate()` — links observations into timeline events |
| `EvidenceVerificationAgent` | `verification_agent.py` | `verify_evidence()` and `evaluate_coverage()` |
| `ReportWriterAgent` | `report_writer_agent.py` | `generate_report()` — compiles findings into a Report |

Each agent's method:
1. Creates a unique `task_id`
2. Wraps parameters into a `TaskRequest`
3. Calls `self.service.execute_task(state, request)` → returns `TaskExecutionOutcome`

---

## 9. Orchestration Layer (`src/vigil/orchestration/`)

This layer manages **how tasks are routed to workers** and **how investigation state transitions**.

### 9.1 `orchestration/executor.py` — Task Routing

**File:** `src/vigil/orchestration/executor.py`

`TaskExecutor` is a simple **registry + dispatcher**:
- `register(task_type, worker)` — maps a string like `"visual_analysis"` to a worker object
- `execute(request)` — looks up the worker, calls `worker.execute(request)`, validates the result

**Validation rules:**
- Worker must return a `TaskResult` object
- The result's `task_id` must match the request's `task_id`
- Status must be final (`COMPLETED`, `FAILED`, or `PARTIAL`) — not `PENDING` or `RUNNING`

**Errors:**
- `UnknownTaskTypeError` — if no worker is registered for that task type
- `TaskResultContractError` — if the worker breaks the result contract

---

### 9.2 `orchestration/service.py` — Orchestration Service

**File:** `src/vigil/orchestration/service.py`

`OrchestrationService` is the **layer between the orchestrator and the executor**. It:
- Manages state transitions (CREATED → RUNNING, etc.)
- Wraps errors in a structured `TaskResult`
- Returns `TaskExecutionOutcome(state, task_result)` after each step

**`execute_task(state, request)` flow:**
```
1. Transition state to RUNNING (if not already)
2. Call executor.execute(request) → runs the worker
3. Wrap exceptions into a FAILED TaskResult with ErrorDetail
4. Return TaskExecutionOutcome with updated state
```

**`complete_investigation(state)`:**
```
1. Transition state from RUNNING → COMPLETED
2. Return updated state
```

---

### 9.3 `orchestration/investigation_state.py` — Tracking Progress

**File:** `src/vigil/orchestration/investigation_state.py`

`InvestigationState` is like a **progress tracker** for an investigation. It's a Pydantic model that records:
- `investigation_id` — which investigation this is
- `status` — current lifecycle status (CREATED/RUNNING/PAUSED/COMPLETED/FAILED)
- `task_ids` — IDs of tasks that have been executed
- `observation_ids` — IDs of observations discovered so far
- `event_ids` — IDs of events correlated so far
- `created_at`, `started_at`, `completed_at`, `updated_at` — timing info

`InvestigationStatus` (enum):
- `CREATED` → `RUNNING` → `COMPLETED`
- `RUNNING` → `PAUSED` → `RUNNING`
- `RUNNING` → `FAILED`

---

### 9.4 `orchestration/task_types.py` — Task Contracts

**File:** `src/vigil/orchestration/task_types.py`

Defines the data shapes for task communication:

**`TaskRequest`** — input to a worker:
- `task_id` — unique ID for this task execution
- `task_type` — what kind of task (e.g., `"visual_analysis"`)
- `input_refs` — IDs of media assets or artifacts to process
- `parameters` — additional settings (e.g., `{"max_frames": 8}`)
- `requested_by` — who/what requested this task

**`TaskResult`** — output from a worker:
- `task_id` — must match the request
- `status` — COMPLETED, PARTIAL, or FAILED
- `output_refs` — IDs of things produced (observation IDs, event IDs, etc.)
- `error` — ErrorDetail if status is FAILED

**`ErrorDetail`** — structured error information:
- `code` — machine-readable code (e.g., `"MEDIA_NOT_FOUND"`)
- `message` — human-readable explanation
- `retryable` — whether retrying might succeed
- `retry_after_seconds` — minimum wait before retrying

**`ModelOutput`** — structured output from an AI call (used by tools internally).

---

### 9.5 `orchestration/transitions.py` — Lifecycle Rules

**File:** `src/vigil/orchestration/transitions.py`

Defines **valid state transitions** for an investigation:

```
CREATED  → RUNNING, FAILED
RUNNING  → PAUSED, COMPLETED, FAILED
PAUSED   → RUNNING, FAILED
COMPLETED → (terminal — no transitions allowed)
FAILED    → (terminal — no transitions allowed)
```

`transition_state(state, new_status)` — validates the transition and returns a new state object with updated timestamps (`started_at` when moving to RUNNING, `completed_at` when COMPLETED or FAILED).

---

## 10. Tools Layer (`src/vigil/tools/`)

These are the **actual workers** that do real work. Each one implements the `TaskWorker` protocol with an `execute(request) → TaskResult` method.

### 10.1 `tools/base.py` — Shared Helpers

Common utility functions used by all tools:
- `generate_sha256(text)` — creates a SHA-256 hash from a string (used for generating deterministic IDs)
- Helper functions for building observations, artifacts, and other domain objects

---

### 10.2 `tools/frame_extractor.py`

**Task type:** `"frame_sampling"` and `"clip_extraction"`

**What it does:**
1. Gets media asset IDs from the task request's `input_refs`
2. For each media asset, retrieves its file path from the repository
3. Calls `MediaDecoder.extract_frames()` to get JPEG images
4. Creates `Artifact` records in the repository for each frame
5. Returns a `TaskResult` with the artifact IDs in `output_refs`

**Parameters:**
- `sample_interval_seconds` — how often to extract a frame (default: 2.0s)
- `max_frames` — maximum number of frames to extract

---

### 10.3 `tools/visual_detector.py`

**Task type:** `"visual_analysis"`

**What it does:**
1. Gets all frame artifacts from the investigation
2. For each frame, reads the JPEG file and encodes it as Base64
3. Calls `llm_client.analyze_image(prompt, image_data)` → AI analyzes the frame
4. Parses the AI's JSON response to extract observations
5. Creates `Observation` records in the repository for each detected entity
6. Returns a `TaskResult` with the observation IDs

**The prompt sent to the AI looks like:**
> "You are a forensic video analyst. Analyze this surveillance frame and identify: persons (clothing, direction), vehicles (color, type), objects, and any anomalies. Return structured JSON..."

---

### 10.4 `tools/audio_transcriber.py`

**Task type:** `"audio_transcription"`

**What it does:**
1. Gets audio artifact files (WAV) from the investigation
2. Calls the AI to transcribe speech and identify acoustic events
3. Creates `Observation` records with `modality="audio"` and `observation_type="audio_transcription"`
4. Returns observation IDs in the `TaskResult`

> For providers like Groq (which supports Whisper), the audio file is sent directly. For other providers, the audio content is described in a text prompt.

---

### 10.5 `tools/event_correlator.py`

**Task type:** `"event_correlation"`

**What it does:**
1. Fetches all observations collected so far in the investigation
2. Sends them to the LLM as a structured prompt
3. Asks the AI: "Given these observations, what distinct events occurred? When did they start/end?"
4. Parses the AI's JSON response into `Event` objects
5. Creates `EventLink` records to show relationships between events
6. Saves everything to the repository
7. Returns event IDs in the `TaskResult`

**Example output:** The AI might return:
- Event: "Restricted area entry" (start: 5s, end: 12s, observations: [obs-001, obs-002])
- Event: "Vehicle departure" (start: 20s, end: 35s, observations: [obs-003])
- EventLink: "restricted_area_entry" is `before` "vehicle_departure"

---

### 10.6 `tools/evidence_assessor.py`

**Task type:** `"evidence_assessment"`

**What it does:**
1. Fetches all events from the investigation
2. For each event, asks the LLM: "Rate the evidence quality, support level, and uncertainty"
3. Creates `EvidenceAssessment` records with ratings: `high`, `moderate`, `low`, or `insufficient`
4. Saves assessments to the repository
5. Returns assessment IDs in `TaskResult`

---

### 10.7 `tools/coverage_tracker.py`

**Task type:** `"coverage_evaluation"`

**What it does:**
1. Fetches all media assets for the investigation
2. Checks which time intervals were examined by looking at existing artifacts
3. Creates `CoverageRecord` objects for each interval:
   - `status="examined"` if frames/audio were extracted
   - `status="not_examined"` for gaps in coverage
4. Saves coverage records to the repository

---

### 10.8 `tools/report_generator.py`

**Task type:** `"report_generation"`

**What it does:**
1. Collects all observations, events, assessments, and coverage records
2. Sends a summary to the LLM and asks it to write an executive summary
3. Creates a `Report` domain object with all the references
4. Saves the report to the repository
5. Returns the report ID in `TaskResult`

---

### 10.9 `tools/clip_slicer.py`

**Task type:** `"clip_slicing"` and `"incident_clip_extraction"`

**What it does:**
1. Takes event timing information (start/end seconds)
2. Locates the original media file
3. Calls `ClipSlicer.slice_clip()` to cut a short MP4 clip around the event
4. Creates an `Artifact` record with `artifact_type="clip"`
5. Returns the clip artifact ID

---

### 10.10 `tools/media_ingestion.py`

**Task type:** `"media_ingestion"`

**What it does:**
1. Takes a media file path from the task parameters
2. Calls `MediaIngestionService.ingest_file()` to extract metadata, frames, and audio
3. Returns the media asset ID and artifact IDs in `TaskResult`

---

## 11. Media Processing Layer (`src/vigil/media/`)

This layer handles **physical video file operations** — reading, decoding, and slicing.

### 11.1 `media/metadata.py` — Probing Video Files

**File:** `src/vigil/media/metadata.py`

`MediaMetadataExtractor` probes a video file and returns a `MediaMetadata` object containing:
- `duration_seconds`, `fps`, `width`, `height`
- `video_codec`, `audio_codec`
- `has_video`, `has_audio`
- `sha256` — file integrity checksum
- `file_size_bytes`

**How it probes files (with fallback strategy):**
1. **First try: PyAV** — more accurate, handles more formats
2. **Fallback: OpenCV** — for common video files
3. **Final fallback: OpenCV image reader** — for still images

`to_media_asset()` — converts `MediaMetadata` into a `MediaAsset` domain object ready to save in the database.

---

### 11.2 `media/decoder.py` — Extracting Frames & Audio

**File:** `src/vigil/media/decoder.py`

`MediaDecoder` does the heavy lifting of actually reading video data:

#### `extract_frames(file_path, output_dir, sample_interval_seconds, max_frames)`
- Opens the video with PyAV (or falls back to OpenCV)
- Iterates through frames and picks ones at the specified interval
- Encodes each selected frame as a JPEG file to disk
- Returns a list of `ExtractedFrame` objects (each has `file_path`, `timestamp_seconds`, `sha256`, `width`, `height`)

#### `demux_audio_to_wav(file_path, output_path)`
- Opens the video with PyAV
- Extracts the audio stream
- Resamples to 16kHz (standard for speech recognition)
- Writes a 16-bit PCM WAV file to disk
- Returns a `DemuxedAudio` object (with `file_path`, `duration_seconds`, `sample_rate`, `sha256`)

---

### 11.3 `media/ingestion.py` — Full Ingestion Pipeline

**File:** `src/vigil/media/ingestion.py`

`MediaIngestionService` coordinates the complete ingestion process:

```
ingest_file(file_path, ...) steps:
1. Extract metadata (via MediaMetadataExtractor)
2. Create/lookup Camera object (if camera_id provided)
3. Create MediaAsset and save to repository
4. Create output directory for artifacts
5. Extract JPEG frames (if has_video) → create Artifact records
6. Extract WAV audio (if has_audio and extract_audio=True) → create Artifact record
7. Return IngestionResult with all created objects
```

**`IngestionResult`** contains:
- `media_asset` — the registered MediaAsset
- `camera` — the Camera object (or None)
- `frame_artifacts` — list of JPEG frame Artifacts
- `audio_artifacts` — list of WAV audio Artifacts

---

### 11.4 `media/slicer.py` — Cutting Video Clips

**File:** `src/vigil/media/slicer.py`

`ClipSlicer.slice_clip(source_path, output_path, start_seconds, end_seconds, padding_seconds)`:

1. Validates parameters (start must be < end, both non-negative)
2. Applies padding: actual clip starts `padding_seconds` before the event and ends `padding_seconds` after
3. **First try: PyAV** — re-encodes video as H264 MP4 with AAC audio
4. **Fallback: OpenCV VideoWriter** — frame-by-frame copy for simpler formats
5. Returns a `SliceResult` with `clip_path`, `sha256`, timing, and dimensions

---

## 12. LLM Models Layer (`src/vigil/models/`)

### 12.1 `models/base.py` — The Common Interface

**File:** `src/vigil/models/base.py`

Defines **what every AI client must be able to do** using a Python `Protocol`:

```python
class BaseLLMClient(Protocol):
    def generate_text(prompt, system_instruction=None, json_mode=False) → LLMResponse
    def analyze_image(prompt, image_data, mime_type, ...) → LLMResponse
```

`LLMResponse` contains:
- `content` — the text output from the model
- `model_name` — which model produced it
- `prompt_tokens`, `completion_tokens` — token usage statistics

Any class implementing these two methods can be used as an LLM client in VIGIL.

---

### 12.2 `models/factory.py` — Choosing the Right AI Provider

**File:** `src/vigil/models/factory.py`

`get_llm_client(app_config, override_provider)` reads the configuration and instantiates the right client:

```
provider = "nvidia_nim" → NvidiaNIMClient (requires NVIDIA_API_KEY)
provider = "gemini"     → GeminiClient   (requires GEMINI_API_KEY)
provider = "groq"       → GroqClient     (requires GROQ_API_KEY)
provider = "ollama"     → OpenAICompatibleClient (local Ollama server)
provider = "openrouter" → OpenAICompatibleClient (requires OPENROUTER_API_KEY)
else                    → MockLLMClient  (offline, deterministic)
```

If a key is missing, it falls back to `MockLLMClient` with a warning.

---

### 12.3 `models/gemini.py` — Google Gemini Client

**File:** `src/vigil/models/gemini.py`

Communicates with **Google's Gemini API** using raw HTTP (`urllib.request`).

**Key features:**
- **Rate limiting:** Uses a global `threading.Semaphore` to limit concurrent requests to 2 (Gemini free tier allows 15 req/min)
- **Retry with exponential backoff + full jitter:** Retries up to 5 times on errors 429/500/502/503/504
- **Image handling:** Automatically reads local file URIs and converts to Base64 for the API

**`generate_text(prompt)`:** Calls Gemini's `generateContent` endpoint with text-only input.

**`analyze_image(prompt, image_data)`:** Sends both text prompt and Base64-encoded image to the multimodal model.

---

### 12.4 `models/nvidia_nim.py` — NVIDIA NIM Client

**File:** `src/vigil/models/nvidia_nim.py`

NVIDIA NIM uses **two separate models** (dual-model architecture):
- **VLM (Visual):** `meta/llama-3.2-11b-vision-instruct` — for analyzing images/frames
- **LLM (Text):** `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` — for reasoning, timeline reconstruction, report writing

**Key features:**
- **Global lock** (`threading.Lock`): Only ONE request can be in-flight at a time (prevents free-tier exhaustion)
- **Mandatory inter-request delay:** 2 seconds between successful requests (configurable via env)
- **Exponential backoff with minimum 5s delay** — gives NVIDIA's worker pool time to recover
- Routes calls to the right endpoint based on model type

---

### 12.5 `models/groq.py` — Groq Client

**File:** `src/vigil/models/groq.py`

Communicates with **Groq Cloud's API** which is OpenAI-compatible.

- `generate_text()` — uses Groq's LLM models (e.g., `llama-3.3-70b-versatile`)
- `analyze_image()` — uses Groq's vision model (e.g., `llama-3.2-11b-vision-preview`)
- For audio (Whisper), there's a separate Groq audio transcription call

---

### 12.6 `models/local.py` — OpenAI-Compatible (Ollama or OpenRouter)

**File:** `src/vigil/models/local.py`

`OpenAICompatibleClient` works with **any OpenAI-compatible API**:
- **Ollama** (local models): `base_url="http://localhost:11434/v1"`
- **OpenRouter** (cloud free tier): `base_url="https://openrouter.ai/api/v1"`

It uses the standard `/chat/completions` format so any compatible endpoint works.

---

### 12.7 `models/mock.py` — Offline Testing Mock

**File:** `src/vigil/models/mock.py`

`MockLLMClient` returns **deterministic fake responses** without making any API calls.

**Context-aware responses based on prompt keywords:**
- If prompt contains "plan" → returns a fake investigation plan JSON
- If prompt contains "report" or "summary" → returns a fake forensic summary
- If prompt contains "correlat" or "event" → returns fake event detections
- If prompt contains "assess" → returns a fake evidence quality rating
- For `analyze_image()` → always returns two observations: a person and a vehicle

This is used during testing, CI/CD, and when no API key is configured.

---

## 13. Storage Layer (`src/vigil/storage/`)

### 13.1 `storage/repository.py` — In-Memory Repository

**File:** `src/vigil/storage/repository.py`

`InvestigationRepository` is an **in-memory data store** that holds everything in Python dictionaries. It's fast but loses data when the process restarts.

**What it stores:**
- Investigations (`dict[str, Investigation]`)
- InvestigationStates (`dict[str, InvestigationState]`)
- MediaAssets, Cameras, Artifacts, Observations, Events
- EventLinks, EvidenceAssessments, CoverageRecords, Reports, AuditLogs

**Key operations:**
- `add_investigation(inv)`, `get_investigation(id)`, `list_investigations()`
- `add_observation(obs)`, `get_observation(id)`, `list_observations(ids)`
- `add_event(event)`, `get_event(id)`, `list_events(ids)`
- `add_report(report)`, `list_reports(investigation_id)`
- `add_audit_log(log)`, `list_audit_logs(investigation_id, target_id)`
- `save_state(state)`, `get_state(investigation_id)`

`EntityNotFoundError` is raised when an ID doesn't exist.

---

### 13.2 `storage/sqlite_repository.py` — Persistent SQLite Database

**File:** `src/vigil/storage/sqlite_repository.py`

`SqliteInvestigationRepository` extends `InvestigationRepository` to **persist all data to a SQLite file** (`vigil.db`).

**Why SQLite?**
- Zero configuration — no separate database server needed
- Data survives process restarts
- Single file — easy to backup and share

**How it works:**
- On startup, creates all necessary tables if they don't exist
- Every `add_*()` call inserts/updates a row in SQLite
- Every `get_*()` call queries SQLite and deserializes the JSON back to domain objects
- Domain objects are stored as JSON text in the database

**Tables created:**
- `investigations`, `investigation_states`
- `media_assets`, `cameras`, `artifacts`
- `observations`, `events`, `event_links`
- `evidence_assessments`, `coverage_records`
- `reports`, `audit_logs`

---

## 14. Domain Layer (`src/vigil/domain/`)

This layer defines the **data structures** used throughout VIGIL. Think of these as the vocabulary — the precise definitions of what an "Investigation", "Event", "Observation" etc. look like.

All domain models extend **`DomainModel`** (in `base.py`) which:
- Forbids extra fields (`extra="forbid"`)
- Strips whitespace from strings automatically
- Validates assignments after creation
- Makes objects immutable (`frozen=True`)

**Core shared types** (in `common.py`):
- `Identifier` — a non-blank string ID
- `Timestamp` — a timezone-aware datetime (must include timezone info)
- `ConfidenceScore` — a float between 0.0 and 1.0
- `ReferenceIds` — a list of unique, non-blank string IDs

### Quick Domain Model Reference

| Model | File | What it represents |
|---|---|---|
| `Investigation` | `investigation.py` | A case: has a title, objective, scope, and links to media |
| `MediaAsset` | `media_asset.py` | The original video/audio file (with resolution, FPS, duration) |
| `Camera` | `camera.py` | The camera that recorded the media (name, location, timezone) |
| `Artifact` | `artifact.py` | A derived file: a JPEG frame, WAV audio segment, or MP4 clip |
| `SourceReference` | `source_reference.py` | A timestamp pointer: which media file and what time interval |
| `Observation` | `observation.py` | A single AI-detected finding (e.g., "person walking at 5.2s") |
| `Provenance` | `provenance.py` | Records *how* and *by whom* an observation was produced |
| `Entity` | `entity.py` | A detected object (person, vehicle, animal) with attributes |
| `Event` | `event.py` | A meaningful incident composed of multiple observations |
| `EventLink` | `event_link.py` | A typed relationship between two events (before/after/overlaps) |
| `EvidenceAssessment` | `evidence_assessment.py` | Quality rating of evidence for an observation or event |
| `CoverageRecord` | `coverage.py` | Documents whether a time interval was examined |
| `Report` | `report.py` | The final forensic document with all findings |
| `AuditLog` | `audit.py` | Immutable log of every human review action |

**Important validation rules:**
- `Event.end_time` cannot be before `Event.start_time`
- `CoverageRecord.interval_end` cannot precede `interval_start`
- `Artifact` with `artifact_type="frame"` must have `media_type="image"`
- `Artifact` with `artifact_type="clip"` must have `media_type="video"`
- `EvidenceAssessment.rating` must be `"insufficient"`, `"low"`, `"moderate"`, or `"high"`
- `AuditLog.actor` cannot be blank
- SHA-256 hashes must be exactly 64 hexadecimal characters

---

## 15. The Frontend UI (`src/vigil/ui/`)

The `ui/` folder contains a **browser-based investigator dashboard** built with plain HTML, CSS, and JavaScript (no framework needed).

| File | Purpose |
|---|---|
| `index.html` | The single-page application shell |
| `app.js` | All dashboard logic — fetching data, rendering events, WebSocket handling, video playback |
| `style.css` | Dark-themed, responsive styling for the dashboard |

**Dashboard features:**
- Lists all investigations with their status
- Shows real-time progress via WebSocket (task progress bar, live event feed)
- Displays observations, events, evidence assessments, and coverage records
- Allows human reviewers to confirm/reject events directly in the browser
- Plays incident video clips inline
- Downloads reports as HTML or PDF

The UI communicates exclusively with the REST API and WebSocket endpoints described in Section 6.

---

## 16. End-to-End Flow Summary

Here's the complete picture of what happens when you upload a video to VIGIL:

```
1. USER uploads video via browser dashboard or API
   ↓
2. API routes/investigations.py: create_investigation() called
   ↓
3. InvestigationService.create_and_ingest_investigation()
   ├── MediaIngestionService.ingest_file()
   │   ├── MediaMetadataExtractor.extract() → probes video properties
   │   ├── MediaDecoder.extract_frames() → saves JPEG frames to disk
   │   ├── MediaDecoder.demux_audio_to_wav() → saves WAV audio to disk
   │   └── Saves MediaAsset + Artifacts to Repository
   ├── Creates Investigation domain object → saves to Repository
   └── Saves initial InvestigationState (status=CREATED)
   ↓
4. InvestigationService.run_investigation() → submits to ThreadPoolExecutor
   ↓
5. AgenticOrchestrator.run_investigation() runs in background thread
   ↓
6. InvestigationPlanner.plan_investigation() → creates 7 PlannedTasks
   ↓
7. For each PlannedTask (sequential):
   ├── Phase 1: frame_sampling
   │   └── FrameExtractorWorker → finds frame artifacts → returns artifact IDs
   ├── Phase 2: visual_analysis
   │   └── VisualDetectorWorker → sends frames to LLM → gets observations
   │       └── LLM (Gemini/NVIDIA/Groq/Mock) → analyzes image → returns JSON
   ├── Phase 3: audio_transcription
   │   └── AudioTranscriberWorker → sends audio to LLM → gets observations
   ├── Phase 4: event_correlation
   │   └── EventCorrelatorWorker → sends all observations to LLM → gets events + links
   ├── Phase 5: evidence_assessment
   │   └── EvidenceAssessorWorker → rates each event's evidence quality
   ├── Phase 6: coverage_evaluation
   │   └── CoverageTrackerWorker → records which footage intervals were examined
   └── Phase 7: report_generation
       └── ReportGeneratorWorker → sends all findings to LLM → creates Report
   ↓
8. All events are broadcast via TelemetryManager → WebSocket → Browser Dashboard updates live
   ↓
9. Investigation status → COMPLETED
   ↓
10. HUMAN INVESTIGATOR REVIEW:
    ├── Views observations and events in dashboard
    ├── Confirms/rejects events via POST /events/{id}/review
    │   └── Creates AuditLog entry, updates Event status
    ├── Requests video clip for confirmed events via POST /events/{id}/clip
    │   └── ClipSlicer cuts MP4 sub-clip, saves Artifact
    └── Finalizes report via POST /report/finalize
        └── Creates final Report with confirmed events + clips
   ↓
11. EXPORT:
    ├── GET /export/html → ReportExporter.export_html() → dark-themed HTML with video players
    └── GET /export/pdf  → ReportExporter.export_pdf()  → court-ready PDF with tables
```

> [!TIP]
> **For offline/testing use:** Set no API keys → `MockLLMClient` is used automatically. All AI calls return pre-scripted forensic responses so the entire pipeline runs without any internet connection.

> [!NOTE]
> **State is persisted in SQLite** at `storage_data/vigil.db` by default. This means you can restart the server and all previous investigations, events, and reports are still there.

> [!IMPORTANT]
> **The 7-phase investigation pipeline always runs sequentially in order.** If Phase 3 (audio transcription) fails, the pipeline stops — Phases 4-7 will not run, and the investigation status becomes FAILED.
