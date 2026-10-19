"""Tests for LLM clients and factory."""

import pytest

from vigil.config import VigilConfig
from vigil.models.base import BaseLLMClient
from vigil.models.factory import get_llm_client
from vigil.models.gemini import GeminiClient
from vigil.models.groq import GroqClient
from vigil.models.local import OpenAICompatibleClient
from vigil.models.mock import MockLLMClient


def test_mock_client_generation() -> None:
    client = MockLLMClient()
    assert isinstance(client, BaseLLMClient)

    resp = client.generate_text("Generate forensic plan for objective")
    assert "phases" in resp.content

    img_resp = client.analyze_image("Analyze scene", image_data="fake_data")
    assert "observations" in img_resp.content


def test_factory_fallback_to_mock_when_keys_missing() -> None:
    cfg = VigilConfig(
        llm_provider="gemini",
        gemini_api_key=None,
        gemini_model="gemini-2.0-flash",
        groq_api_key=None,
        groq_reasoning_model="llama-3.3-70b-versatile",
        groq_vision_model="llama-3.2-11b-vision-preview",
        groq_audio_model="whisper-large-v3",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.2-vision",
        openrouter_api_key=None,
        openrouter_model="google/gemini-2.0-flash-exp:free",
        storage_root="./storage",
        log_level="INFO",
    )
    client = get_llm_client(app_config=cfg)
    assert isinstance(client, MockLLMClient)


def test_gemini_client_init_validation() -> None:
    with pytest.raises(ValueError):
        GeminiClient(api_key="")

    client = GeminiClient(api_key="valid-key", model="gemini-2.0-flash")
    assert client.model == "gemini-2.0-flash"


def test_groq_client_init_validation() -> None:
    with pytest.raises(ValueError):
        GroqClient(api_key="")

    client = GroqClient(api_key="valid-groq-key")
    assert client.reasoning_model == "llama-3.3-70b-versatile"


def test_openai_compatible_client_init() -> None:
    client = OpenAICompatibleClient(
        base_url="http://localhost:11434/v1", model="llama3.2-vision"
    )
    assert client.base_url == "http://localhost:11434/v1"
    assert client.model == "llama3.2-vision"
