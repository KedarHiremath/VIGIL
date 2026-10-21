"""Groq Cloud Free Tier client using standard library HTTP."""

import base64
from pathlib import Path
from urllib.parse import unquote, urlparse


def _ensure_base64_image(image_data: str) -> str:
    """Resolve file URI or local path into base64 string if necessary."""
    try:
        if image_data.startswith("file://"):
            parsed = urlparse(image_data)
            path_str = unquote(parsed.path)
            if path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
                path_str = path_str[1:]
            p = Path(path_str)
            if p.is_file():
                return base64.b64encode(p.read_bytes()).decode("utf-8")
        elif Path(image_data).is_file():
            return base64.b64encode(Path(image_data).read_bytes()).decode("utf-8")
    except Exception:
        pass
    return image_data

import json
import urllib.error
import urllib.request
from typing import Any

from vigil.models.base import BaseLLMClient, LLMResponse

# Cloudflare (error code 1010) blocks requests with the default Python-urllib
# User-Agent. Use a browser-like UA so the Groq API edge passes the request.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class GroqAPIError(RuntimeError):
    """Raised when Groq API returns an error."""


class GroqClient(BaseLLMClient):
    """Client for Groq Cloud Free Tier (GPT-OSS 20B reasoning, Whisper audio)."""

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
                "User-Agent": _USER_AGENT,
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
        b64_data = _ensure_base64_image(image_data)
        image_url = (
            f"data:{mime_type};base64,{b64_data}"
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
