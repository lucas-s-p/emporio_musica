"""Records conversations and renders them as Markdown (used to produce examples/)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # agent imports memory.history, so a runtime import here would be circular
    from emporio.agent.agent import AgentReply, ToolTrace

_RESULT_PREVIEW = 300


@dataclass
class TranscriptTurn:
    conversation: int
    user: str
    reply: AgentReply


@dataclass
class Transcript:
    title: str = "Conversa com o agente"
    subtitle: str = ""  # one italic line under the title (date, model, how it was generated)
    turns: list[TranscriptTurn] = field(default_factory=list)
    _conversation: int = 1

    def new_conversation(self) -> None:
        if self.turns and self.turns[-1].conversation == self._conversation:
            self._conversation += 1

    def add(self, user: str, reply: AgentReply) -> None:
        self.turns.append(TranscriptTurn(self._conversation, user, reply))

    def to_markdown(self, *, include_tools: bool = True) -> str:
        lines = [f"# {self.title}", ""]
        if self.subtitle:
            lines += [f"_{self.subtitle}_", ""]
        current = 0
        for turn in self.turns:
            if turn.conversation != current:
                current = turn.conversation
                if len(self._numbers()) > 1:
                    lines += [f"## Conversa {current}", ""]
            lines += [f"**Cliente:** {turn.user}", ""]
            if include_tools and turn.reply.tool_traces:
                lines += [_render_tools(turn.reply.tool_traces), ""]
            lines += [f"**Agente:** {turn.reply.text}", ""]
        return "\n".join(lines).rstrip() + "\n"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")

    def _numbers(self) -> set[int]:
        return {t.conversation for t in self.turns}


def _render_tools(traces: list[ToolTrace]) -> str:
    rows = []
    for t in traces:
        result = (
            t.result if len(t.result) <= _RESULT_PREVIEW else t.result[:_RESULT_PREVIEW] + "..."
        )
        args = _compact(t.arguments)
        rows.append(f"- `{t.name}({args})` devolveu `{result}`")
    return "Ferramentas usadas:\n" + "\n".join(rows)


def _compact(arguments: str) -> str:
    try:
        data = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return arguments
    if not isinstance(data, dict):
        return arguments
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in data.items())
