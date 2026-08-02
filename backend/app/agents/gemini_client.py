"""
gemini_client.py — Centralized, rate-limit-safe Gemini LLM helper.

Performance optimizations:
  - Uses deque instead of list for O(1) pop from left (rate-limit timestamps).
  - Thread-safe rate limit check using a lock for concurrent call safety.
  - Caches LLM instances per (model, timeout) to avoid recreating objects.
  - Async version uses asyncio.to_thread to keep FastAPI event loop free.
  - Model fallback chain: gemini-2.0-flash → gemini-1.5-flash → gemini-1.5-flash-8b.
  - Exponential back-off on 429 / ResourceExhausted so we never crash the pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe soft rate-limit guard: never fire more than MAX_RPM calls/min
# ---------------------------------------------------------------------------
_CALL_TIMESTAMPS: deque[float] = deque()  # O(1) popleft vs O(n) list.pop(0)
_RATE_LOCK = threading.Lock()
MAX_RPM = 30  # Support higher throughput with fallback models


def _check_rate_limit() -> None:
    """Remove timestamps older than 60 s; sleep if we're at the cap."""
    with _RATE_LOCK:
        now = time.monotonic()
        # Purge expired entries — O(1) per pop with deque
        while _CALL_TIMESTAMPS and now - _CALL_TIMESTAMPS[0] > 60.0:
            _CALL_TIMESTAMPS.popleft()
        if len(_CALL_TIMESTAMPS) >= MAX_RPM:
            wait = 61.0 - (now - _CALL_TIMESTAMPS[0])
            if wait > 0:
                logger.info("GeminiClient: soft rate-limit — sleeping %.1fs", wait)
                time.sleep(wait)
        _CALL_TIMESTAMPS.append(time.monotonic())


# ---------------------------------------------------------------------------
# Model fallback chain (fastest first)
# ---------------------------------------------------------------------------
_MODEL_CHAIN = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

# LLM instance cache: (model, timeout) → ChatGoogleGenerativeAI
# Avoids creating new SDK objects for every call
_LLM_CACHE: dict[tuple[str, str, int], ChatGoogleGenerativeAI] = {}
_LLM_CACHE_LOCK = threading.Lock()


def _get_llm(model: str, api_key: str, timeout: int = 20) -> ChatGoogleGenerativeAI:
    """Return a cached LLM instance, creating it only once per (model, api_key_hash, timeout)."""
    # Use first 8 chars of key as cache discriminator (never log full key)
    key_hint = api_key[:8] if api_key else ""
    cache_key = (model, key_hint, timeout)
    with _LLM_CACHE_LOCK:
        if cache_key not in _LLM_CACHE:
            _LLM_CACHE[cache_key] = ChatGoogleGenerativeAI(
                model=model,
                api_key=SecretStr(api_key),
                max_retries=0,       # We handle retries ourselves
                timeout=timeout,
            )
        return _LLM_CACHE[cache_key]


def call_gemini(
    messages: Sequence[BaseMessage],
    *,
    timeout: int = 20,
    tools: list[Any] | None = None,
) -> str:
    """
    Synchronous Gemini call with:
      - thread-safe soft rate-limit guard
      - model fallback chain (flash → flash-lite → flash-8b)
      - up to 2 retries per model on 429 / timeout
    Returns the response text, or raises RuntimeError if all models fail.
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    last_exc: Exception | None = None

    for model in _MODEL_CHAIN:
        for attempt in range(2):
            try:
                _check_rate_limit()
                llm = _get_llm(model, api_key, timeout=timeout)
                if tools:
                    # Bind tools creates a new wrapper — don't cache this
                    llm = llm.bind_tools(tools)  # type: ignore[assignment]
                response = llm.invoke(messages)
                content = str(response.content) if response.content else ""
                if content.strip():
                    logger.info(
                        "GeminiClient: success model=%s attempt=%d len=%d",
                        model, attempt + 1, len(content),
                    )
                    return content
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                is_rate_limit = any(
                    k in err_str for k in ("429", "resource_exhausted", "quota", "rate")
                )
                if is_rate_limit:
                    sleep_for = 1 * (attempt + 1)  # Minimal sleep: 1s, 2s
                    logger.warning(
                        "GeminiClient: 429 on %s attempt=%d — sleeping %ds",
                        model, attempt + 1, sleep_for,
                    )
                    time.sleep(sleep_for)
                else:
                    logger.warning(
                        "GeminiClient: error on %s attempt=%d: %s",
                        model, attempt + 1, exc,
                    )
                    break  # Non-rate-limit error → try next model immediately

    raise RuntimeError(f"All Gemini models failed. Last error: {last_exc}")


async def call_gemini_async(
    messages: Sequence[BaseMessage],
    *,
    timeout: int = 20,
    tools: list[Any] | None = None,
) -> str:
    """Async wrapper — runs call_gemini in a thread to keep FastAPI's event loop free."""
    return await asyncio.to_thread(call_gemini, messages, timeout=timeout, tools=tools)
