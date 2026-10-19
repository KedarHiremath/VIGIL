"""Google Gemini Free Tier client using standard library HTTP."""

import json
import urllib.error
import urllib.request
from typing import Any

from vigil.models.base import BaseLLMClient, LLMResponse


class GeminiAPIError(RuntimeError):
    """Raised when the Gemini API returns an error or fails."""


class GeminiClient(BaseLLMClient):
    """Client for Google Gemini (Free Tier: Gemini 2.0 Flash / 1.5 Flash)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key must be provided.")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds

    def _call_api(self, payload: dict[str, Any]) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise GeminiAPIError(
                f"Gemini API request failed with status {exc.code}: {err_body}"
            ) from exc
        except Exception as exc:
            raise GeminiAPIError(f"Gemini API request failed: {exc}") from exc

        try:
            candidates = resp_data.get("candidates", [])
            if not candidates:
                raise GeminiAPIError("Gemini API returned no candidates.")
            content_parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = [
                part.get("text", "") for part in content_parts if "text" in part
            ]
            return "".join(text_parts)
        except (KeyError, IndexError) as exc:
            raise GeminiAPIError(
                f"Failed to parse Gemini API response: {resp_data}"
            ) from exc

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {},
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}],
            }

        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        content = self._call_api(payload)
        return LLMResponse(content=content, model_name=self.model)

    def analyze_image(
        self,
        prompt: str,
        image_data: str,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        parts: list[dict[str, Any]] = [
            {"text": prompt},
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": image_data,
                }
            },
        ]

        payload: dict[str, Any] = {
            "contents": [
                {
                    "parts": parts,
                }
            ],
            "generationConfig": {},
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}],
            }

        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        content = self._call_api(payload)
        return LLMResponse(content=content, model_name=self.model)
