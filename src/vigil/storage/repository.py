"""In-memory repository managing VIGIL domain records and referential checks."""

import threading
from collections.abc import Sequence
from typing import TypeVar

from vigil.domain.artifact import Artifact
from vigil.domain.audit import AuditLog
from vigil.domain.camera import Camera
from vigil.domain.coverage import CoverageRecord
from vigil.domain.entity import Entity
from vigil.domain.event import Event
from vigil.domain.event_link import EventLink
from vigil.domain.evidence_assessment import EvidenceAssessment
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.report import Report
from vigil.domain.source_reference import SourceReference
from vigil.orchestration.investigation_state import InvestigationState
from vigil.orchestration.task_types import ModelOutput

T = TypeVar("T")


class RepositoryError(Exception):
    """Base exception for repository operations."""


class EntityNotFoundError(RepositoryError):
    """Raised when a requested entity does not exist."""


class ReferentialIntegrityError(RepositoryError):
    """Raised when an ID reference does not resolve to an existing record."""


class InvestigationRepository:
    """Thread-safe in-memory store for investigation domain objects and artifacts."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cameras: dict[str, Camera] = {}
        self._media_assets: dict[str, MediaAsset] = {}
        self._source_references: dict[str, SourceReference] = {}
        self._artifacts: dict[str, Artifact] = {}
        self._observations: dict[str, Observation] = {}
        self._entities: dict[str, Entity] = {}
        self._events: dict[str, Event] = {}
        self._event_links: dict[str, EventLink] = {}
        self._evidence_assessments: dict[str, EvidenceAssessment] = {}
        self._investigations: dict[str, Investigation] = {}
        self._coverage_records: dict[str, CoverageRecord] = {}
        self._reports: dict[str, Report] = {}
        self._model_outputs: dict[str, ModelOutput] = {}
        self._investigation_states: dict[str, InvestigationState] = {}
        self._audit_logs: dict[str, AuditLog] = {}

    # -------------------------------------------------------------------------
    # Camera
    # -------------------------------------------------------------------------
    def add_camera(self, camera: Camera) -> Camera:
        with self._lock:
            self._cameras[camera.camera_id] = camera
            return camera

    def get_camera(self, camera_id: str) -> Camera:
        with self._lock:
            cam = self._cameras.get(camera_id)
            if cam is None:
                raise EntityNotFoundError(f"Camera '{camera_id}' not found.")
            return cam

    def list_cameras(self) -> list[Camera]:
        with self._lock:
            return list(self._cameras.values())

    # -------------------------------------------------------------------------
    # MediaAsset
    # -------------------------------------------------------------------------
    def add_media_asset(self, media_asset: MediaAsset) -> MediaAsset:
        with self._lock:
            if media_asset.camera_id and media_asset.camera_id not in self._cameras:
                pass
            self._media_assets[media_asset.media_asset_id] = media_asset
            return media_asset

    def get_media_asset(self, media_asset_id: str) -> MediaAsset:
        with self._lock:
            asset = self._media_assets.get(media_asset_id)
            if asset is None:
                raise EntityNotFoundError(f"MediaAsset '{media_asset_id}' not found.")
            return asset

    def list_media_assets(self) -> list[MediaAsset]:
        with self._lock:
            return list(self._media_assets.values())

    # -------------------------------------------------------------------------
    # Artifact
    # -------------------------------------------------------------------------
    def add_artifact(self, artifact: Artifact) -> Artifact:
        with self._lock:
            self._artifacts[artifact.artifact_id] = artifact
            return artifact

    def get_artifact(self, artifact_id: str) -> Artifact:
        with self._lock:
            art = self._artifacts.get(artifact_id)
            if art is None:
                raise EntityNotFoundError(f"Artifact '{artifact_id}' not found.")
            return art

    def list_artifacts(self) -> list[Artifact]:
        with self._lock:
            return list(self._artifacts.values())

    # -------------------------------------------------------------------------
    # Observation
    # -------------------------------------------------------------------------
    def add_observation(self, observation: Observation) -> Observation:
        with self._lock:
            self._observations[observation.observation_id] = observation
            return observation

    def get_observation(self, observation_id: str) -> Observation:
        with self._lock:
            obs = self._observations.get(observation_id)
            if obs is None:
                raise EntityNotFoundError(f"Observation '{observation_id}' not found.")
            return obs

    def list_observations(
        self, observation_ids: Sequence[str] | None = None
    ) -> list[Observation]:
        with self._lock:
            if observation_ids is None:
                return list(self._observations.values())
            return [
                self._observations[oid]
                for oid in observation_ids
                if oid in self._observations
            ]

    # -------------------------------------------------------------------------
    # Entity
    # -------------------------------------------------------------------------
    def add_entity(self, entity: Entity) -> Entity:
        with self._lock:
            self._entities[entity.entity_id] = entity
            return entity

    def get_entity(self, entity_id: str) -> Entity:
        with self._lock:
            ent = self._entities.get(entity_id)
            if ent is None:
                raise EntityNotFoundError(f"Entity '{entity_id}' not found.")
            return ent

    def list_entities(self) -> list[Entity]:
        with self._lock:
            return list(self._entities.values())

    # -------------------------------------------------------------------------
    # Event & EventLink
    # -------------------------------------------------------------------------
    def add_event(self, event: Event) -> Event:
        with self._lock:
            self._events[event.event_id] = event
            return event

    def get_event(self, event_id: str) -> Event:
        with self._lock:
            evt = self._events.get(event_id)
            if evt is None:
                raise EntityNotFoundError(f"Event '{event_id}' not found.")
            return evt

    def list_events(self, event_ids: Sequence[str] | None = None) -> list[Event]:
        with self._lock:
            if event_ids is None:
                return list(self._events.values())
            return [self._events[eid] for eid in event_ids if eid in self._events]

    def add_event_link(self, link: EventLink) -> EventLink:
        with self._lock:
            self._event_links[link.event_link_id] = link
            return link

    def list_event_links(self) -> list[EventLink]:
        with self._lock:
            return list(self._event_links.values())

    # -------------------------------------------------------------------------
    # EvidenceAssessment
    # -------------------------------------------------------------------------
    def add_evidence_assessment(
        self, assessment: EvidenceAssessment
    ) -> EvidenceAssessment:
        with self._lock:
            self._evidence_assessments[assessment.assessment_id] = assessment
            return assessment

    def list_evidence_assessments(
        self, target_id: str | None = None
    ) -> list[EvidenceAssessment]:
        with self._lock:
            if target_id is None:
                return list(self._evidence_assessments.values())
            return [
                a
                for a in self._evidence_assessments.values()
                if a.target_id == target_id
            ]

    # -------------------------------------------------------------------------
    # CoverageRecord
    # -------------------------------------------------------------------------
    def add_coverage_record(self, record: CoverageRecord) -> CoverageRecord:
        with self._lock:
            self._coverage_records[record.coverage_id] = record
            return record

    def list_coverage_records(
        self, investigation_id: str | None = None
    ) -> list[CoverageRecord]:
        with self._lock:
            if investigation_id is None:
                return list(self._coverage_records.values())
            return [
                c
                for c in self._coverage_records.values()
                if c.investigation_id == investigation_id
            ]

    # -------------------------------------------------------------------------
    # Investigation & State
    # -------------------------------------------------------------------------
    def add_investigation(self, investigation: Investigation) -> Investigation:
        with self._lock:
            self._investigations[investigation.investigation_id] = investigation
            return investigation

    def get_investigation(self, investigation_id: str) -> Investigation:
        with self._lock:
            inv = self._investigations.get(investigation_id)
            if inv is None:
                raise EntityNotFoundError(
                    f"Investigation '{investigation_id}' not found."
                )
            return inv

    def list_investigations(self) -> list[Investigation]:
        with self._lock:
            return list(self._investigations.values())

    def save_state(self, state: InvestigationState) -> InvestigationState:
        with self._lock:
            self._investigation_states[state.investigation_id] = state
            return state

    def get_state(self, investigation_id: str) -> InvestigationState | None:
        with self._lock:
            return self._investigation_states.get(investigation_id)

    # -------------------------------------------------------------------------
    # Report
    # -------------------------------------------------------------------------
    def add_report(self, report: Report) -> Report:
        with self._lock:
            self._reports[report.report_id] = report
            return report

    def get_report(self, report_id: str) -> Report:
        with self._lock:
            rep = self._reports.get(report_id)
            if rep is None:
                raise EntityNotFoundError(f"Report '{report_id}' not found.")
            return rep

    def list_reports(self, investigation_id: str | None = None) -> list[Report]:
        with self._lock:
            if investigation_id is None:
                return list(self._reports.values())
            return [
                r
                for r in self._reports.values()
                if r.investigation_id == investigation_id
            ]

    # -------------------------------------------------------------------------
    # AuditLog
    # -------------------------------------------------------------------------
    def add_audit_log(self, audit_log: AuditLog) -> AuditLog:
        with self._lock:
            self._audit_logs[audit_log.audit_id] = audit_log
            return audit_log

    def get_audit_log(self, audit_id: str) -> AuditLog:
        with self._lock:
            log = self._audit_logs.get(audit_id)
            if log is None:
                raise EntityNotFoundError(f"AuditLog '{audit_id}' not found.")
            return log

    def list_audit_logs(
        self,
        investigation_id: str | None = None,
        target_id: str | None = None,
    ) -> list[AuditLog]:
        with self._lock:
            logs = list(self._audit_logs.values())
            if investigation_id is not None:
                logs = [l for l in logs if l.investigation_id == investigation_id]
            if target_id is not None:
                logs = [l for l in logs if l.target_id == target_id]
            return sorted(logs, key=lambda l: l.timestamp)

    # -------------------------------------------------------------------------
    # ModelOutput
    # -------------------------------------------------------------------------
    def add_model_output(self, output: ModelOutput) -> ModelOutput:
        with self._lock:
            self._model_outputs[output.output_id] = output
            return output

    # -------------------------------------------------------------------------
    # Referential integrity checks
    # -------------------------------------------------------------------------
    def validate_references_exist(
        self,
        ref_ids: Sequence[str],
        expected_type: str,
    ) -> None:
        """Validate that all referenced IDs exist in the respective store."""
        with self._lock:
            stores = {
                "media_asset": self._media_assets,
                "artifact": self._artifacts,
                "observation": self._observations,
                "entity": self._entities,
                "event": self._events,
                "coverage": self._coverage_records,
                "assessment": self._evidence_assessments,
                "audit": self._audit_logs,
            }
            target_store = stores.get(expected_type)
            if target_store is None:
                raise ValueError(f"Unknown entity type for validation: {expected_type}")

            missing = [ref for ref in ref_ids if ref not in target_store]
            if missing:
                raise ReferentialIntegrityError(
                    f"Referenced {expected_type} IDs do not exist: {missing}"
                )
