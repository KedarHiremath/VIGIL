"""Base protocol and common types for VIGIL LLM providers."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMResponse:
    """Standardized response from an LLM inference call."""

    content: str
    model_name: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@runtime_checkable
class BaseLLMClient(Protocol):
    """Protocol defining the standard interface for LLM operations in VIGIL."""

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate text or JSON completion from a textual prompt."""
        ...

    def analyze_image(
        self,
        prompt: str,
        image_data: str,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Analyze an image (base64 encoded or URI) with a prompt."""
        ...
