import pytest

from emporio.agent.agent import AgentReply, ToolTrace
from emporio.llm.base import Message
from emporio.memory import Transcript, trim_turns


def turn(i: int, with_tool: bool = False) -> list[Message]:
    msgs: list[Message] = [{"role": "user", "content": f"u{i}"}]
    if with_tool:
        msgs += [
            {"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}"}]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": "{}"},
        ]
    msgs.append({"role": "assistant", "content": f"a{i}"})
    return msgs


def history(n: int) -> list[Message]:
    msgs: list[Message] = [{"role": "system", "content": "sys"}]
    for i in range(n):
        msgs += turn(i, with_tool=i % 2 == 0)
    return msgs


def test_trim_keeps_system_and_latest_turns() -> None:
    msgs = history(5)
    assert trim_turns(msgs, 2) == 3
    assert msgs[0]["role"] == "system"
    assert [m["content"] for m in msgs if m["role"] == "user"] == ["u3", "u4"]


def test_trim_never_orphans_tool_messages() -> None:
    msgs = history(6)
    trim_turns(msgs, 3)
    assert msgs[1]["role"] == "user"
    ids_called = {c["id"] for m in msgs for c in m.get("tool_calls", [])}
    ids_answered = {m["tool_call_id"] for m in msgs if m["role"] == "tool"}
    assert ids_called == ids_answered


def test_trim_is_a_noop_when_short_and_validates_limit() -> None:
    msgs = history(2)
    before = list(msgs)
    assert trim_turns(msgs, 5) == 0 and msgs == before
    with pytest.raises(ValueError):
        trim_turns(msgs, 0)


def reply(text: str, *traces: ToolTrace) -> AgentReply:
    return AgentReply(text, list(traces))


def test_transcript_markdown_with_tools() -> None:
    t = Transcript(title="Exemplo")
    trace = ToolTrace("search_products", '{"query": "violão"}', '{"items": []}')
    t.add("tem violão?", reply("Tenho sim.", trace))
    md = t.to_markdown()
    assert md.startswith("# Exemplo")
    assert '`search_products(query="violão")`' in md
    assert "**Cliente:** tem violão?" in md and "**Agente:** Tenho sim." in md
    assert "Ferramentas usadas" not in t.to_markdown(include_tools=False)


def test_transcript_numbers_conversations_only_when_several(tmp_path) -> None:  # type: ignore[no-untyped-def]
    t = Transcript()
    t.add("oi", reply("olá"))
    assert "## Conversa" not in t.to_markdown()
    t.new_conversation()
    t.new_conversation()  # empty conversation is not counted twice
    t.add("oi de novo", reply("olá de novo"))
    md = t.to_markdown()
    assert "## Conversa 1" in md and "## Conversa 2" in md and "## Conversa 3" not in md
    path = tmp_path / "sub" / "c.md"
    t.save(path)
    assert path.read_text(encoding="utf-8") == md
