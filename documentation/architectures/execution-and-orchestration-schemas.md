# VIGIL Layer 1 — Execution and Orchestration Schema Specification

**Status:** Initial implementation specification  
**Scope:** TaskRequest, TaskResult, TaskStatus, ErrorDetail, ModelOutput and InvestigationState

## 1. TaskRequest

**Python file:** `src/vigil/orchestration/task_types.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `task_id` | `str` | Yes | Stable unique identifier for the task. |
| `task_type` | `str` | Yes | Operation to perform, such as frame sampling or visual analysis. |
| `input_refs` | `list[str]` | No | IDs of media assets, artifacts or other inputs. Defaults to an empty list. |
| `parameters` | `dict[str, JsonValue]` | No | JSON-compatible parameters controlling the operation. Defaults to an empty dictionary. |
| `requested_by` | `str \| None` | No | Identifier of the requesting agent or component, if known. |
| `created_at` | `datetime` | Yes | Timezone-aware task creation timestamp; defaults to UTC now. |

**Validation rules**

- Task IDs and task types must not be blank.
- Input references must not be blank or duplicated.
- Creation timestamps must be timezone-aware.
- Parameters must contain JSON-compatible values.
- Referenced inputs must be resolved by the service or repository layer.

## 2. TaskStatus

**Python file:** `src/vigil/orchestration/task_types.py`

| Value | Meaning |
|---|---|
| `pending` | Task is waiting to execute. |
| `running` | Task is currently executing. |
| `completed` | Task completed successfully. |
| `partial` | Task produced partial results but did not complete all requested work. |
| `failed` | Task execution failed. |

These values describe execution, not the truth or confidence of an analysis finding.

## 3. ErrorDetail

**Python file:** `src/vigil/orchestration/task_types.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `code` | `str` | Yes | Stable machine-readable error code. |
| `message` | `str` | Yes | Human-readable explanation of the error. |
| `retryable` | `bool` | Yes | Indicates whether retrying may succeed. |
| `retry_after_seconds` | `float \| None` | No | Optional non-negative delay before retrying. |

**Validation rules**

- Error code and message must not be blank.
- Retry delays must be finite and non-negative.
- A retry delay may be supplied only when the error is retryable.
- Retryability should be defined consistently for each error code.

## 4. TaskResult

**Python file:** `src/vigil/orchestration/task_types.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `task_id` | `str` | Yes | Identifier of the task producing the result. |
| `status` | `TaskStatus` | Yes | Execution lifecycle status. |
| `output_refs` | `list[str]` | No | IDs of outputs such as observations or artifacts. Defaults to an empty list. |
| `error` | `ErrorDetail \| None` | No | Structured execution error, when applicable. |
| `started_at` | `datetime \| None` | No | Timezone-aware execution start time, if known. |
| `completed_at` | `datetime \| None` | No | Timezone-aware execution end time, if known. |

**Validation rules**

- Task ID must not be blank.
- Output references must not be blank or duplicated.
- Execution timestamps must be timezone-aware.
- Completion time must not precede start time.
- Failed results require error details.
- Completed results must not contain an error.
- Partial results may include an error describing incomplete work.

## 5. ModelOutput

**Python file:** `src/vigil/orchestration/task_types.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `output_id` | `str` | Yes | Stable unique identifier for the model or tool output. |
| `producer_name` | `str` | Yes | Name of the model or tool producing the output. |
| `output_type` | `str` | Yes | Type of structured output, such as detection or transcription. |
| `payload` | `dict[str, JsonValue]` | Yes | JSON-compatible structured result. |
| `confidence` | `float \| None` | No | Optional producer-reported score between 0 and 1. |
| `artifact_ids` | `list[str]` | No | IDs of associated artifacts. Defaults to an empty list. |
| `created_at` | `datetime` | Yes | Timezone-aware output creation timestamp; defaults to UTC now. |

**Validation rules**

- Required identifiers and descriptive fields must not be blank.
- Payload values must be JSON-compatible.
- Confidence must be finite and within 0–1.
- Artifact references must not be blank or duplicated.
- Creation timestamps must be timezone-aware.
- Tool-specific payload structures must be validated by their respective contracts.

## 6. InvestigationState

**Python file:** `src/vigil/orchestration/investigation_state.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `investigation_id` | `str` | Yes | Stable identifier for the investigation workflow. |
| `status` | `InvestigationStatus` | Yes | Lifecycle state: created, running, paused, completed or failed. Defaults to created. |
| `task_ids` | `list[str]` | No | Associated task IDs. Defaults to an empty list. |
| `observation_ids` | `list[str]` | No | Observation IDs produced during the investigation. Defaults to an empty list. |
| `event_ids` | `list[str]` | No | Event IDs identified during the investigation. Defaults to an empty list. |
| `started_at` | `datetime \| None` | No | Timezone-aware investigation start time. |
| `updated_at` | `datetime` | Yes | Timezone-aware last-update timestamp; defaults to UTC now. |
| `completed_at` | `datetime \| None` | No | Timezone-aware terminal-state timestamp. |

**Validation rules**

- Investigation IDs must not be blank.
- References must not be blank or duplicated.
- All supplied timestamps must be timezone-aware.
- Completed and failed investigations require a completion timestamp.
- Completion time must not precede start time.
- References must resolve to existing records when validated by the service layer.

## Shared execution conventions

- All schema models inherit from the shared `DomainModel`.
- Task execution status is separate from evidence confidence and event verification status.
- Task and investigation IDs identify records but do not prove that referenced records exist.
- Schema validation does not execute tasks, perform retries or persist state.
- State transitions, retry policies, task scheduling and concurrency control belong to the orchestration implementation.
- Changes to contracts must be accompanied by updated tests and documentation.
