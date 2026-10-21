"""SQLite-backed persistent repository for VIGIL domain models and execution state."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

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
from vigil.orchestration.investigation_state import InvestigationState
from vigil.orchestration.task_types import ModelOutput
from vigil.storage.repository import (
    EntityNotFoundError,
    InvestigationRepository,
    ReferentialIntegrityError,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cameras (
    camera_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location_label TEXT,
    timezone TEXT,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_assets (
    media_asset_id TEXT PRIMARY KEY,
    media_type TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    camera_id TEXT,
    duration_seconds REAL,
    sha256 TEXT,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    media_type TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    media_asset_id TEXT,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    modality TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    label TEXT,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_links (
    event_link_id TEXT PRIMARY KEY,
    source_event_id TEXT NOT NULL,
    target_event_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_assessments (
    assessment_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coverage_records (
    coverage_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    source_reference_id TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investigations (
    investigation_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investigation_states (
    investigation_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    title TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_outputs (
    output_id TEXT PRIMARY KEY,
    output_type TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_camera ON media_assets(camera_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_media ON artifacts(media_asset_id);
CREATE INDEX IF NOT EXISTS idx_evidence_target ON evidence_assessments(target_id);
CREATE INDEX IF NOT EXISTS idx_coverage_inv ON coverage_records(investigation_id);
CREATE INDEX IF NOT EXISTS idx_reports_inv ON reports(investigation_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_inv ON audit_logs(investigation_id);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_logs(target_id);
"""


class SqliteInvestigationRepository(InvestigationRepository):
    """Thread-safe SQLite persistent store for VIGIL domain models and execution state."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        super().__init__()
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            p = Path(self.db_path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=10.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock, self._conn:
            if self.db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            self._conn.execute("PRAGMA busy_timeout = 10000;")
            self._conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        """Close SQLite database connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # -------------------------------------------------------------------------
    # Camera
    # -------------------------------------------------------------------------
    def add_camera(self, camera: Camera) -> Camera:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO cameras (camera_id, name, location_label, timezone, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(camera_id) DO UPDATE SET
                    name = excluded.name,
                    location_label = excluded.location_label,
                    timezone = excluded.timezone,
                    payload = excluded.payload
                """,
                (
                    camera.camera_id,
                    camera.name,
                    camera.location_label,
                    camera.timezone,
                    camera.model_dump_json(),
                ),
            )
            return camera

    def get_camera(self, camera_id: str) -> Camera:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM cameras WHERE camera_id = ?", (camera_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(f"Camera '{camera_id}' not found.")
            return Camera.model_validate_json(row["payload"])

    def list_cameras(self) -> list[Camera]:
        with self._lock:
            cursor = self._conn.execute("SELECT payload FROM cameras")
            return [Camera.model_validate_json(row["payload"]) for row in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # MediaAsset
    # -------------------------------------------------------------------------
    def add_media_asset(self, media_asset: MediaAsset) -> MediaAsset:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO media_assets (media_asset_id, media_type, storage_uri, camera_id, duration_seconds, sha256, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(media_asset_id) DO UPDATE SET
                    media_type = excluded.media_type,
                    storage_uri = excluded.storage_uri,
                    camera_id = excluded.camera_id,
                    duration_seconds = excluded.duration_seconds,
                    sha256 = excluded.sha256,
                    payload = excluded.payload
                """,
                (
                    media_asset.media_asset_id,
                    media_asset.media_type,
                    media_asset.storage_uri,
                    media_asset.camera_id,
                    media_asset.duration_seconds,
                    media_asset.sha256,
                    media_asset.model_dump_json(),
                ),
            )
            return media_asset

    def get_media_asset(self, media_asset_id: str) -> MediaAsset:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM media_assets WHERE media_asset_id = ?",
                (media_asset_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(f"MediaAsset '{media_asset_id}' not found.")
            return MediaAsset.model_validate_json(row["payload"])

    def list_media_assets(self) -> list[MediaAsset]:
        with self._lock:
            cursor = self._conn.execute("SELECT payload FROM media_assets")
            return [
                MediaAsset.model_validate_json(row["payload"]) for row in cursor.fetchall()
            ]

    # -------------------------------------------------------------------------
    # Artifact
    # -------------------------------------------------------------------------
    def add_artifact(self, artifact: Artifact) -> Artifact:
        media_id = artifact.source_reference.media_asset_id
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO artifacts (artifact_id, artifact_type, media_type, storage_uri, media_asset_id, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    artifact_type = excluded.artifact_type,
                    media_type = excluded.media_type,
                    storage_uri = excluded.storage_uri,
                    media_asset_id = excluded.media_asset_id,
                    payload = excluded.payload
                """,
                (
                    artifact.artifact_id,
                    artifact.artifact_type,
                    artifact.media_type,
                    artifact.storage_uri,
                    media_id,
                    artifact.model_dump_json(),
                ),
            )
            return artifact

    def get_artifact(self, artifact_id: str) -> Artifact:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(f"Artifact '{artifact_id}' not found.")
            return Artifact.model_validate_json(row["payload"])

    def list_artifacts(self) -> list[Artifact]:
        with self._lock:
            cursor = self._conn.execute("SELECT payload FROM artifacts")
            return [
                Artifact.model_validate_json(row["payload"]) for row in cursor.fetchall()
            ]

    # -------------------------------------------------------------------------
    # Observation
    # -------------------------------------------------------------------------
    def add_observation(self, observation: Observation) -> Observation:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO observations (observation_id, modality, observation_type, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(observation_id) DO UPDATE SET
                    modality = excluded.modality,
                    observation_type = excluded.observation_type,
                    payload = excluded.payload
                """,
                (
                    observation.observation_id,
                    observation.modality,
                    observation.observation_type,
                    observation.model_dump_json(),
                ),
            )
            return observation

    def get_observation(self, observation_id: str) -> Observation:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM observations WHERE observation_id = ?",
                (observation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(f"Observation '{observation_id}' not found.")
            return Observation.model_validate_json(row["payload"])

    def list_observations(
        self, observation_ids: Sequence[str] | None = None
    ) -> list[Observation]:
        with self._lock:
            if observation_ids is None:
                cursor = self._conn.execute("SELECT payload FROM observations")
                return [
                    Observation.model_validate_json(row["payload"])
                    for row in cursor.fetchall()
                ]

            if not observation_ids:
                return []

            placeholders = ",".join("?" for _ in observation_ids)
            cursor = self._conn.execute(
                f"SELECT payload FROM observations WHERE observation_id IN ({placeholders})",
                tuple(observation_ids),
            )
            return [
                Observation.model_validate_json(row["payload"])
                for row in cursor.fetchall()
            ]

    # -------------------------------------------------------------------------
    # Entity
    # -------------------------------------------------------------------------
    def add_entity(self, entity: Entity) -> Entity:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO entities (entity_id, entity_type, label, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    entity_type = excluded.entity_type,
                    label = excluded.label,
                    payload = excluded.payload
                """,
                (
                    entity.entity_id,
                    entity.entity_type,
                    entity.label,
                    entity.model_dump_json(),
                ),
            )
            return entity

    def get_entity(self, entity_id: str) -> Entity:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM entities WHERE entity_id = ?", (entity_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(f"Entity '{entity_id}' not found.")
            return Entity.model_validate_json(row["payload"])

    def list_entities(self) -> list[Entity]:
        with self._lock:
            cursor = self._conn.execute("SELECT payload FROM entities")
            return [Entity.model_validate_json(row["payload"]) for row in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Event & EventLink
    # -------------------------------------------------------------------------
    def add_event(self, event: Event) -> Event:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO events (event_id, event_type, status, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    event_type = excluded.event_type,
                    status = excluded.status,
                    payload = excluded.payload
                """,
                (
                    event.event_id,
                    event.event_type,
                    event.status,
                    event.model_dump_json(),
                ),
            )
            return event

    def get_event(self, event_id: str) -> Event:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM events WHERE event_id = ?", (event_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(f"Event '{event_id}' not found.")
            return Event.model_validate_json(row["payload"])

    def list_events(self, event_ids: Sequence[str] | None = None) -> list[Event]:
        with self._lock:
            if event_ids is None:
                cursor = self._conn.execute("SELECT payload FROM events")
                return [Event.model_validate_json(row["payload"]) for row in cursor.fetchall()]

            if not event_ids:
                return []

            placeholders = ",".join("?" for _ in event_ids)
            cursor = self._conn.execute(
                f"SELECT payload FROM events WHERE event_id IN ({placeholders})",
                tuple(event_ids),
            )
            return [Event.model_validate_json(row["payload"]) for row in cursor.fetchall()]

    def add_event_link(self, link: EventLink) -> EventLink:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO event_links (event_link_id, source_event_id, target_event_id, relationship_type, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(event_link_id) DO UPDATE SET
                    source_event_id = excluded.source_event_id,
                    target_event_id = excluded.target_event_id,
                    relationship_type = excluded.relationship_type,
                    payload = excluded.payload
                """,
                (
                    link.event_link_id,
                    link.from_event_id,
                    link.to_event_id,
                    link.relationship_type,
                    link.model_dump_json(),
                ),
            )
            return link

    def list_event_links(self) -> list[EventLink]:
        with self._lock:
            cursor = self._conn.execute("SELECT payload FROM event_links")
            return [
                EventLink.model_validate_json(row["payload"]) for row in cursor.fetchall()
            ]

    # -------------------------------------------------------------------------
    # EvidenceAssessment
    # -------------------------------------------------------------------------
    def add_evidence_assessment(
        self, assessment: EvidenceAssessment
    ) -> EvidenceAssessment:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO evidence_assessments (assessment_id, target_id, target_type, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(assessment_id) DO UPDATE SET
                    target_id = excluded.target_id,
                    target_type = excluded.target_type,
                    payload = excluded.payload
                """,
                (
                    assessment.assessment_id,
                    assessment.target_id,
                    assessment.target_type,
                    assessment.model_dump_json(),
                ),
            )
            return assessment

    def list_evidence_assessments(
        self, target_id: str | None = None
    ) -> list[EvidenceAssessment]:
        with self._lock:
            if target_id is None:
                cursor = self._conn.execute("SELECT payload FROM evidence_assessments")
            else:
                cursor = self._conn.execute(
                    "SELECT payload FROM evidence_assessments WHERE target_id = ?",
                    (target_id,),
                )
            return [
                EvidenceAssessment.model_validate_json(row["payload"])
                for row in cursor.fetchall()
            ]

    # -------------------------------------------------------------------------
    # CoverageRecord
    # -------------------------------------------------------------------------
    def add_coverage_record(self, record: CoverageRecord) -> CoverageRecord:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO coverage_records (coverage_id, investigation_id, source_reference_id, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(coverage_id) DO UPDATE SET
                    investigation_id = excluded.investigation_id,
                    source_reference_id = excluded.source_reference_id,
                    payload = excluded.payload
                """,
                (
                    record.coverage_id,
                    record.investigation_id,
                    record.source_reference_id,
                    record.model_dump_json(),
                ),
            )
            return record

    def list_coverage_records(
        self, investigation_id: str | None = None
    ) -> list[CoverageRecord]:
        with self._lock:
            if investigation_id is None:
                cursor = self._conn.execute("SELECT payload FROM coverage_records")
            else:
                cursor = self._conn.execute(
                    "SELECT payload FROM coverage_records WHERE investigation_id = ?",
                    (investigation_id,),
                )
            return [
                CoverageRecord.model_validate_json(row["payload"])
                for row in cursor.fetchall()
            ]

    # -------------------------------------------------------------------------
    # Investigation & State
    # -------------------------------------------------------------------------
    def add_investigation(self, investigation: Investigation) -> Investigation:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO investigations (investigation_id, title, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                    title = excluded.title,
                    payload = excluded.payload
                """,
                (
                    investigation.investigation_id,
                    investigation.title,
                    investigation.model_dump_json(),
                ),
            )
            return investigation

    def get_investigation(self, investigation_id: str) -> Investigation:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM investigations WHERE investigation_id = ?",
                (investigation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(
                    f"Investigation '{investigation_id}' not found."
                )
            return Investigation.model_validate_json(row["payload"])

    def list_investigations(self) -> list[Investigation]:
        with self._lock:
            cursor = self._conn.execute("SELECT payload FROM investigations")
            return [
                Investigation.model_validate_json(row["payload"])
                for row in cursor.fetchall()
            ]

    def save_state(self, state: InvestigationState) -> InvestigationState:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO investigation_states (investigation_id, status, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                    status = excluded.status,
                    payload = excluded.payload
                """,
                (
                    state.investigation_id,
                    state.status.value,
                    state.model_dump_json(),
                ),
            )
            return state

    def get_state(self, investigation_id: str) -> InvestigationState | None:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM investigation_states WHERE investigation_id = ?",
                (investigation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return InvestigationState.model_validate_json(row["payload"])

    # -------------------------------------------------------------------------
    # Report
    # -------------------------------------------------------------------------
    def add_report(self, report: Report) -> Report:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO reports (report_id, investigation_id, title, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    investigation_id = excluded.investigation_id,
                    title = excluded.title,
                    payload = excluded.payload
                """,
                (
                    report.report_id,
                    report.investigation_id,
                    report.title,
                    report.model_dump_json(),
                ),
            )
            return report

    def get_report(self, report_id: str) -> Report:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM reports WHERE report_id = ?", (report_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(f"Report '{report_id}' not found.")
            return Report.model_validate_json(row["payload"])

    def list_reports(self, investigation_id: str | None = None) -> list[Report]:
        with self._lock:
            if investigation_id is None:
                cursor = self._conn.execute("SELECT payload FROM reports")
            else:
                cursor = self._conn.execute(
                    "SELECT payload FROM reports WHERE investigation_id = ?",
                    (investigation_id,),
                )
            return [Report.model_validate_json(row["payload"]) for row in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # ModelOutput
    # -------------------------------------------------------------------------
    def add_model_output(self, output: ModelOutput) -> ModelOutput:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO model_outputs (output_id, output_type, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(output_id) DO UPDATE SET
                    output_type = excluded.output_type,
                    payload = excluded.payload
                """,
                (
                    output.output_id,
                    output.output_type,
                    output.model_dump_json(),
                ),
            )
            return output

    # -------------------------------------------------------------------------
    # AuditLog
    # -------------------------------------------------------------------------
    def add_audit_log(self, audit_log: AuditLog) -> AuditLog:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO audit_logs (audit_id, investigation_id, target_id, target_type, action, actor, timestamp, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    action = excluded.action,
                    actor = excluded.actor,
                    payload = excluded.payload
                """,
                (
                    audit_log.audit_id,
                    audit_log.investigation_id,
                    audit_log.target_id,
                    audit_log.target_type,
                    audit_log.action,
                    audit_log.actor,
                    audit_log.timestamp.isoformat(),
                    audit_log.model_dump_json(),
                ),
            )
            return audit_log

    def get_audit_log(self, audit_id: str) -> AuditLog:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM audit_logs WHERE audit_id = ?",
                (audit_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(f"AuditLog '{audit_id}' not found.")
            return AuditLog.model_validate_json(row["payload"])

    def list_audit_logs(
        self,
        investigation_id: str | None = None,
        target_id: str | None = None,
    ) -> list[AuditLog]:
        with self._lock:
            query = "SELECT payload FROM audit_logs"
            conditions: list[str] = []
            params: list[str] = []
            if investigation_id is not None:
                conditions.append("investigation_id = ?")
                params.append(investigation_id)
            if target_id is not None:
                conditions.append("target_id = ?")
                params.append(target_id)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY timestamp ASC"

            cursor = self._conn.execute(query, tuple(params))
            return [
                AuditLog.model_validate_json(row["payload"])
                for row in cursor.fetchall()
            ]

    # -------------------------------------------------------------------------
    # Referential integrity checks
    # -------------------------------------------------------------------------
    def validate_references_exist(
        self,
        ref_ids: Sequence[str],
        expected_type: str,
    ) -> None:
        """Validate that all referenced IDs exist in the respective store."""
        if not ref_ids:
            return

        table_map = {
            "media_asset": ("media_assets", "media_asset_id"),
            "artifact": ("artifacts", "artifact_id"),
            "observation": ("observations", "observation_id"),
            "entity": ("entities", "entity_id"),
            "event": ("events", "event_id"),
            "coverage": ("coverage_records", "coverage_id"),
            "assessment": ("evidence_assessments", "assessment_id"),
            "audit": ("audit_logs", "audit_id"),
        }

        entry = table_map.get(expected_type)
        if entry is None:
            raise ValueError(f"Unknown entity type for validation: {expected_type}")

        table_name, id_col = entry
        with self._lock:
            placeholders = ",".join("?" for _ in ref_ids)
            cursor = self._conn.execute(
                f"SELECT {id_col} FROM {table_name} WHERE {id_col} IN ({placeholders})",
                tuple(ref_ids),
            )
            found_ids = {row[0] for row in cursor.fetchall()}
            missing = [ref for ref in ref_ids if ref not in found_ids]
            if missing:
                raise ReferentialIntegrityError(
                    f"Referenced {expected_type} IDs do not exist: {missing}"
                )
