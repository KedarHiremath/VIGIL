# VIGIL Orchestration — Executor, Transitions and Service Specification

**Status:** Initial implementation specification
**Scope:** `TaskExecutor` and its exceptions (`executor.py`), `transition_state` and the lifecycle table (`transitions.py`), `OrchestrationService` and its outcome/exception types (`service.py`)

**Depends on:** `TaskRequest`, `TaskResult`, `TaskStatus`, `ErrorDetail` (`task_types.py`) and `InvestigationState`, `InvestigationStatus` (`investigation_state.py`).

## 0. How the three modules fit together

```
caller
  │  execute_task(state, request)
  ▼
OrchestrationService  (service.py)      ← owns the workflow: preconditions, state updates, failure policy
  │ uses                       │ uses
  ▼                            ▼
TaskExecutor (executor.py)     transition_state (transitions.py)
  routes request → worker        validates lifecycle changes
  validates the TaskResult       returns a NEW InvestigationState
  │
  ▼
TaskWorker implementations (not yet written)
```

- The **executor** knows about tasks only. It never sees `InvestigationState`.
- **Transitions** know about investigation lifecycle only. They never see tasks.
- The **service** is the only module that knows about both and decides what a task outcome means for the investigation.
- All state objects are immutable (`DomainModel` is `frozen=True`). Every "update" returns a new object that is re-validated through Pydantic.

---

## 1. executor.py

**Python file:** `src/vigil/orchestration/executor.py`

### 1.1 TaskWorker (Protocol)

| Member | Signature | Description |
|---|---|---|
| `execute` | `(request: TaskRequest) -> TaskResult` | Executes one task synchronously and returns its final result. |

Any object with a matching `execute` method is a valid worker (structural typing; no inheritance required).

### 1.2 Exceptions

| Exception | Base | Raised when |
|---|---|---|
| `ExecutorError` | `Exception` | Base class for all executor errors. |
| `UnknownTaskTypeError` | `ExecutorError` | No worker is registered for the request's `task_type`. |
| `TaskResultContractError` | `ExecutorError` | A worker returns something that violates the result contract. |
| `WorkerExecutionError` | `ExecutorError` | **Raised by workers** to report an expected, handled execution failure. The executor does not raise or catch it. |

### 1.3 TaskExecutor

| Attribute / method | Description |
|---|---|
| `_workers: dict[str, TaskWorker]` | Private registry mapping a normalized task type to its worker. |
| `register(task_type, worker) -> None` | Registers exactly one worker for a task type. |
| `execute(request) -> TaskResult` | Looks up the worker, runs it and validates the returned result. |

**`register` rules**

- The task type is stripped of surrounding whitespace before use.
- A blank task type raises `ValueError`.
- Registering a second worker for the same (normalized) task type raises `ValueError`; workers are never silently replaced.

**`execute` rules (in order)**

1. Look up the worker by `request.task_type`. If none exists → `UnknownTaskTypeError`.
2. Call `worker.execute(request)`.
3. The return value must be a `TaskResult` instance → otherwise `TaskResultContractError`.
4. `result.task_id` must equal `request.task_id` → otherwise `TaskResultContractError`.
5. `result.status` must be final (`completed`, `partial` or `failed`). `pending` or `running` → `TaskResultContractError`, because this executor is synchronous.
6. Return the result unchanged.

**What the executor deliberately does not do**

- It does not catch worker exceptions. `WorkerExecutionError` and any unexpected exception propagate to the caller.
- It does not retry, time, log, schedule or run tasks concurrently.
- It does not check that `output_refs` point to existing records.
- It does not inspect `TaskResult.error` beyond what `TaskResult` already validates for itself.

---

## 2. transitions.py

**Python file:** `src/vigil/orchestration/transitions.py`

### 2.1 InvalidStateTransitionError

Subclass of `ValueError`. Raised when a requested lifecycle change is not in the allowed table.

### 2.2 Allowed transitions

| From | Allowed next states |
|---|---|
| `created` | `running`, `failed` |
| `running` | `paused`, `completed`, `failed` |
| `paused` | `running`, `failed` |
| `completed` | *(none — terminal)* |
| `failed` | *(none — terminal)* |

Consequences worth knowing:

- Same-state transitions (for example `running → running`) are **not** allowed and raise.
- `created → completed` is not allowed; an investigation must pass through `running`.
- `completed` and `failed` are terminal and cannot be reopened.

The table is the module-private constant `_ALLOWED_TRANSITIONS`.

### 2.3 transition_state

| Parameter | Type | Description |
|---|---|---|
| `state` | `InvestigationState` | Current state. Never modified. |
| `new_status` | `InvestigationStatus` | Requested status. |
| **Returns** | `InvestigationState` | A new, validated state. |

**Behavior**

1. If `new_status` is not allowed from `state.status` → `InvalidStateTransitionError` (message includes both status values).
2. Take a single `now = datetime.now(UTC)`.
3. Always set `status = new_status` and `updated_at = now`.
4. When moving to `running` **and** `started_at` is `None`, set `started_at = now`. Resuming from `paused` therefore keeps the original `started_at`.
5. When moving to `completed` or `failed`, set `completed_at = now`.
6. Build the result with `InvestigationState.model_validate(state.model_dump() | updates)`, so every `InvestigationState` validator runs again. (`model_copy(update=...)` is intentionally avoided because it skips validation.)

---

## 3. service.py

**Python file:** `src/vigil/orchestration/service.py`

### 3.1 TaskExecutionOutcome

Frozen, slotted `dataclass` returned by `execute_task`.

| Attribute | Type | Description |
|---|---|---|
| `state` | `InvestigationState` | The investigation state after the task was processed. |
| `task_result` | `TaskResult` | The result returned by the worker, or a synthesized failure result. |

### 3.2 Exceptions

| Exception | Base | Raised when |
|---|---|---|
| `OrchestrationServiceError` | `RuntimeError` | Base class for service errors. |
| `InvalidInvestigationStateError` | `OrchestrationServiceError` | The investigation's status does not allow the requested operation. |
| `DuplicateTaskError` | `OrchestrationServiceError` | `request.task_id` is already in `state.task_ids`. |

`UnknownTaskTypeError`, `TaskResultContractError` and `InvalidStateTransitionError` are **not** wrapped; they pass through the service unchanged.

### 3.3 OrchestrationService

Constructed with a `TaskExecutor`. It holds no investigation state itself; state is passed in and returned.

#### `execute_task(state, request) -> TaskExecutionOutcome`

**Preconditions**

- `state.status` must be `created` or `running`; otherwise `InvalidInvestigationStateError`. (`paused`, `completed` and `failed` investigations cannot accept tasks.)
- `request.task_id` must not already be in `state.task_ids`; otherwise `DuplicateTaskError`.

**Flow**

1. Record `started_at = now`.
2. If the state is `created`, transition it to `running` (this also sets the investigation's `started_at`). If it is already `running`, use it as is.
3. Call `executor.execute(request)`.
   - `UnknownTaskTypeError` or `TaskResultContractError` → re-raised. These are configuration or contract bugs and must stay visible. The input state is untouched, so the caller still holds the pre-call state.
   - `WorkerExecutionError` → converted into a `TaskResult` with `status=failed`, `output_refs=[]`, `error=ErrorDetail(code="WORKER_EXECUTION_ERROR", message="The worker reported an execution failure.", retryable=False)`, and the service's `started_at` / `completed_at` timestamps.
4. Build a new state containing `task_ids + [request.task_id]` and `updated_at = finished_at`.
5. If the task result is `failed`, transition that state to `failed` (setting `completed_at`). Otherwise return it as is; `completed` and `partial` tasks leave the investigation `running`.
6. Return `TaskExecutionOutcome(state, task_result)`.

**Failure policy (current)**

| Task result | Investigation after the call |
|---|---|
| `completed` | `running` |
| `partial` | `running` |
| `failed` | `failed` (terminal) |

A single failed task therefore ends the whole investigation. `ErrorDetail.retryable` is recorded but not acted on.

#### `complete_investigation(state) -> InvestigationState`

- Only a `running` investigation can be completed; otherwise `InvalidInvestigationStateError`.
- Delegates to `transition_state(state, COMPLETED)`.

---

## 4. Known limitations and deferred work

- **No output recording.** `TaskResult.output_refs` are not written into `InvestigationState.observation_ids` or `event_ids`.
- **No pause, resume or explicit fail operations** on the service. The `paused` state exists in the lifecycle table but nothing in the service reaches it.
- **Worker failure details are discarded.** The message of a caught `WorkerExecutionError` is replaced by a generic message; the error code is always `WORKER_EXECUTION_ERROR` and `retryable` is always `false`.
- **Unexpected worker exceptions** (anything other than `WorkerExecutionError`) propagate out of the service without being recorded in state.
- **No persistence.** State lives only in the returned objects; nothing is stored.
- **Synchronous, single-task execution only.** No retries, scheduling, timeouts or concurrency.
- **No existence checks** on `input_refs` or `output_refs`; these belong to the future repository/application layer (see `shared_contracts.md`, section 8).
- **No concrete workers** are registered anywhere yet.

## 5. Testing expectations

Changes to these modules should be accompanied by unit tests covering at least:

- Executor: blank/duplicate registration, unknown task type, non-`TaskResult` return, mismatched `task_id`, `pending`/`running` result, normal pass-through.
- Transitions: every allowed and disallowed pair, `started_at` set only on the first `running`, `completed_at` set on terminal states, input state not mutated.
- Service: the three task outcomes, `created → running` on first task, duplicate task ID, invalid state, `WorkerExecutionError` conversion, pass-through of configuration/contract errors, `complete_investigation` guard.
