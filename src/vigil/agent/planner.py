"""Investigation planning and adaptive task generation."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from vigil.domain.investigation import Investigation
from vigil.models.base import BaseLLMClient
from vigil.orchestration.task_types import TaskRequest


@dataclass(frozen=True)
class PlannedTask:
    """A task planned by the agentic reasoner."""

    task_type: str
    description: str
    input_refs: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_task_request(
        self, requested_by: str = "investigation-planner"
    ) -> TaskRequest:
        """Convert planned task into a domain TaskRequest."""
        return TaskRequest(
            task_id=f"task-{self.task_type.replace('_', '-')}-{uuid.uuid4().hex[:6]}",
            task_type=self.task_type,
            input_refs=self.input_refs,
            parameters=self.parameters,
            requested_by=requested_by,
        )


class InvestigationPlanner:
    """Decomposes an investigation objective and scope into structured forensic tasks."""

    def __init__(self, llm_client: BaseLLMClient | None = None) -> None:
        self.llm = llm_client

    def plan_investigation(self, investigation: Investigation) -> list[PlannedTask]:
        """Construct the initial multi-phase forensic investigation plan."""
        inv_id = investigation.investigation_id
        media_refs = list(investigation.media_asset_ids)
        media_count = len(media_refs)

        tasks: list[PlannedTask] = []

        # Phase 1: Frame Extraction / Interval Sampling
        feed_note = f" across {media_count} surveillance camera feeds" if media_count > 1 else " across timeline"
        tasks.append(
            PlannedTask(
                task_type="frame_sampling",
                description=f"Extract forensic sample frames from media assets{feed_note}",
                input_refs=media_refs,
                parameters={
                    "investigation_id": inv_id,
                    "sample_interval_seconds": 2.0,
                    "max_frames": 8,
                },
            )
        )

        # Phase 2: Visual Multi-modal Analysis
        tasks.append(
            PlannedTask(
                task_type="visual_analysis",
                description=f"Analyze extracted frame artifacts across premise feeds for persons, vehicles, objects, and anomalies",
                input_refs=[],  # Dynamically resolved by worker or updated by agent
                parameters={
                    "investigation_id": inv_id,
                    "detect_entities": True,
                    "max_frames_per_task": max(8, media_count * 4),
                },
            )
        )

        # Phase 3: Audio Transcription & Acoustic Analysis (if applicable)
        tasks.append(
            PlannedTask(
                task_type="audio_transcription",
                description=f"Transcribe audio tracks and detect acoustic trigger events across feeds",
                input_refs=media_refs,
                parameters={
                    "investigation_id": inv_id,
                },
            )
        )

        # Phase 4: Temporal Correlation & Event Link Discovery
        tasks.append(
            PlannedTask(
                task_type="event_correlation",
                description="Correlate observations across premise camera feeds into Events and EventLinks",
                input_refs=[],
                parameters={
                    "investigation_id": inv_id,
                },
            )
        )

        # Phase 5: Evidence Assessment
        tasks.append(
            PlannedTask(
                task_type="evidence_assessment",
                description="Assess evidence quality, support level, and uncertainty for identified events",
                input_refs=[],
                parameters={
                    "investigation_id": inv_id,
                    "assessed_by": "vigil-forensic-assessor",
                },
            )
        )

        # Phase 6: Coverage Evaluation
        tasks.append(
            PlannedTask(
                task_type="coverage_evaluation",
                description=f"Evaluate and record source examination coverage across all {media_count} premise feeds",
                input_refs=media_refs,
                parameters={
                    "investigation_id": inv_id,
                },
            )
        )

        # Phase 7: Forensic Report Generation
        tasks.append(
            PlannedTask(
                task_type="report_generation",
                description="Synthesize all findings, observations, events, and assessments into a final Report",
                input_refs=[],
                parameters={
                    "investigation_id": inv_id,
                    "title": f"Forensic Investigation Report: {investigation.title}",
                    "generated_by": "vigil-lead-investigator",
                },
            )
        )

        return tasks
