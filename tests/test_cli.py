from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import ScriptedLLM, say

from emporio.agent import Agent
from emporio.interfaces.cli import main, run_chat
from emporio.llm.base import LLMResponse, ToolCall
from emporio.memory import Transcript
from emporio.tools.base import ToolRegistry


def make_agents(*llms: ScriptedLLM) -> Iterator[Agent]:
    for llm in llms:
        yield Agent(llm, ToolRegistry([]), "sys")


def drive(inputs: list[str], *llms: ScriptedLLM, **kwargs) -> list[str]:  # type: ignore[no-untyped-def]
    out: list[str] = []
    feed = iter(inputs)
    agents = make_agents(*llms)

    def read(_: str) -> str:
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    run_chat(lambda: next(agents), read=read, write=out.append, **kwargs)
    return out


def test_chat_answers_and_exits_on_eof() -> None:
    out = drive(["oi", ""], ScriptedLLM(say("Olá!")))
    assert any("Agente: Olá!" in line for line in out)


def test_sair_stops_before_reading_more() -> None:
    llm = ScriptedLLM(say("não deveria chamar"))
    out = drive(["/sair", "oi"], llm)
    assert not any("Agente:" in line for line in out) and llm.seen == []


def test_novo_starts_a_fresh_agent_and_transcript_conversation() -> None:
    first, second = ScriptedLLM(say("um")), ScriptedLLM(say("dois"))
    t = Transcript()
    drive(["a", "/novo", "b"], first, second, transcript=t)
    assert len(first.seen[0]) == 2 and len(second.seen[0]) == 2  # system + user only
    assert [x.conversation for x in t.turns] == [1, 2]


def test_tools_toggle_shows_traces() -> None:
    llm = ScriptedLLM(
        LLMResponse(tool_calls=[ToolCall(id="c", name="x", arguments="{}")]), say("pronto")
    )
    out = drive(["/ferramentas", "oi"], llm)
    assert any("[ferramenta] x(" in line and "UNKNOWN_TOOL" in line for line in out)


def test_transcript_saved_after_each_turn(tmp_path: Path) -> None:
    path = tmp_path / "c.md"
    drive(["oi"], ScriptedLLM(say("Olá!")), transcript=Transcript(), save_path=path)
    assert "**Agente:** Olá!" in path.read_text(encoding="utf-8")


def test_main_without_api_key_explains_and_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    for var in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"):
        monkeypatch.delenv(var, raising=False)
    assert main([]) == 2
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err
