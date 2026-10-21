"""Google Gemini Free Tier client using standard library HTTP."""

from __future__ import annotations

import base64
import json
import logging
import random
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from vigil.models.base import BaseLLMClient, LLMResponse

logger = logging.getLogger(__name__)

# HTTP status codes that are transient and worth retrying automatically.
_RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

# ---------------------------------------------------------------------------
# Global API-call throttle
# ---------------------------------------------------------------------------
# Gemini Free Tier allows 15 requests/minute per API key.  When multiple
# investigations run in parallel they all share the same key, so we cap the
# number of *concurrent* outbound API calls to avoid hammering the quota and
# triggering 503 / read-timeout cascades.
#
# The semaphore does NOT serialise calls entirely – up to MAX_CONCURRENT_CALLS
# requests may be in flight simultaneously.  Callers that cannot acquire the
# semaphore block until a slot opens, which gracefully queues work rather than
# failing fast.
_MAX_CONCURRENT_CALLS: int = 2  # tune via VIGIL_GEMINI_MAX_CONCURRENT env var
try:
    import os as _os
    _MAX_CONCURRENT_CALLS = int(_os.getenv("VIGIL_GEMINI_MAX_CONCURRENT", "2"))
except (TypeError, ValueError):
    pass

_api_semaphore: threading.Semaphore = threading.Semaphore(_MAX_CONCURRENT_CALLS)


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


class GeminiAPIError(RuntimeError):
    """Raised when the Gemini API returns an error or fails."""


class GeminiClient(BaseLLMClient):
    """Client for Google Gemini (Free Tier: Gemini 2.0 Flash / 1.5 Flash).

    Improvements over the original implementation
    --------------------------------------------
    * A **process-wide semaphore** caps concurrent outbound requests so that
      parallel investigations cannot flood the Free-Tier quota (15 RPM).
    * **Exponential back-off with full jitter** spreads retries across the
      time window instead of letting all threads wake up simultaneously.
    * **More retries by default** (5 instead of 3) to handle transient 503s
      and read timeouts that are common under load.
    * ``max_retries`` now applies uniformly to both HTTP errors *and* OS-level
      socket/timeout errors (previously OS errors stopped retrying after the
      retry counter was already 0).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        timeout_seconds: float = 120.0,
        max_retries: int = 5,
        retry_backoff_base: float = 2.0,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key must be provided.")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _backoff_delay(self, attempt: int) -> float:
        """Return a jittered exponential back-off delay for the given attempt number.

        Using *full jitter* (AWS recommendation) prevents the thundering-herd
        problem when multiple threads all hit a rate-limit at the same time.

        ``attempt`` is 1-based (first retry = attempt 1).
        """
        cap = 60.0  # never sleep more than 60 s
        base_delay = min(cap, self.retry_backoff_base ** attempt)
        return random.uniform(0.0, base_delay)  # noqa: S311

    def _call_api(self, payload: dict[str, Any]) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        data = json.dumps(payload).encode("utf-8")

        last_exc: Exception | None = None
        resp_data: dict[str, Any] = {}

        # Acquire the global semaphore *before* entering the retry loop so
        # that only MAX_CONCURRENT_CALLS threads are ever speaking to the API
        # at once.  The semaphore is released after the entire retry sequence
        # (success or final failure).
        with _api_semaphore:
            for attempt in range(self.max_retries + 1):
                if attempt > 0:
                    delay = self._backoff_delay(attempt)
                    logger.warning(
                        "GeminiClient: attempt %d/%d failed (%s); retrying in %.1fs",
                        attempt,
                        self.max_retries,
                        last_exc,
                        delay,
                    )
                    time.sleep(delay)

                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                    break  # success — exit retry loop
                except urllib.error.HTTPError as exc:
                    err_body = exc.read().decode("utf-8", errors="replace")
                    if exc.code in _RETRYABLE_HTTP_CODES and attempt < self.max_retries:
                        last_exc = RuntimeError(f"HTTP Error {exc.code}: {exc.reason}")
                        continue
                    raise GeminiAPIError(
                        f"Gemini API request failed with status {exc.code}: {err_body}"
                    ) from exc
                except OSError as exc:
                    # Covers socket.timeout, TimeoutError, ConnectionResetError, etc.
                    last_exc = exc
                    if attempt < self.max_retries:
                        continue
                    raise GeminiAPIError(f"Gemini API request failed: {exc}") from exc
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

    # ------------------------------------------------------------------
    # Public API (implements BaseLLMClient)
    # ------------------------------------------------------------------

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
                    "data": _ensure_base64_image(image_data),
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
