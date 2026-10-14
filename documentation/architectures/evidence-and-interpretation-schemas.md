# VIGIL Layer 1 — Evidence and Interpretation Schema Specification

**Status:** Initial implementation specification  
**Scope:** Provenance, Observation, Entity, Event, EventLink and EvidenceAssessment

## 1. Provenance

**Python file:** `src/vigil/domain/provenance.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `producer_type` | Literal | Yes | Category of the model, tool, rule, agent or human that produced the result. |
| `producer_name` | `str` | Yes | Name of the producing component or person. |
| `producer_version` | `str \| None` | No | Version of the producing component, if known. |
| `method` | `str` | Yes | Operation or analysis method used to produce the result. |
| `input_artifact_ids` | `list[str]` | No | IDs of derived artifacts consumed during analysis. Defaults to an empty list. |
| `parent_observation_ids` | `list[str]` | No | IDs of earlier observations used to derive or refine the result. Defaults to an empty list. |
| `created_at` | `datetime` | Yes | Timezone-aware timestamp when the result was produced; defaults to UTC now. |

**Validation rules**

- Producer name and method must not be blank.
- References must not be blank or duplicated.
- Creation timestamps must be timezone-aware.
- References must resolve to existing records when validated by the service layer.

## 2. Observation

**Python file:** `src/vigil/domain/observation.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `observation_id` | `str` | Yes | Stable unique identifier for the observation. |
| `modality` | Literal | Yes | Media modality: video, audio or image. |
| `observation_type` | `str` | Yes | Kind of finding, such as person detection, motion or audio transcription. |
| `description` | `str` | Yes | Human-readable description of the finding. |
| `source_references` | `list[SourceReference]` | Yes | One or more source-media intervals supporting the finding. |
| `artifact_ids` | `list[str]` | No | IDs of associated derived artifacts. Defaults to an empty list. |
| `confidence` | `float \| None` | No | Optional producer-reported score from 0 to 1; not necessarily a calibrated probability. |
| `provenance` | `Provenance` | Yes | Information about how the observation was produced. |

**Validation rules**

- The ID, type and description must not be blank.
- At least one source reference is required.
- Confidence must be finite and within 0–1.
- Artifact references must not be blank or duplicated.
- Source intervals and artifact references must be checked against existing records by the service layer.

## 3. Entity

**Python file:** `src/vigil/domain/entity.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `entity_id` | `str` | Yes | Stable identifier for a detected or tracked entity. |
| `entity_type` | Literal | Yes | Category: person, vehicle, animal, object or unknown. |
| `label` | `str \| None` | No | Optional human-readable label; not necessarily a verified identity. |
| `associated_observation_ids` | `list[str]` | Yes | IDs of observations associated with this entity; at least one is required. |
| `attributes` | `dict[str, str \| int \| float \| bool \| None]` | No | Optional structured attributes such as clothing color or vehicle type. Defaults to an empty dictionary. |

**Validation rules**

- Entity IDs must not be blank.
- At least one associated observation is required.
- Observation references must not be blank or duplicated.
- Attribute names must not be blank.
- Numeric attribute values must be finite.
- Association and identity consistency must be evaluated by the service layer.

## 4. Event

**Python file:** `src/vigil/domain/event.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `event_id` | `str` | Yes | Stable unique identifier for the event. |
| `event_type` | `str` | Yes | Category of occurrence, such as restricted-area entry. |
| `description` | `str` | Yes | Human-readable description of the occurrence. |
| `observation_ids` | `list[str]` | Yes | Supporting observation IDs; at least one is required. |
| `entity_ids` | `list[str]` | No | Associated entity IDs. Defaults to an empty list. |
| `status` | Literal | Yes | Review state: proposed, under review, confirmed or rejected. Defaults to proposed. |
| `start_time` | `datetime \| None` | No | Optional timezone-aware estimated wall-clock start time. |
| `end_time` | `datetime \| None` | No | Optional timezone-aware estimated wall-clock end time. |

**Validation rules**

- Event IDs, types and descriptions must not be blank.
- At least one supporting observation is required.
- Observation and entity references must not be blank or duplicated.
- Timestamps must be timezone-aware when supplied.
- End time must not precede start time when both are supplied.
- Event references must resolve to existing records.
- Confirmation status must not be treated as proof without an established verification process.

## 5. EventLink

**Python file:** `src/vigil/domain/event_link.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `event_link_id` | `str` | Yes | Stable unique identifier for the relationship. |
| `from_event_id` | `str` | Yes | ID of the source event. |
| `to_event_id` | `str` | Yes | ID of the destination event. |
| `relationship_type` | Literal | Yes | Relationship: before, after, overlaps, related to or possible same incident. |
| `rationale` | `str` | Yes | Explanation for recording the relationship. |
| `confidence` | `float \| None` | No | Optional producer-reported confidence score between 0 and 1. |
| `created_at` | `datetime` | Yes | Timezone-aware relationship creation timestamp; defaults to UTC now. |

**Validation rules**

- Event IDs and rationale must not be blank.
- Source and destination events must differ.
- Confidence must be finite and within 0–1.
- Creation timestamps must be timezone-aware.
- Both event references must resolve to existing events.
- Relationship direction and inverse semantics must be documented before implementing correlation rules.
- Temporal association must not automatically imply causation.

## 6. EvidenceAssessment

**Python file:** `src/vigil/domain/evidence_assessment.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `assessment_id` | `str` | Yes | Stable unique identifier for the assessment. |
| `target_type` | Literal | Yes | Type of assessed record: observation or event. |
| `target_id` | `str` | Yes | ID of the record being assessed. |
| `assessment_type` | Literal | Yes | Assessment dimension: evidence quality, support level or uncertainty. |
| `rating` | Literal | Yes | Qualitative rating: insufficient, low, moderate or high. |
| `rationale` | `str` | Yes | Explanation supporting the assessment. |
| `assessed_by` | `str` | Yes | Name or identifier of the assessor or assessment tool. |
| `created_at` | `datetime` | Yes | Timezone-aware assessment timestamp; defaults to UTC now. |

**Validation rules**

- Assessment ID, target ID, rationale and assessor must not be blank.
- Target type and assessment type must use declared values.
- The target must exist and match the declared target type.
- Ratings must be interpreted according to documented assessment criteria.
- Assessments must remain distinct from model confidence scores.

## Shared conventions

- All schema models inherit from the shared `DomainModel`.
- Unknown information must remain optional rather than being fabricated.
- IDs identify records; they do not prove that the referenced records exist.
- Cross-record existence and integrity checks belong in a repository or service layer.
- Source references preserve media-relative time; wall-clock time is optional and timezone-aware.
- Changes to fields, types, relationships or validation rules require corresponding tests and documentation updates.