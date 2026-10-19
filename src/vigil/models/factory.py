"""Factory for initializing LLM clients based on configuration."""

import logging
from typing import Literal

from vigil.config import VigilConfig, config
from vigil.models.base import BaseLLMClient
from vigil.models.gemini import GeminiClient
from vigil.models.groq import GroqClient
from vigil.models.local import OpenAICompatibleClient
from vigil.models.mock import MockLLMClient

logger = logging.getLogger(__name__)

ProviderType = Literal["gemini", "groq", "ollama", "openrouter", "mock"]


def get_llm_client(
    app_config: VigilConfig | None = None,
    override_provider: str | None = None,
) -> BaseLLMClient:
    """Create and return an LLM client based on configuration.

    Args:
        app_config: Optional custom configuration. Defaults to system config.
        override_provider: Force a specific provider (e.g. "mock", "gemini").

    Returns:
        Configured BaseLLMClient instance.
    """
    cfg = app_config or config
    provider = (override_provider or cfg.llm_provider).lower().strip()

    if provider == "gemini":
        if not cfg.gemini_api_key:
            logger.warning(
                "GEMINI_API_KEY is not set. Falling back to MockLLMClient. "
                "Set GEMINI_API_KEY in .env to use Google Gemini free tier."
            )
            return MockLLMClient(model_name="fallback-mock-gemini")
        return GeminiClient(
            api_key=cfg.gemini_api_key,
            model=cfg.gemini_model,
        )

    if provider == "groq":
        if not cfg.groq_api_key:
            logger.warning(
                "GROQ_API_KEY is not set. Falling back to MockLLMClient. "
                "Set GROQ_API_KEY in .env to use Groq free tier."
            )
            return MockLLMClient(model_name="fallback-mock-groq")
        return GroqClient(
            api_key=cfg.groq_api_key,
            reasoning_model=cfg.groq_reasoning_model,
            vision_model=cfg.groq_vision_model,
        )

    if provider == "ollama":
        return OpenAICompatibleClient(
            base_url=f"{cfg.ollama_base_url}/v1",
            api_key="ollama",
            model=cfg.ollama_model,
        )

    if provider == "openrouter":
        if not cfg.openrouter_api_key:
            logger.warning(
                "OPENROUTER_API_KEY is not set. Falling back to MockLLMClient."
            )
            return MockLLMClient(model_name="fallback-mock-openrouter")
        return OpenAICompatibleClient(
            base_url="https://openrouter.ai/api/v1",
            api_key=cfg.openrouter_api_key,
            model=cfg.openrouter_model,
        )

    return MockLLMClient()
