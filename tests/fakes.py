"""Test doubles shared by several test modules (imported as `fakes`)."""

import json
from collections.abc import Sequence

from emporio.llm.base import (
    JsonDict,
    LLMClient,
    LLMError,
    LLMResponse,
    Message,
    ToolCall,
)


class ScriptedLLM(LLMClient):
    """Returns canned responses in order and records what the agent sent."""

    def __init__(self, *steps: LLMResponse | LLMError) -> None:
        self._steps = list(steps)
        self.seen: list[list[Message]] = []

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[JsonDict] | None = None,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.seen.append([dict(m) for m in messages])
        step = self._steps.pop(0)
        if isinstance(step, LLMError):
            raise step
        return step


def say(text: str, model: str = "fake") -> LLMResponse:
    return LLMResponse(content=text, model=model)


def call(name: str, arguments: JsonDict | str = "{}", call_id: str = "c1") -> LLMResponse:
    args = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return LLMResponse(tool_calls=[ToolCall(id=call_id, name=name, arguments=args)], model="fake")
