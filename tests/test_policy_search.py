from datetime import date
from pathlib import Path

import pytest

from emporio.data import Store
from emporio.knowledge import PolicyIndex, load_policy_index
from emporio.services.clock import build_clock
from emporio.tools import ToolRegistry, build_registry

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def index() -> PolicyIndex:
    return load_policy_index(DATA_DIR)


def top(index: PolicyIndex, query: str) -> str:
    hits = index.search(query)
    assert hits, f"no result for {query!r}"
    return hits[0].section.section_id


@pytest.mark.parametrize(
    ("query", "section"),
    [
        ("Me arrependi da minha compra, posso devolver meu pedido?", "4.1"),
        ("quanto tempo tenho pra devolver", "4.1"),
        ("meu violão veio com defeito", "4.2"),
        ("quero trocar por outro modelo", "4.3"),
        ("posso parcelar em 12x?", "3.1"),
        ("vocês vendem cordas de violão?", "1"),
        ("que horas abre sábado", "2"),
        ("como rastrear meu pedido", "5.3"),
        ("como excluir meus dados", "9"),
        ("quero reclamar do atendimento", "7.3"),
        ("telefone da loja", "1.2"),
    ],
)
def test_customer_questions_find_the_right_section(
    index: PolicyIndex, query: str, section: str
) -> None:
    assert top(index, query) == section


def test_restricted_item_is_among_the_results(index: PolicyIndex) -> None:
    sections = [h.section.section_id for h in index.search("posso devolver uma boquilha de sax")]
    assert "4.4" in sections


def test_shipping_to_other_cities_returns_carrier_table(index: PolicyIndex) -> None:
    sections = [h.section.section_id for h in index.search("prazo de entrega para Dourados")]
    assert "5.2" in sections


@pytest.mark.parametrize("query", ["qual a capital da França", "previsão do tempo amanhã", "?? !!"])
def test_off_topic_queries_return_nothing(index: PolicyIndex, query: str) -> None:
    assert index.search(query) == []


def test_accents_and_case_do_not_matter(index: PolicyIndex) -> None:
    assert top(index, "DEVOLUÇÃO") == top(index, "devolucao")


def test_conflicting_sections_carry_a_note(index: PolicyIndex) -> None:
    hits = {h.section.section_id: h for h in index.search("formas de pagamento parcela mínima", 5)}
    assert hits["3"].note and "get_payment_options" in hits["3"].note
    assert hits["3.1"].note is None


def test_limit_is_respected(index: PolicyIndex) -> None:
    assert len(index.search("devolução troca garantia defeito", 2)) <= 2


# --- tool -----------------------------------------------------------------------------------


@pytest.fixture
def registry(store: Store, index: PolicyIndex) -> ToolRegistry:
    return build_registry(store, build_clock(date(2026, 11, 3)), policies=index)


def test_policy_tool_is_optional(store: Store) -> None:
    assert "search_policies" not in build_registry(store, build_clock(date(2026, 11, 3))).names


def test_policy_tool_is_registered_with_a_valid_spec(registry: ToolRegistry) -> None:
    assert "search_policies" in registry.names
    spec = next(s for s in registry.specs() if s["function"]["name"] == "search_policies")
    assert spec["function"]["parameters"]["required"] == ["query"]


def test_policy_tool_result(registry: ToolRegistry) -> None:
    result = registry.execute("search_policies", {"query": "direito de arrependimento"})
    first = result["results"][0]
    assert first["section"] == "4.1" and "7 (sete) dias corridos" in first["text"]
    assert first["page"] == 4 and "Versão" not in first["text"]
    assert result["source"].startswith("Manual de Políticas")


def test_policy_tool_includes_notes(registry: ToolRegistry) -> None:
    result = registry.execute("search_policies", {"query": "whatsapp da loja"})
    assert any("get_store_info" in r.get("note", "") for r in result["results"])


def test_policy_tool_refuses_to_guess(registry: ToolRegistry) -> None:
    result = registry.execute("search_policies", {"query": "previsão do tempo amanhã"})
    assert result["error"] == "NOT_IN_POLICIES" and result["results"] == []


def test_policy_tool_validates_input(registry: ToolRegistry) -> None:
    assert registry.execute("search_policies", {"query": "a"})["error"] == "INVALID_ARGUMENTS"
