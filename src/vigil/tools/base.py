"""Base tool worker and utility contracts for VIGIL."""

import abc
import hashlib
from datetime import UTC, datetime

from vigil.models.base import BaseLLMClient
from vigil.models.factory import get_llm_client
from vigil.orchestration.task_types import (
    ErrorDetail,
    TaskRequest,
    TaskResult,
    TaskStatus,
)
from vigil.storage.repository import InvestigationRepository


def generate_sha256(content: str | bytes) -> str:
    """Generate a 64-character hexadecimal SHA-256 string."""
    raw = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(raw).hexdigest()


class BaseToolWorker(abc.ABC):
    """Base class for VIGIL task workers with timing, error trapping, and repository access."""

    def __init__(
        self,
        repository: InvestigationRepository,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.repository = repository
        self.llm = llm_client or get_llm_client()

    @abc.abstractmethod
    def run(self, request: TaskRequest) -> list[str]:
        """Execute tool logic and return output reference IDs."""
        ...

    def execute(self, request: TaskRequest) -> TaskResult:
        """Conform to the TaskWorker protocol with full contract guarantees."""
        started_at = datetime.now(UTC)

        try:
            output_refs = self.run(request)
            completed_at = datetime.now(UTC)

            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.COMPLETED,
                output_refs=output_refs,
                error=None,
                started_at=started_at,
                completed_at=completed_at,
            )
        except Exception as exc:  # noqa: BLE001
            completed_at = datetime.now(UTC)
            return TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                output_refs=[],
                error=ErrorDetail(
                    code=self.__class__.__name__.upper(),
                    message=f"Tool execution failed: {exc!s}",
                    retryable=False,
                ),
                started_at=started_at,
                completed_at=completed_at,
            )
