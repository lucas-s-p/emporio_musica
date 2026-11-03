import json
import re
from datetime import date
from pathlib import Path

import pytest
from fakes import ScriptedLLM, call, say

from emporio.agent import Agent, build_agent, build_system_prompt
from emporio.agent.agent import GIVE_UP_MESSAGE, OUTAGE_MESSAGE
from emporio.data import Store
from emporio.knowledge import PolicyIndex, load_policy_index
from emporio.llm.base import LLMClient, LLMUnavailableError
from emporio.services.clock import build_clock
from emporio.tools import build_registry

ROOT = Path(__file__).resolve().parents[1]
CLOCK = build_clock(date(2026, 11, 2))  # a Monday


@pytest.fixture(scope="module")
def policies() -> PolicyIndex:
    return load_policy_index(ROOT / "data")


def make_agent(llm: LLMClient, store: Store, policies: PolicyIndex, **kwargs: int) -> Agent:
    return Agent(
        llm,
        build_registry(store, CLOCK, policies=policies),
        build_system_prompt(CLOCK, ROOT),
        **kwargs,
    )


def test_system_prompt_injects_today_and_has_no_placeholders() -> None:
    prompt = build_system_prompt(CLOCK, ROOT)
    assert "02/11/2026" in prompt and "segunda-feira" in prompt
    assert "{today}" not in prompt and "{weekday}" not in prompt


def test_persona_only_mentions_tools_that_exist(store: Store, policies: PolicyIndex) -> None:
    names = set(build_registry(store, CLOCK, policies=policies).names)
    mentioned = set(re.findall(r"`([a-z_]+)`", build_system_prompt(CLOCK, ROOT)))
    tool_like = {
        m for m in mentioned if m.startswith(("get_", "search_", "verify_", "check_", "estimate_"))
    }
    assert tool_like and tool_like <= names


def test_persona_has_the_required_guardrails() -> None:
    prompt = build_system_prompt(CLOCK, ROOT).lower()
    for needle in ("acessórios", "fora disso", "nunca invente", "verificad", "não use travessão"):
        assert needle in prompt


def test_plain_answer_is_added_to_history(store: Store, policies: PolicyIndex) -> None:
    agent = make_agent(ScriptedLLM(say("Olá! Como posso ajudar?")), store, policies)
    reply = agent.respond("oi")
    assert reply.text == "Olá! Como posso ajudar?" and not reply.degraded
    assert [m["role"] for m in agent.messages] == ["system", "user", "assistant"]


def test_tool_round_feeds_result_back_to_the_model(store: Store, policies: PolicyIndex) -> None:
    llm = ScriptedLLM(call("get_store_info"), say("Abrimos às 9h."))
    agent = make_agent(llm, store, policies)
    reply = agent.respond("que horas abrem hoje?")
    assert reply.text == "Abrimos às 9h."
    assert [t.name for t in reply.tool_traces] == ["get_store_info"]
    second_turn = llm.seen[1]
    assert second_turn[-2]["role"] == "assistant" and second_turn[-2]["tool_calls"]
    tool_msg = second_turn[-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    assert "2026-11-02" in tool_msg["content"]  # injected clock reached the tool


def test_order_data_is_blocked_before_verification(store: Store, policies: PolicyIndex) -> None:
    llm = ScriptedLLM(call("get_order_status", {"order_id": 1}), say("Preciso verificar você."))
    agent = make_agent(llm, store, policies)
    agent.respond("cadê meu pedido 1?")
    result = json.loads(llm.seen[1][-1]["content"])
    assert result["error"] == "NOT_VERIFIED"


def test_invalid_tool_arguments_do_not_crash(store: Store, policies: PolicyIndex) -> None:
    llm = ScriptedLLM(call("search_products", "{not json"), call("nope"), say("Ok."))
    reply = make_agent(llm, store, policies).respond("violão")
    assert reply.text == "Ok."
    errors = [json.loads(t.result)["error"] for t in reply.tool_traces]
    assert errors == ["INVALID_ARGUMENTS", "UNKNOWN_TOOL"]


def test_think_blocks_are_stripped(store: Store, policies: PolicyIndex) -> None:
    agent = make_agent(ScriptedLLM(say("<think>hmm\nplan</think>Oi!")), store, policies)
    assert agent.respond("oi").text == "Oi!"


def test_tool_loop_is_bounded_and_history_rolled_back(store: Store, policies: PolicyIndex) -> None:
    llm = ScriptedLLM(*[call("get_store_info", call_id=f"c{i}") for i in range(10)])
    agent = make_agent(llm, store, policies, max_tool_rounds=2)
    reply = agent.respond("oi")
    assert reply.degraded and reply.text == GIVE_UP_MESSAGE
    assert len(llm.seen) == 3  # 2 tool rounds + the last attempt
    assert not any(m["role"] == "tool" for m in agent.messages)
    assert [m["role"] for m in agent.messages] == ["system", "user", "assistant"]


def test_outage_gives_canned_answer_with_store_contact(store: Store, policies: PolicyIndex) -> None:
    llm = ScriptedLLM(LLMUnavailableError(["a: HTTP 429"]), say("Voltei!"))
    agent = make_agent(llm, store, policies)
    reply = agent.respond("oi")
    assert reply.degraded and reply.text == OUTAGE_MESSAGE and "3341-4444" in reply.text
    assert agent.respond("e agora?").text == "Voltei!"  # conversation survives
    roles = [m["role"] for m in agent.messages]
    assert roles == ["system", "user", "assistant", "user", "assistant"]


def test_empty_model_answer_is_not_sent_to_the_customer(
    store: Store, policies: PolicyIndex
) -> None:
    reply = make_agent(ScriptedLLM(say("<think>x</think>")), store, policies).respond("oi")
    assert reply.degraded


def test_each_conversation_has_its_own_identity(store: Store, policies: PolicyIndex) -> None:
    a = build_agent(ScriptedLLM(), store, CLOCK, policies, ROOT)
    b = build_agent(ScriptedLLM(), store, CLOCK, policies, ROOT)
    assert a._registry is not b._registry


def test_history_is_bounded_but_identity_survives(store: Store, policies: PolicyIndex) -> None:
    llm = ScriptedLLM(*[say(f"r{i}") for i in range(5)])
    agent = Agent(
        llm,
        build_registry(store, CLOCK, policies=policies),
        "sys",
        max_history_turns=2,
    )
    for i in range(5):
        agent.respond(f"u{i}")
    users = [m["content"] for m in agent.messages if m["role"] == "user"]
    assert users == ["u2", "u3", "u4"]  # 2 previous turns + the latest
    assert agent.messages[0]["role"] == "system"
