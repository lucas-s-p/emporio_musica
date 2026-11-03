"""Provider-agnostic LLM interface.

Messages and tool specs use the OpenAI-compatible dict format (the same one `ToolRegistry.specs()`
produces), so the agent never imports a provider SDK and swapping providers means writing one
new `LLMClient` implementation.
"""

import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

JsonDict = dict[str, Any]
Message = dict[str, Any]


class LLMError(Exception):
    """Base class for LLM layer failures."""


class LLMConfigError(LLMError):
    """Missing or rejected configuration (no API key, no model, invalid key). Not retryable."""


class LLMUnavailableError(LLMError):
    """Every configured model failed after retries."""

    def __init__(self, failures: Sequence[str]) -> None:
        super().__init__("All models failed: " + "; ".join(failures))
        self.failures = list(failures)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str = ""  # raw JSON string, exactly as the model produced it


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str = ""  # model that actually answered (may be a fallback)
    finish_reason: str | None = None
    usage: Usage = Field(default_factory=Usage)

    def to_message(self) -> Message:
        """The assistant message to append to the history before sending tool results."""
        message: Message = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments or "{}"},
                }
                for call in self.tool_calls
            ]
        return message


def tool_message(tool_call_id: str, content: str | JsonDict) -> Message:
    """A `tool` role message carrying a tool result back to the model."""
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return {"role": "tool", "tool_call_id": tool_call_id, "content": text}


class LLMClient(ABC):
    """What the agent needs from a provider: one chat completion, optionally with tools."""

    @abstractmethod
    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[JsonDict] | None = None,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Return the next assistant turn. Raises LLMConfigError or LLMUnavailableError."""
