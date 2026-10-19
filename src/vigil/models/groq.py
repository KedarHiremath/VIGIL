"""Groq Cloud Free Tier client using standard library HTTP."""

import json
import urllib.error
import urllib.request
from typing import Any

from vigil.models.base import BaseLLMClient, LLMResponse


class GroqAPIError(RuntimeError):
    """Raised when Groq API returns an error."""


class GroqClient(BaseLLMClient):
    """Client for Groq Cloud Free Tier (Llama 3.3 70B, Llama 3.2 Vision, Whisper)."""

    def __init__(
        self,
        api_key: str,
        reasoning_model: str = "llama-3.3-70b-versatile",
        vision_model: str = "llama-3.2-11b-vision-preview",
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("Groq API key must be provided.")
        self.api_key = api_key.strip()
        self.reasoning_model = reasoning_model.strip()
        self.vision_model = vision_model.strip()
        self.timeout_seconds = timeout_seconds

    def _call_completions(
        self, model: str, messages: list[dict[str, Any]], json_mode: bool
    ) -> LLMResponse:
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise GroqAPIError(f"Groq API error {exc.code}: {err_body}") from exc
        except Exception as exc:
            raise GroqAPIError(f"Groq API request failed: {exc}") from exc

        choices = resp_data.get("choices", [])
        if not choices:
            raise GroqAPIError("Groq API returned no completion choices.")

        content = choices[0].get("message", {}).get("content", "")
        usage = resp_data.get("usage", {})
        return LLMResponse(
            content=content,
            model_name=model,
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
        return self._call_completions(self.reasoning_model, messages, json_mode)

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
        return self._call_completions(self.vision_model, messages, json_mode)
