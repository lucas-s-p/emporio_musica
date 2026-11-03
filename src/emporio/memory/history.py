"""Bounds the message history without ever breaking a tool call from its results."""

from emporio.llm.base import Message


def trim_turns(messages: list[Message], max_turns: int) -> int:
    """Drop the oldest turns in place, keeping the system prompt. Returns how many were dropped.

    A turn starts at a user message and runs to the next one, so an assistant message with
    tool calls is never separated from its `tool` results (providers reject that).
    """
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1")
    starts = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    excess = len(starts) - max_turns
    if excess <= 0:
        return 0
    first_kept = starts[excess]
    first_turn = starts[0]
    del messages[first_turn:first_kept]
    return excess
