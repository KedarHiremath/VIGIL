"""OpenAI-compatible client for Ollama, OpenRouter, and local models."""

import json
import urllib.error
import urllib.request
from typing import Any

from vigil.models.base import BaseLLMClient, LLMResponse


class LocalAPIError(RuntimeError):
    """Raised when an OpenAI-compatible API returns an error."""


class OpenAICompatibleClient(BaseLLMClient):
    """Client for Ollama, OpenRouter, or other OpenAI-compatible endpoints."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str | None = None,
        model: str = "llama3.2-vision",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds

    def _call_completions(
        self, messages: list[dict[str, Any]], json_mode: bool
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise LocalAPIError(
                f"API request failed with {exc.code}: {err_body}"
            ) from exc
        except Exception as exc:
            raise LocalAPIError(f"API request failed: {exc}") from exc

        choices = resp_data.get("choices", [])
        if not choices:
            raise LocalAPIError("API returned no completion choices.")

        content = choices[0].get("message", {}).get("content", "")
        usage = resp_data.get("usage", {})
        return LLMResponse(
            content=content,
            model_name=self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        messages: list[dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        return self._call_completions(messages, json_mode)

    def analyze_image(
        self,
        prompt: str,
        image_data: str,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        image_url = (
            f"data:{mime_type};base64,{image_data}"
            if not image_data.startswith("http")
            else image_data
        )
        messages: list[dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        )
        return self._call_completions(messages, json_mode)
