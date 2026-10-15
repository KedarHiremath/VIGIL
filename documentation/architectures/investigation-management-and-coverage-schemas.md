# Investigation Management and Coverage Schemas

## 1. Purpose

This document defines the domain contracts for managing investigations, recording examination coverage, and producing structured reports in VIGIL.

The schemas build on the existing source/media and evidence schemas. They store references to existing objects rather than duplicating their contents.

## 2. Investigation

**Source file:** `src/vigil/domain/investigation.py`

**Purpose:** Represents an investigation, its objective, its scope, and the media/source references associated with it.

| Attribute | Type | Required | Description |
|---|---|---|---|
| `investigation_id` | `str` | Yes | Unique identifier for the investigation. Must not be blank. |
| `title` | `str` | Yes | Human-readable investigation title. |
| `objective` | `str` | Yes | Describes what the investigation aims to establish. |
| `scope_description` | `str` | Yes | Describes the investigation boundaries and constraints. |
| `media_asset_ids` | `list[str]` | No | IDs of media assets associated with the investigation. Defaults to an empty list. |
| `source_reference_ids` | `list[str]` | No | IDs of source references associated with the investigation. Defaults to an empty list. |
| `created_at` | `datetime` | No | Time the investigation record was created. Defaults to the current UTC time and must be timezone-aware. |
| `created_by` | `str \| None` | No | Optional identifier for the user or component that created the investigation. |

### Validation rules

- Required text fields cannot be blank.
- Media and source reference IDs must be nonblank and unique within their respective lists.
- `created_at` must be timezone-aware.
- Unknown fields are rejected through the shared `DomainModel` configuration.
- The schema does not currently define investigation lifecycle status.

## 3. CoverageRecord

**Source file:** `src/vigil/domain/coverage.py`

**Purpose:** Records whether a source or time interval was examined and captures the outcome and associated artifacts.

### CoverageStatus values

| Value | Meaning |
|---|---|
| `examined` | The examination was completed successfully. |
| `partial` | Only part of the intended examination was completed. |
| `failed` | The examination attempt failed. |
| `not_examined` | The source or interval has not been examined. |

### Attributes

| Attribute | Type | Required | Description |
|---|---|---|---|
| `coverage_id` | `str` | Yes | Unique identifier for this coverage record. |
| `investigation_id` | `str` | Yes | Identifier of the associated investigation. |
| `source_reference_id` | `str` | Yes | Identifier of the source being examined. |
| `status` | `CoverageStatus` | Yes | Outcome of the examination. |
| `interval_start` | `datetime \| None` | No | Start of the interval being examined. |
| `interval_end` | `datetime \| None` | No | End of the interval being examined. |
| `examined_at` | `datetime \| None` | No | Time the examination was recorded as completed or attempted. |
| `notes` | `str \| None` | No | Explanation of limitations, failures, or other relevant details. |
| `artifact_ids` | `list[str]` | No | IDs of artifacts produced by the examination. Defaults to an empty list. |

### Validation rules

- Required identifiers must not be blank.
- Supplied timestamps must be timezone-aware.
- `interval_start` and `interval_end` must either both be provided or both be omitted.
- The interval end cannot precede the interval start.
- `examined` status requires `examined_at`.
- Artifact IDs must be nonblank and unique.
- Optional notes cannot be blank when supplied.

### Interpretation rule

Coverage records describe examination activity. They do not establish that a source contains no relevant events. In particular, `not_examined` must not be interpreted as a successful examination with no findings.

## 4. Report

**Source file:** `src/vigil/domain/report.py`

**Purpose:** Represents structured investigation findings and references the evidence and coverage records supporting them.

| Attribute | Type | Required | Description |
|---|---|---|---|
| `report_id` | `str` | Yes | Unique report identifier. |
| `investigation_id` | `str` | Yes | Identifier of the investigation summarized by the report. |
| `title` | `str` | Yes | Human-readable report title. |
| `summary` | `str` | Yes | High-level summary of findings. |
| `observation_ids` | `list[str]` | No | IDs of supporting observations. Defaults to an empty list. |
| `event_ids` | `list[str]` | No | IDs of supporting events. Defaults to an empty list. |
| `assessment_ids` | `list[str]` | No | IDs of evidence assessments used in the report. Defaults to an empty list. |
| `coverage_ids` | `list[str]` | No | IDs of relevant coverage records. Defaults to an empty list. |
| `generated_at` | `datetime` | No | Report generation time. Defaults to the current UTC time and must be timezone-aware. |
| `generated_by` | `str` | Yes | Identifier of the user or component that generated the report. |

### Validation rules

- Required text fields cannot be blank.
- Each evidence/coverage reference list must contain unique, nonblank IDs.
- `generated_at` must be timezone-aware.
- Unknown fields are rejected through `DomainModel`.

## 5. Dependencies and boundaries

The schemas reference existing domain concepts:

- `Investigation` references media assets and source references.
- `CoverageRecord` references an investigation, a source reference, and optional artifacts.
- `Report` references an investigation, observations, events, evidence assessments, and coverage records.

These are identifier references, not automatic database relationships. Referential existence checks, persistence, and cross-record consistency are responsibilities of a later repository or application-service layer.

## 6. Intentionally deferred

The following are outside this schema set's current scope:

- Investigation lifecycle transitions.
- Automatic calculation of examination completeness.
- Rules for deciding whether coverage is sufficient.
- Report rendering to PDF, HTML, or other formats.
- Validation that every referenced ID exists in persistent storage.
- Report versioning and approval workflows.

These capabilities can be added when the corresponding application behavior is designed.