# VIGIL — Project Context (Layer 1: Domain & Orchestration Contracts)

Agentic video-forensics system. **Currently implemented: Pydantic schemas only** (no persistence, services, agents, or API yet). `src/vigil/__init__.py` is still the `uv init` placeholder (`main()` prints hello).

## Stack & Tooling
- Python `>=3.12,<3.13` (pinned 3.12), managed with **uv** (`uv_build` backend, `src/` layout, module `vigil`, script `vigil = vigil:main`)
- Runtime deps: `pydantic>=2.7,<3` (locked 2.14.1), `tzdata`
- Dev deps: `pytest>=8.0` (locked 9.1.1), `ruff>=0.9` (locked 0.17.0)
- Commands: `uv sync` · `uv run pytest tests/unit/domain/test_source_media_schemas.py -v` · `uv run ruff check [--fix] src/vigil/domain tests/unit/domain` · `uv run ruff format [--check] ...`
- Authors: KedarHiremath, kriti03ka

## Structure
```
src/vigil/
  domain/         base, common, camera, media_asset, source_reference, artifact,
                  provenance, observation, entity, event, event_link,
                  evidence_assessment, investigation, coverage, report
  orchestration/  task_types, investigation_state
documentation/architectures/   5 spec .md files (one per schema group + shared_contracts)
tests/unit/domain/             (tests exist per docs; not provided)
```
`domain/__init__.py` exports only `CoverageRecord`, `CoverageStatus`, `Investigation`, `Report`.

## Shared Foundation
- **`DomainModel`** (base for all): `extra="forbid"`, `str_strip_whitespace`, `validate_assignment`, **`frozen=True`** (immutable).
- **`common.py` types:** `Identifier` (stripped, nonblank str) · `Timestamp` (`AwareDatetime`) · `ConfidenceScore` (float 0–1, no inf/NaN) · `ReferenceIds` (list of `Identifier`, nonblank + unique after strip).

## Conventions (shared_contracts)
- IDs: opaque nonblank strings; prefixes (`media-`, `event-`) are readability only; existence is **not** validated by schemas.
- Time: tz-aware only, UTC default; media-relative seconds kept separate from wall-clock; unknown stays `None` (never fabricate). Intervals are half-open `[start, end)`.
- Confidence ≠ uncertainty ≠ evidence quality; score is not a calibrated probability.
- Store ID references, not copies of objects. Provenance aids traceability, doesn't prove correctness.
- Validation layers: schema → cross-reference → workflow → persistence → semantic. Each rule lives at the boundary that can enforce it.
- Versioning: baseline contract `1.0` (documentation only; no `schema_version` field on models). Prefer additive optional fields.

## Domain Schemas
**Source/media**
| Model | Key fields | Validation |
|---|---|---|
| `Camera` | `camera_id`, `name`, `location_label?`, `timezone?`, `clock_offset_seconds?` | valid IANA tz; finite offset |
| `MediaAsset` | `media_asset_id`, `media_type` (video/audio/image), `storage_uri`, `camera_id?`, `duration_seconds?`, `recorded_at?`, `sha256?` | duration >0 & finite; sha256 = 64 hex; URI nonblank |
| `SourceReference` | `media_asset_id`, `start_seconds` (≥0), `end_seconds` (>0), `source_timestamp?` | finite; `end > start` |
| `Artifact` | `artifact_id`, `artifact_type` (frame/crop/clip/audio_segment/derived_media), `media_type`, `storage_uri`, `source_reference`, `sha256?`, `created_at` | frame/crop→image, clip→video, audio_segment→audio; `derived_media` any |

**Evidence/interpretation**
| Model | Key fields | Validation |
|---|---|---|
| `Provenance` | `producer_type` (vision_model/audio_model/rule/agent/human/other), `producer_name`, `producer_version?`, `method`, `input_artifact_ids`, `parent_observation_ids`, `created_at` | — |
| `Observation` | `observation_id`, `modality`, `observation_type`, `description`, `source_references` (≥1), `artifact_ids`, `confidence?`, `provenance` | ≥1 source ref |
| `Entity` | `entity_id`, `entity_type` (person/vehicle/animal/object/unknown), `label?` (not verified identity), `associated_observation_ids` (≥1), `attributes` (str/int/float/bool/None) | nonblank keys; finite floats |
| `Event` | `event_id`, `event_type`, `description`, `observation_ids` (≥1), `entity_ids`, `status` (proposed→under_review/confirmed/rejected; default proposed), `start_time?`, `end_time?` | `end ≥ start` |
| `EventLink` | `event_link_id`, `from_event_id`, `to_event_id`, `relationship_type` (before/after/overlaps/related_to/possible_same_incident), `rationale`, `confidence?`, `created_at` | no self-link |
| `EvidenceAssessment` | `assessment_id`, `target_type` (observation/event), `target_id`, `assessment_type` (evidence_quality/support_level/uncertainty), `rating` (insufficient/low/moderate/high), `rationale`, `assessed_by`, `created_at` | distinct from confidence |

**Investigation management**
| Model | Key fields | Validation |
|---|---|---|
| `Investigation` | `investigation_id`, `title`, `objective`, `scope_description`, `media_asset_ids`, `source_reference_ids`, `created_at`, `created_by?` | no lifecycle status here |
| `CoverageRecord` | `coverage_id`, `investigation_id`, `source_reference_id`, `status` (`CoverageStatus`: examined/partial/failed/not_examined), `interval_start?/end?`, `examined_at?`, `notes?`, `artifact_ids` | interval bounds both-or-neither; `end ≥ start`; `examined` requires `examined_at`; notes nonblank |
| `Report` | `report_id`, `investigation_id`, `title`, `summary`, `observation_ids`, `event_ids`, `assessment_ids`, `coverage_ids`, `generated_at`, `generated_by` | nonblank text |

Coverage records describe examination activity only — `not_examined` ≠ "examined, nothing found".

## Orchestration Schemas
| Model | Key fields | Validation |
|---|---|---|
| `TaskStatus` (enum) | pending, running, completed, partial, failed | execution status only, not truth/confidence |
| `ErrorDetail` | `code`, `message`, `retryable`, `retry_after_seconds?` (≥0, finite) | retry delay only if `retryable` |
| `TaskRequest` | `task_id`, `task_type`, `input_refs`, `parameters` (JSON dict), `requested_by?`, `created_at` | nonblank type |
| `TaskResult` | `task_id`, `status`, `output_refs`, `error?`, `started_at?`, `completed_at?` | failed ⇒ error required; completed ⇒ no error; `completed ≥ started` |
| `ModelOutput` | `output_id`, `producer_name`, `output_type`, `payload` (JSON dict), `confidence?`, `artifact_ids`, `created_at` | tool-specific payload validated elsewhere |
| `InvestigationStatus` (enum) | created, running, paused, completed, failed | — |
| `InvestigationState` | `investigation_id`, `status` (default created), `task_ids`, `observation_ids`, `event_ids`, `started_at?`, `updated_at`, `completed_at?` | completed/failed ⇒ `completed_at`; `completed ≥ started` |

## Explicitly Deferred (service/repository layer)
Referential existence checks · ID generation/uniqueness · media↔wall-clock conversion · interval-within-duration checks · state transitions, retries, scheduling · coverage sufficiency rules · report rendering/versioning/approval · schema-version migration tooling · provenance propagation · confirmation/verification process for events.

## Notes / Gaps
- Docs say `TaskResult` `partial` may carry an error; code allows it but doesn't require it.
- Docs list "interval must fit media duration" and "referenced IDs must exist" for `SourceReference`/`Artifact`/`MediaAsset`; these are **not** enforced in the schemas (by design, service layer).
- `InvestigationStatus` lives in `orchestration/investigation_state.py`; `Investigation` (domain) has no status.
- Test files, `README.md`, and any `Command_History`/`.gitignore` details beyond the above weren't relevant to the schema context.
