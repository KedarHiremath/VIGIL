"""NVIDIA NIM client for hosted VLM and LLM inference.

Dual-model design
-----------------
* **VLM** (visual tasks):  ``meta/llama-3.2-11b-vision-instruct``
  – Cosmos 3 Nano Reasoner is optimised for structured physical-scene reasoning
  from images/video frames; used by ``analyze_image``.
  Endpoint: ``https://ai.api.nvidia.com/v1``

* **LLM** (text reasoning):  ``nvidia/nemotron-3-nano-omni-30b-a3b-reasoning``
  – Nemotron 3 Nano 30B A3B (Reasoning) excels at timeline reconstruction,
  investigator Q&A, and structured report generation; used by ``generate_text``.
  Endpoint: ``https://integrate.api.nvidia.com/v1``

Note on endpoints
-----------------
NVIDIA operates two base URLs:
* ``integrate.api.nvidia.com`` — LLM / text models (Nemotron, Llama, Mistral…)
* ``ai.api.nvidia.com``        — VLM / multimodal models (Cosmos Reasoner…)

The client automatically routes each call to the correct base URL so callers
only need one API key.

Rate-limiting / reliability
---------------------------
A process-wide **global lock** (``threading.Lock``) serialises all outbound
calls to a single in-flight request at a time, preventing the free-tier
"Worker local total request limit" exhaustion (``ResourceExhausted 503``).

After every successful call a mandatory inter-request cool-down is observed
(``VIGIL_NVIDIA_INTER_REQUEST_DELAY`` env var, default 3.5 s) to keep the
per-minute request rate well under quota.

All transient HTTP errors (429, 500–504) and socket-level failures trigger
exponential back-off with full jitter (up to ``_MAX_BACKOFF_SECONDS``).

A per-call ``lock_acquire_timeout`` (default 600 s) prevents a slow or
retrying request from blocking the queue indefinitely: if the lock cannot
be acquired within that window the call raises ``NvidiaNIMError`` immediately
so the pipeline worker can log and move on.
"""

from __future__ import annotations

import base64
import json
import logging
import os
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Endpoint routing — NVIDIA uses two separate base URLs by model family
# ---------------------------------------------------------------------------
# LLM / text models  (Nemotron, Llama, Mistral …)
NVIDIA_LLM_BASE_URL = "https://integrate.api.nvidia.com/v1"
# VLM / multimodal models  (Cosmos Reasoner, NVLM …)
NVIDIA_VLM_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Default model identifiers (can be overridden via env / constructor)
DEFAULT_VLM_MODEL = "meta/llama-3.2-11b-vision-instruct"
DEFAULT_LLM_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

# HTTP status codes that are transient and worth retrying automatically
_RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

# Maximum back-off ceiling (seconds)
_MAX_BACKOFF_SECONDS: float = 60.0

# ---------------------------------------------------------------------------
# Global call serialiser + inter-request cool-down
# ---------------------------------------------------------------------------
# The NVIDIA NIM free-tier has a very small worker pool (16 slots).  Sending
# even two requests simultaneously reliably triggers:
#   ResourceExhausted: Worker local total request limit reached (16/16)
#
# Strategy:
#   1. A process-wide Lock serialises ALL outbound calls — only one request
#      is ever in-flight at a time regardless of threading.
#   2. After every successful call we sleep for INTER_REQUEST_DELAY seconds
#      before releasing the lock, spreading calls across the minute window.
#   3. On 503/429 we apply full-jitter exponential back-off starting from a
#      MINIMUM of 5 s so we give the worker pool time to drain.
#   4. A lock acquisition timeout prevents indefinite blocking when many
#      pipeline tasks are queued simultaneously.

_api_lock: threading.Lock = threading.Lock()

_INTER_REQUEST_DELAY: float = 3.5  # seconds between requests (success path)
try:
    _INTER_REQUEST_DELAY = float(os.getenv("VIGIL_NVIDIA_INTER_REQUEST_DELAY", "3.5"))
except (TypeError, ValueError):
    pass

_MIN_RETRY_DELAY: float = 5.0  # minimum back-off on first retry

# How long (seconds) a call will wait to acquire _api_lock before giving up.
# This prevents an indefinitely-blocking queue when upstream is very slow.
_LOCK_ACQUIRE_TIMEOUT: float = 600.0
try:
    _LOCK_ACQUIRE_TIMEOUT = float(os.getenv("VIGIL_NVIDIA_LOCK_TIMEOUT", "600.0"))
except (TypeError, ValueError):
    pass

# Observability: count requests queued behind the global lock
_requests_waiting: int = 0
_requests_waiting_lock: threading.Lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_base64_image(image_data: str) -> str:
    """Resolve a file URI or local filesystem path to a base64-encoded string.

    If ``image_data`` is already a base64 string (or an ``http(s)://`` URL),
    it is returned unchanged.

    Returns ``None`` if the path cannot be resolved to an existing file,
    allowing callers to skip unresolvable images gracefully.
    """
    try:
        if image_data.startswith("file://"):
            parsed = urlparse(image_data)
            path_str = unquote(parsed.path)
            # On Windows the path looks like /C:/...; strip the leading slash.
            if path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
                path_str = path_str[1:]
            p = Path(path_str)
            if p.is_file():
                return base64.b64encode(p.read_bytes()).decode("utf-8")
            # File URI but no file on disk — signal failure
            logger.warning(
                "NvidiaNIMClient: image file not found at resolved path '%s' (URI: %s)",
                path_str,
                image_data,
            )
            return ""
        p = Path(image_data)
        if p.is_file():
            return base64.b64encode(p.read_bytes()).decode("utf-8")
        # Plain string that is not an existing path — may already be base64
    except Exception:  # noqa: BLE001
        pass
    return image_data


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class NvidiaNIMError(RuntimeError):
    """Raised when the NVIDIA NIM API returns an error or the request fails."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class NvidiaNIMClient(BaseLLMClient):
    """OpenAI-compatible client for NVIDIA NIM hosted endpoints.

    Routes calls to the correct NVIDIA base URL by model type:
    * LLM text calls  → ``integrate.api.nvidia.com/v1``
    * VLM image calls → ``ai.api.nvidia.com/v1``

    A process-wide lock serialises all outbound requests to prevent the
    free-tier worker-pool exhaustion (``ResourceExhausted: Worker local total
    request limit reached``).  A mandatory inter-request delay is observed
    after each successful call to spread load across the RPM window.

    Parameters
    ----------
    api_key:
        Your ``nvapi-*`` key from https://build.nvidia.com.
    vlm_model:
        Model used for image/video-frame analysis (``analyze_image``).
        Defaults to ``meta/llama-3.2-11b-vision-instruct``.
    llm_model:
        Model used for text generation and reasoning (``generate_text``).
        Defaults to ``nvidia/nemotron-3-nano-omni-30b-a3b-reasoning``.
    base_url:
        Deprecated — kept for API compatibility but ignored; each model
        family is routed to its own NVIDIA endpoint automatically.
    timeout_seconds:
        Per-request socket timeout in seconds.
    max_retries:
        Maximum number of retry attempts for transient failures.
    retry_backoff_base:
        Base for exponential back-off calculation (``base ** attempt``).
    """

    def __init__(
        self,
        api_key: str,
        vlm_model: str = DEFAULT_VLM_MODEL,
        llm_model: str = DEFAULT_LLM_MODEL,
        base_url: str = NVIDIA_LLM_BASE_URL,  # kept for compat; auto-routed
        vlm_base_url: str | None = None,
        llm_base_url: str | None = None,
        timeout_seconds: float = 120.0,
        max_retries: int = 5,
        retry_backoff_base: float = 2.0,
    ) -> None:
        if not api_key:
            raise ValueError(
                "NVIDIA NIM API key must be provided. "
                "Get a free key at https://build.nvidia.com."
            )
        self.api_key = api_key.strip()
        self.vlm_model = vlm_model.strip()
        self.llm_model = llm_model.strip()
        # Allow per-instance base URL override (reads from env/config)
        import os as _os
        self._llm_base_url = (
            llm_base_url
            or _os.getenv("NVIDIA_LLM_BASE_URL")
            or NVIDIA_LLM_BASE_URL
        )
        self._vlm_base_url = (
            vlm_base_url
            or _os.getenv("NVIDIA_VLM_BASE_URL")
            or NVIDIA_VLM_BASE_URL
        )
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

        logger.info(
            "NvidiaNIMClient initialised — LLM: %s [%s] | VLM: %s [%s]",
            self.llm_model,
            self._llm_base_url,
            self.vlm_model,
            self._vlm_base_url,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _backoff_delay(self, attempt: int) -> float:
        """Return a jittered exponential back-off delay (full-jitter strategy).

        ``attempt`` is 1-based (first retry = attempt 1).
        Always at least ``_MIN_RETRY_DELAY`` seconds to give the NIM worker
        pool time to drain, never exceeds ``_MAX_BACKOFF_SECONDS``.
        """
        cap = _MAX_BACKOFF_SECONDS
        raw = min(cap, self.retry_backoff_base ** attempt)
        # Clamp lower bound to MIN_RETRY_DELAY so we never hammer a saturated pool
        lower = max(_MIN_RETRY_DELAY, raw * 0.5)
        return random.uniform(lower, raw)  # noqa: S311

    def _call_completions(
        self,
        model: str,
        base_url: str,
        messages: list[dict[str, Any]],
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Send a chat-completions request to a NVIDIA NIM endpoint.

        All calls are serialised through ``_api_lock`` (one in-flight request
        at a time) and separated by ``_INTER_REQUEST_DELAY`` seconds on
        success to prevent ResourceExhausted / worker-pool exhaustion.

        If the lock cannot be acquired within ``_LOCK_ACQUIRE_TIMEOUT``
        seconds, raises ``NvidiaNIMError`` immediately so the queued pipeline
        task can fail gracefully without blocking everything else.

        Args:
            model: The model identifier string (VLM or LLM).
            base_url: The NIM base URL for this model family.
            messages: OpenAI-format message list.
            json_mode: Whether to request structured JSON output.
            temperature: Sampling temperature (lower = more deterministic).
            max_tokens: Maximum tokens to generate in the response.

        Returns:
            Parsed ``LLMResponse`` with content and token counts.

        Raises:
            NvidiaNIMError: On unrecoverable API or network failures, or if
                the lock cannot be acquired within the timeout window.
        """
        url = f"{base_url.rstrip('/')}/chat/completions"

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 0.7,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        data = json.dumps(payload).encode("utf-8")

        last_exc: Exception | None = None
        resp_data: dict[str, Any] = {}

        # Track queue depth for observability
        global _requests_waiting
        with _requests_waiting_lock:
            _requests_waiting += 1
            queue_pos = _requests_waiting

        if queue_pos > 1:
            logger.info(
                "NvidiaNIMClient: request queued — %d request(s) ahead in the "
                "serialisation queue (model=%s). "
                "Estimated wait ≥ %.0fs.",
                queue_pos - 1,
                model,
                (queue_pos - 1) * (_INTER_REQUEST_DELAY + self.timeout_seconds / 4),
            )

        try:
            # Attempt to acquire the global serialisation lock with a timeout
            # so a stuck upstream request cannot block the pipeline indefinitely.
            lock_acquired = _api_lock.acquire(timeout=_LOCK_ACQUIRE_TIMEOUT)
            if not lock_acquired:
                raise NvidiaNIMError(
                    f"NvidiaNIMClient: could not acquire API lock within "
                    f"{_LOCK_ACQUIRE_TIMEOUT:.0f}s — upstream may be stalled. "
                    f"Request for model '{model}' dropped."
                )

            try:
                for attempt in range(self.max_retries + 1):
                    if attempt > 0:
                        delay = self._backoff_delay(attempt)
                        logger.warning(
                            "NvidiaNIMClient: attempt %d/%d failed (%s); retrying in %.1fs",
                            attempt,
                            self.max_retries,
                            last_exc,
                            delay,
                        )
                        time.sleep(delay)

                    req = urllib.request.Request(
                        url,
                        data=data,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {self.api_key}",
                            "Accept": "application/json",
                        },
                        method="POST",
                    )

                    try:
                        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                            resp_data = json.loads(resp.read().decode("utf-8"))
                        # Mandatory cool-down between successful requests
                        if _INTER_REQUEST_DELAY > 0:
                            time.sleep(_INTER_REQUEST_DELAY)
                        break  # success — exit retry loop
                    except urllib.error.HTTPError as exc:
                        err_body = exc.read().decode("utf-8", errors="replace")
                        if exc.code in _RETRYABLE_HTTP_CODES and attempt < self.max_retries:
                            last_exc = RuntimeError(
                                f"HTTP {exc.code}: {exc.reason} — {err_body[:200]}"
                            )
                            continue
                        raise NvidiaNIMError(
                            f"NVIDIA NIM API error {exc.code}: {err_body}"
                        ) from exc
                    except OSError as exc:
                        # Covers socket.timeout, TimeoutError, ConnectionResetError, etc.
                        last_exc = exc
                        if attempt < self.max_retries:
                            continue
                        raise NvidiaNIMError(
                            f"NVIDIA NIM network failure: {exc}"
                        ) from exc
                    except Exception as exc:
                        raise NvidiaNIMError(
                            f"NVIDIA NIM unexpected error: {exc}"
                        ) from exc
            finally:
                _api_lock.release()

        finally:
            with _requests_waiting_lock:
                _requests_waiting -= 1

        # Parse response
        choices = resp_data.get("choices", [])
        if not choices:
            raise NvidiaNIMError(
                f"NVIDIA NIM API returned no completion choices. "
                f"Raw response: {resp_data}"
            )

        content = choices[0].get("message", {}).get("content", "")
        usage = resp_data.get("usage", {})
        return LLMResponse(
            content=content,
            model_name=model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    # ------------------------------------------------------------------
    # Public API — implements BaseLLMClient
    # ------------------------------------------------------------------

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate text or structured JSON via Nemotron 3 Nano 30B A3B (Reasoning).

        Routes to ``integrate.api.nvidia.com`` (LLM endpoint).

        Used for: timeline reconstruction, investigator Q&A, report generation,
        and any reasoning task that does NOT require visual input.

        Args:
            prompt: The user-facing prompt.
            system_instruction: Optional system/role context for the model.
            json_mode: When True, instructs the model to return valid JSON.

        Returns:
            ``LLMResponse`` with the generated text and token usage.
        """
        messages: list[dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        return self._call_completions(
            self.llm_model,
            self._llm_base_url,
            messages,
            json_mode=json_mode,
        )

    def analyze_image(
        self,
        prompt: str,
        image_data: str,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Analyse a video frame or image via NVIDIA Cosmos 3 Nano Reasoner (VLM).

        Routes to ``ai.api.nvidia.com`` (VLM/multimodal endpoint).

        Cosmos 3 Nano Reasoner is designed for structured physical-scene
        understanding: interpreting actions, object interactions, spatial
        relationships, and temporal event sequences from visual input.

        Args:
            prompt: Analytical question or instruction for the scene.
            image_data: Base64-encoded image bytes, a local file path,
                        a ``file://`` URI, or a public ``https://`` URL.
            mime_type: MIME type of the image (default ``image/jpeg``).
            system_instruction: Optional system/role context for the model.
            json_mode: When True, instructs the model to return valid JSON.

        Returns:
            ``LLMResponse`` with the visual analysis and token usage.

        Raises:
            NvidiaNIMError: If the image cannot be resolved or the API fails.
        """
        # Resolve file path / URI → base64; leave http(s) URLs untouched.
        if image_data.startswith("http://") or image_data.startswith("https://"):
            image_url_value = image_data
        else:
            b64 = _ensure_base64_image(image_data)
            if not b64:
                # File path could not be resolved — raise so callers can handle
                raise NvidiaNIMError(
                    f"analyze_image: image file not found or unreadable: '{image_data}'"
                )
            image_url_value = f"data:{mime_type};base64,{b64}"

        messages: list[dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url_value}},
                ],
            }
        )
        return self._call_completions(
            self.vlm_model,
            self._vlm_base_url,
            messages,
            json_mode=json_mode,
        )
