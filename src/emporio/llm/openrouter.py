"""OpenRouter implementation (OpenAI-compatible API) with retry, backoff and model fallback.

Free models are rate limited and come and go, so the client walks an ordered model list:
for each model it retries transient errors with exponential backoff, then moves to the next.
Auth errors abort at once (a different model will not fix a bad key).
"""

import logging
import random
import time
from collections.abc import Callable, Sequence
from typing import Any

import openai
from openai import OpenAI

from emporio.llm.base import (
    JsonDict,
    LLMClient,
    LLMConfigError,
    LLMResponse,
    LLMUnavailableError,
    Message,
    ToolCall,
    Usage,
)

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class _Transient(Exception):
    """Raised internally for an empty or malformed 200 response, worth one more try."""


def _status(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    return value if isinstance(value, int) else None


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, _Transient | openai.APIConnectionError):  # includes timeouts
        return True
    return isinstance(exc, openai.APIStatusError) and _status(exc) in _TRANSIENT_STATUS


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    header = response.headers.get("retry-after") if response is not None else None
    try:
        return float(header) if header is not None else None
    except ValueError:
        return None


class OpenRouterClient(LLMClient):
    def __init__(
        self,
        api_key: str | None,
        models: Sequence[str],
        *,
        base_url: str = OPENROUTER_BASE_URL,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 20.0,
        timeout: float = 60.0,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        monotonic: Callable[[], float] = time.monotonic,
        cooldown: float = 60.0,
    ) -> None:
        if not api_key and client is None:
            raise LLMConfigError("OPENROUTER_API_KEY is not set (see .env.example)")
        chain = list(dict.fromkeys(m for m in models if m))  # dedupe, keep order
        if not chain:
            raise LLMConfigError("No model configured: set OPENROUTER_MODEL (see .env.example)")
        self.models = chain
        self._max_retries = max(1, max_retries)
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep = sleep
        self._jitter = jitter
        self._monotonic = monotonic
        self._cooldown = cooldown
        self._dead: set[str] = set()  # 400/404/422: the model cannot serve this request at all
        self._resting: dict[str, float] = {}  # rate limited or down: skip until this instant
        # The SDK's own retries are off: retrying here keeps one policy and testable timing.
        self._client = client or OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
            default_headers={"X-Title": "Emporio da Musica agent"},
        )

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[JsonDict] | None = None,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        failures: list[str] = []
        for model in self._candidates():
            try:
                return self._complete_with_retry(model, messages, tools, temperature, max_tokens)
            except openai.AuthenticationError as exc:
                raise LLMConfigError(f"OpenRouter rejected the API key: {exc}") from exc
            except openai.PermissionDeniedError as exc:
                raise LLMConfigError(f"OpenRouter denied access: {exc}") from exc
            except Exception as exc:  # next model: 400/404 here usually means "no tool support"
                failures.append(f"{model}: {self._describe(exc)}")
                self._penalize(model, exc)
        raise LLMUnavailableError(failures)

    def _candidates(self) -> list[str]:
        """Models worth trying now. Never empty: if everything is penalized, try them all again."""
        now = self._monotonic()
        usable = [m for m in self.models if m not in self._dead]
        ready = [m for m in usable if self._resting.get(m, 0.0) <= now]
        return ready or usable or list(self.models)

    def _penalize(self, model: str, exc: Exception) -> None:
        """Remember a failure, so the next calls do not pay for the same dead end again."""
        status = _status(exc)
        if status in (400, 404, 422):
            fresh = model not in self._dead
            self._dead.add(model)
            note = "skipping it for the rest of the session"
        elif _is_transient(exc):
            fresh = self._resting.get(model, 0.0) <= self._monotonic()
            self._resting[model] = self._monotonic() + self._cooldown
            note = f"resting it for {self._cooldown:.0f}s"
        else:  # e.g. an empty answer worth one more try on the next call
            fresh, note = True, "trying the next model"
        level = logging.WARNING if fresh else logging.INFO
        logger.log(level, "Model %s failed (%s), %s", model, self._describe(exc), note)

    def _complete_with_retry(
        self,
        model: str,
        messages: Sequence[Message],
        tools: Sequence[JsonDict] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> LLMResponse:
        for attempt in range(self._max_retries):
            try:
                return self._call(model, messages, tools, temperature, max_tokens)
            except Exception as exc:
                last_attempt = attempt == self._max_retries - 1
                if not _is_transient(exc) or last_attempt:
                    raise
                delay = self._delay(attempt, exc)
                logger.info("Model %s: %s, retry in %.1fs", model, self._describe(exc), delay)
                self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    def _delay(self, attempt: int, exc: Exception) -> float:
        hinted = _retry_after(exc)
        if hinted is not None:
            return min(max(hinted, 0.0), self._max_delay)
        backoff = self._base_delay * (2**attempt)
        return min(backoff + self._jitter() * self._base_delay, self._max_delay)

    def _call(
        self,
        model: str,
        messages: Sequence[Message],
        tools: Sequence[JsonDict] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = list(tools)
            kwargs["tool_choice"] = "auto"
        completion = self._client.chat.completions.create(**kwargs)
        return self._parse(completion, model)

    @staticmethod
    def _parse(completion: Any, requested: str) -> LLMResponse:
        # OpenRouter may answer 200 with an `error` body and no choices (upstream provider failure).
        choices = getattr(completion, "choices", None)
        if not choices:
            raise _Transient("response without choices")
        choice = choices[0]
        message = choice.message
        calls = [
            ToolCall(
                id=c.id or f"call_{i}", name=c.function.name, arguments=c.function.arguments or ""
            )
            for i, c in enumerate(message.tool_calls or [])
        ]
        content = message.content or None
        if content is None and not calls:
            raise _Transient("empty response")
        usage = getattr(completion, "usage", None)
        return LLMResponse(
            content=content,
            tool_calls=calls,
            model=getattr(completion, "model", None) or requested,
            finish_reason=getattr(choice, "finish_reason", None),
            usage=Usage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            ),
        )

    @staticmethod
    def _describe(exc: Exception) -> str:
        status = _status(exc)
        return f"HTTP {status}" if status else f"{type(exc).__name__}: {exc}"
