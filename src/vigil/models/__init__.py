"""VIGIL LLM and multi-modal model abstractions."""

from vigil.models.base import BaseLLMClient, LLMResponse
from vigil.models.factory import get_llm_client
from vigil.models.gemini import GeminiClient
from vigil.models.groq import GroqClient
from vigil.models.local import OpenAICompatibleClient
from vigil.models.mock import MockLLMClient
from vigil.models.nvidia_nim import NvidiaNIMClient
from vigil.models.vlm_preprocessor import (
    GreedyKnapsackBatcher,
    ImageBatch,
    Llama32VisionPreprocessor,
    PreprocessedImage,
)

__all__ = [
    "BaseLLMClient",
    "GeminiClient",
    "GreedyKnapsackBatcher",
    "GroqClient",
    "ImageBatch",
    "LLMResponse",
    "Llama32VisionPreprocessor",
    "MockLLMClient",
    "NvidiaNIMClient",
    "OpenAICompatibleClient",
    "PreprocessedImage",
    "get_llm_client",
]
