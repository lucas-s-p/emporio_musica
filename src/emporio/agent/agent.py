"""The conversation loop: model turn, tool execution, model turn, until a text answer."""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from emporio.llm.base import LLMClient, LLMError, Message, tool_message
from emporio.services.store import STORE_INFO
from emporio.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

OUTAGE_MESSAGE = (
    "Desculpe, estou com uma instabilidade agora e não consegui processar sua mensagem. "
    f"Tente de novo em instantes ou fale com a loja: {STORE_INFO.phone} ou {STORE_INFO.email}."
)
GIVE_UP_MESSAGE = (
    "Desculpe, não consegui concluir essa consulta. Pode reformular o pedido? "
    f"Se preferir, a loja atende pelo {STORE_INFO.phone}."
)


@dataclass(frozen=True)
class ToolTrace:
    name: str
    arguments: str
    result: str


@dataclass
class AgentReply:
    text: str
    tool_traces: list[ToolTrace] = field(default_factory=list)
    model: str = ""
    degraded: bool = False  # True when the text is a canned fallback, not a model answer


def clean_text(text: str | None) -> str:
    """Drop reasoning blocks some models leak into the answer."""
    return _THINK_BLOCK.sub("", text or "").strip()


class Agent:
    """One conversation. The history lives in self.messages and is the only state."""

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        system_prompt: str,
        *,
        max_tool_rounds: int = 6,
        temperature: float = 0.2,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._max_rounds = max_tool_rounds
        self._temperature = temperature
        self.messages: list[Message] = [{"role": "system", "content": system_prompt}]

    def respond(self, user_text: str) -> AgentReply:
        checkpoint = len(self.messages)
        self.messages.append({"role": "user", "content": user_text})
        traces: list[ToolTrace] = []
        specs = self._registry.specs()
        model = ""
        try:
            for _ in range(self._max_rounds + 1):
                out = self._llm.complete(
                    self.messages, specs, temperature=self._temperature, max_tokens=None
                )
                model = out.model
                if not out.tool_calls:
                    text = clean_text(out.content)
                    if not text:
                        break
                    self.messages.append({"role": "assistant", "content": text})
                    return AgentReply(text, traces, model)
                self.messages.append(out.to_message())
                for call in out.tool_calls:
                    result = self._registry.execute_json(call.name, call.arguments)
                    traces.append(ToolTrace(call.name, call.arguments, result))
                    self.messages.append(tool_message(call.id, result))
        except LLMError as exc:
            logger.error("LLM unavailable: %s", exc)
            return self._abort(checkpoint, OUTAGE_MESSAGE, traces, model)
        logger.warning("Gave up after %d tool rounds", self._max_rounds)
        return self._abort(checkpoint, GIVE_UP_MESSAGE, traces, model)

    def _abort(
        self, checkpoint: int, text: str, traces: Sequence[ToolTrace], model: str
    ) -> AgentReply:
        """Roll the half-finished turn back, so the next message starts from a valid history."""
        del self.messages[checkpoint:]
        self.messages.append({"role": "user", "content": "(mensagem não processada)"})
        self.messages.append({"role": "assistant", "content": text})
        return AgentReply(text, list(traces), model, degraded=True)
