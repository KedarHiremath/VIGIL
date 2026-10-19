# VIGIL — Agentic Orchestration, Specialized Agents & Forensic Tools Specification

**Status:** Completed Baseline Implementation (Layer 2)  
**Scope:** `AgenticOrchestrator`, `InvestigationPlanner`, Specialized Agents (`VisualAgent`, `AudioAgent`, `TemporalCorrelationAgent`, `EvidenceVerificationAgent`, `ReportWriterAgent`), Forensic Tool Workers, Free Model Adapters, and Referential Repository.

---

## 1. System Overview & Alignment with Workflow Diagram

The VIGIL agentic orchestration layer realizes the core intelligence and workflow described in `VIGIL_vison_modelContext.txt`. It connects the strict Pydantic domain schemas (Layer 1) with autonomous reasoning, specialized analysis agents, multi-modal tools, and free-tier LLMs.

### Architectural Mapping

```
                                      [ Investigator / User ]
                                                 │
                                                 ▼
                                     [ API / Application Layer ]
                                                 │
                                                 ▼
                                     [ Investigation Planner ]
                                                 │
                                                 ▼
                                    [ Agentic Orchestrator ]
                     (State Machine, Lifecycle Transitions, Checkpoints)
                                                 │
            ┌──────────────────┬─────────────────┼──────────────────┬──────────────────┐
            ▼                  ▼                 ▼                  ▼                  ▼
     [ Visual Agent ]   [ Audio Agent ]   [ Temporal Agent ] [ Verif. Agent ]  [ Report Agent ]
            │                  │                 │                  │                  │
            ▼                  ▼                 ▼                  ▼                  ▼
      Vision Tools        Audio Tools      Temporal Tools     Evidence Tools     Reporting Tools
     (FrameExtractor)  (AudioTranscriber) (EventCorrelator)  (EvidenceAssessor) (ReportGenerator)
     (VisualDetector)                                        (CoverageTracker)
            │                  │                 │                  │                  │
            └──────────────────┴────────┬────────┴──────────────────┴──────────────────┘
                                        ▼
                             [ Free Model Adapters ]
                     (Gemini 2.0 Flash, Groq Llama 3.3, Ollama)
                                        │
                                        ▼
                         [ Investigation Repository ]
                   (Artifacts, Observations, Events, Reports)
```

---

## 2. Specialized Agents Specification

### 2.1 `AgenticOrchestrator` (`LeadInvestigatorAgent`)
- **Module:** `src/vigil/agent/investigator.py`
- **Role:** Owns the multi-phase execution loop, state tracking, and error recovery.
- **Key Responsibilities:**
  1. Registers the initial `Investigation` into `InvestigationRepository`.
  2. Initializes `InvestigationState` in `CREATED` status.
  3. Obtains the decomposed forensic task sequence from `InvestigationPlanner`.
  4. Coordinates specialized agents and routes tasks through `OrchestrationService`.
  5. Accumulates generated `Observation` and `Event` IDs into the immutable `InvestigationState`.
  6. Completes the investigation upon successful task completion, transitioning to `COMPLETED`.

### 2.2 `InvestigationPlanner`
- **Module:** `src/vigil/agent/planner.py`
- **Role:** Decomposes investigation title, objective, scope, and media assets into actionable `PlannedTask` instances.
- **Workflow Phases Planned:**
  1. `frame_sampling`: Sample keyframes across media timeline.
  2. `visual_analysis`: Detect persons, vehicles, objects, and anomalies.
  3. `audio_transcription`: Extract acoustic cues and spoken dialogue.
  4. `event_correlation`: Group observations into chronological incidents and event links.
  5. `evidence_assessment`: Evaluate evidence quality, support level, and uncertainty.
  6. `coverage_evaluation`: Verify footage examination intervals.
  7. `report_generation`: Compile findings into a structured `Report`.

### 2.3 `VisualAgent`
- **Module:** `src/vigil/agent/specialized/visual_agent.py`
- **Role:** Coordinates frame extraction and visual multi-modal analysis.
- **Tools Invoked:** `FrameExtractorWorker` (`frame_sampling`), `VisualDetectorWorker` (`visual_analysis`).

### 2.4 `AudioAgent`
- **Module:** `src/vigil/agent/specialized/audio_agent.py`
- **Role:** Coordinates acoustic transcription, speech analysis, and sound event detection.
- **Tools Invoked:** `AudioTranscriberWorker` (`audio_transcription`).

### 2.5 `TemporalCorrelationAgent`
- **Module:** `src/vigil/agent/specialized/correlation_agent.py`
- **Role:** Discovers chronological sequences, overlapping activities, and multi-camera associations.
- **Tools Invoked:** `EventCorrelatorWorker` (`event_correlation`).
- **Domain Outputs:** Produces `Event` and `EventLink` (`before`, `after`, `overlaps`, `related_to`, `possible_same_incident`).

### 2.6 `EvidenceVerificationAgent`
- **Module:** `src/vigil/agent/specialized/verification_agent.py`
- **Role:** Assesses evidence quality, support level, uncertainty, and footage coverage completeness.
- **Tools Invoked:** `EvidenceAssessorWorker` (`evidence_assessment`), `CoverageTrackerWorker` (`coverage_evaluation`).
- **Domain Outputs:** Produces `EvidenceAssessment` and `CoverageRecord`.

### 2.7 `ReportWriterAgent`
- **Module:** `src/vigil/agent/specialized/report_writer_agent.py`
- **Role:** Synthesizes verified findings, timelines, and assessments into a formal forensic document.
- **Tools Invoked:** `ReportGeneratorWorker` (`report_generation`).
- **Domain Outputs:** Produces `Report`.

---

## 3. Forensic Tools (`src/vigil/tools/`)

All workers conform strictly to the `TaskWorker` protocol (`execute(request: TaskRequest) -> TaskResult`):

| Worker Class | Task Type | Input References | Generated Outputs | Key Validations |
| :--- | :--- | :--- | :--- | :--- |
| `FrameExtractorWorker` | `frame_sampling`<br>`clip_extraction` | `MediaAsset` IDs | `Artifact` IDs | Frame interval bounds, 64-hex SHA-256 checksums, positive durations. |
| `VisualDetectorWorker` | `visual_analysis` | `Artifact` IDs | `Observation` IDs, `Entity` IDs | Media modality = `image`, `Provenance` record with model name, non-blank descriptions. |
| `AudioTranscriberWorker` | `audio_transcription` | `MediaAsset` / `Artifact` IDs | `Observation` IDs | Media modality = `audio`, audio provenance. |
| `EventCorrelatorWorker` | `event_correlation` | `Observation` IDs | `Event` IDs, `EventLink` IDs | Supporting observations ≥ 1, no self-referential links, timezone-aware event times. |
| `EvidenceAssessorWorker` | `evidence_assessment` | `Observation` / `Event` IDs | `EvidenceAssessment` IDs | Ratings (`insufficient`, `low`, `moderate`, `high`), distinct from model confidence. |
| `CoverageTrackerWorker` | `coverage_evaluation` | `SourceReference` / `MediaAsset` IDs | `CoverageRecord` IDs | Paired start/end timestamps, `examined` status requires `examined_at`. |
| `ReportGeneratorWorker` | `report_generation` | None (reads repo) | `Report` IDs | Non-blank title, summary, and links to all supporting records. |

---

## 4. Free-Tier Model Adapters (`src/vigil/models/`)

The architecture provides multi-provider LLM support through standard library HTTP (`urllib.request`), requiring zero heavy third-party dependencies:

1. **Google Gemini Free Tier (`GeminiClient`)**:
   - Endpoint: `https://generativelanguage.googleapis.com/v1beta`
   - Models: `gemini-2.0-flash`, `gemini-1.5-flash`
   - Free Quota: 15 RPM, 1M TPM, 1,500 RPD.
2. **Groq Cloud Free Tier (`GroqClient`)**:
   - Endpoint: `https://api.groq.com/openai/v1`
   - Models: `llama-3.3-70b-versatile`, `llama-3.2-11b-vision-preview`, `whisper-large-v3`
3. **Local & Offline (`OpenAICompatibleClient`)**:
   - Endpoint: `http://localhost:11434/v1` (Ollama) or OpenRouter free models (`:free`)
4. **Mock Provider (`MockLLMClient`)**:
   - Deterministic, high-fidelity mock client for automated testing and CI/CD without API keys.

---

## 5. Storage & Referential Integrity (`src/vigil/storage/`)

- Implements `InvestigationRepository` with `threading.RLock`.
- Provides lookup, persistence, and cross-record existence checks (`validate_references_exist`) ensuring referential integrity without polluting Pydantic model schemas.

---

## 6. Next Plan of Action (Phase 3 Roadmap)

According to the workflow diagram in `VIGIL_vison_modelContext.txt`, the next logical implementation phases are:

### Phase 3: Media Ingestion, Indexing & Storage Engine
1. **Actual Video/Audio Ingestion Worker**:
   - Integrate lightweight media decoding (e.g. OpenCV / PyAV / ffmpeg wrapper) to extract actual image frames from `.mp4`/`.avi` files.
   - Demux audio tracks into `.wav` segments for Whisper transcription.
2. **Metadata Extractor**:
   - Extract real video FPS, resolution, codec, duration, and container timestamps.
3. **Playable Incident Clip Generator**:
   - Slice short video clips (`Artifact(artifact_type="clip")`) around detected event intervals for human investigator playback.
4. **Persistent Database Layer**:
   - Provide a SQLite/PostgreSQL implementation of `InvestigationRepository` so long-running investigations survive process restarts.

### Phase 4: Application Services & API Layer
1. **FastAPI Endpoints**:
   - `POST /investigations`: Submit video footage and investigation objectives.
   - `GET /investigations/{id}/state`: Stream or poll real-time task progress.
   - `GET /investigations/{id}/report`: Fetch the compiled forensic report.
2. **WebSocket Telemetry**:
   - Push live agent reasoning steps, detected observations, and coverage updates.

### Phase 5: Human Review & Audit Layer
1. **Investigator Confirmation Workflow**:
   - Endpoint for human review: approve, reject, or edit proposed `Event` records (`Event.status = "confirmed"` or `"rejected"`).
2. **Report Versioning & Export**:
   - Export reports to standardized formats (PDF, Markdown, HTML) with embedded clip links and audit signatures.
