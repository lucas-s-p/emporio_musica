from types import SimpleNamespace
from typing import Any

import openai
import pytest

from emporio.config import Settings
from emporio.llm import (
    LLMConfigError,
    LLMUnavailableError,
    OpenRouterClient,
    build_llm,
    tool_message,
)

# The SDK only reads .request, .status_code and .headers from the response, so duck-typed fakes
# keep these tests independent of the HTTP library the installed SDK version uses (httpx/httpx2).
REQUEST: Any = SimpleNamespace(method="POST", url="https://openrouter.ai/api/v1/chat/completions")


def status_error(code: int, headers: dict[str, str] | None = None) -> openai.APIStatusError:
    response: Any = SimpleNamespace(request=REQUEST, status_code=code, headers=headers or {})
    cls = {
        401: openai.AuthenticationError,
        404: openai.NotFoundError,
        429: openai.RateLimitError,
    }.get(code, openai.APIStatusError)
    return cls("boom", response=response, body=None)


def completion(
    content: str | None = "oi", tool_calls: list[Any] | None = None, model: str = "m"
) -> Any:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        model=model,
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2),
    )


class FakeSDK:
    """Plays a script per model: each item is an exception to raise or a value to return."""

    def __init__(self, script: dict[str, list[Any]]) -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        step = self.script[kwargs["model"]].pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def make(
    script: dict[str, list[Any]], **kwargs: Any
) -> tuple[OpenRouterClient, FakeSDK, list[float]]:
    sdk = FakeSDK(script)
    sleeps: list[float] = []
    client = OpenRouterClient(
        "key", list(script), client=sdk, sleep=sleeps.append, jitter=lambda: 0.0, **kwargs
    )
    return client, sdk, sleeps


MSGS = [{"role": "user", "content": "oi"}]


def test_returns_content_and_usage() -> None:
    client, _, _ = make({"a": [completion("olá", model="a")]})
    out = client.complete(MSGS)
    assert out.content == "olá"
    assert out.model == "a"
    assert (out.usage.prompt_tokens, out.usage.completion_tokens) == (5, 2)


def test_parses_tool_calls_and_builds_assistant_message() -> None:
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="get_x", arguments='{"a": 1}'))
    client, sdk, _ = make({"a": [completion(None, [call])]})
    out = client.complete(MSGS, tools=[{"type": "function"}])
    assert out.tool_calls[0].name == "get_x"
    assert sdk.calls[0]["tool_choice"] == "auto"
    msg = out.to_message()
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    assert tool_message("c1", {"ok": True})["content"] == '{"ok": true}'


def test_no_tools_means_no_tool_choice() -> None:
    client, sdk, _ = make({"a": [completion()]})
    client.complete(MSGS)
    assert "tools" not in sdk.calls[0] and "tool_choice" not in sdk.calls[0]


def test_retries_transient_with_exponential_backoff() -> None:
    client, sdk, sleeps = make({"a": [status_error(503), status_error(429), completion()]})
    assert client.complete(MSGS).content == "oi"
    assert len(sdk.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_retry_after_header_is_respected_and_capped() -> None:
    client, _, sleeps = make(
        {
            "a": [
                status_error(429, {"retry-after": "7"}),
                status_error(429, {"retry-after": "999"}),
                completion(),
            ]
        }
    )
    client.complete(MSGS)
    assert sleeps == [7.0, 20.0]


def test_falls_back_after_retries_exhausted() -> None:
    client, sdk, _ = make({"a": [status_error(429)] * 3, "b": [completion(model="b")]})
    out = client.complete(MSGS)
    assert out.model == "b"
    assert [c["model"] for c in sdk.calls] == ["a", "a", "a", "b"]


def test_non_transient_error_skips_to_next_model_without_retry() -> None:
    client, sdk, sleeps = make({"a": [status_error(404)], "b": [completion()]})
    client.complete(MSGS)
    assert [c["model"] for c in sdk.calls] == ["a", "b"]
    assert sleeps == []


def test_empty_and_choiceless_responses_are_retried() -> None:
    choiceless = SimpleNamespace(choices=None)
    client, _, sleeps = make({"a": [choiceless, completion(None), completion("ok")]})
    assert client.complete(MSGS).content == "ok"
    assert len(sleeps) == 2


def test_connection_errors_are_transient() -> None:
    err = openai.APIConnectionError(request=REQUEST)
    client, _, sleeps = make({"a": [err, completion()]})
    client.complete(MSGS)
    assert len(sleeps) == 1


def test_auth_error_aborts_without_trying_fallbacks() -> None:
    client, sdk, _ = make({"a": [status_error(401)], "b": [completion()]})
    with pytest.raises(LLMConfigError):
        client.complete(MSGS)
    assert len(sdk.calls) == 1


def test_all_models_failing_reports_each_failure() -> None:
    client, _, _ = make({"a": [status_error(404)], "b": [status_error(404)]})
    with pytest.raises(LLMUnavailableError) as info:
        client.complete(MSGS)
    assert len(info.value.failures) == 2
    assert info.value.failures[0].startswith("a: HTTP 404")


def test_requires_key_and_model() -> None:
    with pytest.raises(LLMConfigError):
        OpenRouterClient(None, ["a"])
    with pytest.raises(LLMConfigError):
        OpenRouterClient("key", [])


def test_model_chain_from_settings_dedupes() -> None:
    settings = Settings(
        _env_file=None,
        openrouter_api_key="k",
        openrouter_model="a",
        openrouter_fallback_models="b, a ,c",
    )
    assert settings.model_chain == ["a", "b", "c"]
    assert build_llm(settings).models == ["a", "b", "c"]  # type: ignore[attr-defined]
