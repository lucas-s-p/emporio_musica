from pathlib import Path

import pytest

from emporio.knowledge import PolicyIndex, load_policy_index, parse_policies, policy_pdf_path
from emporio.knowledge.errata import ERRATA

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def sections():  # type: ignore[no-untyped-def]
    return parse_policies(policy_pdf_path(DATA_DIR))


@pytest.fixture(scope="module")
def index() -> PolicyIndex:
    return load_policy_index(DATA_DIR)


def test_every_numbered_section_is_found(sections) -> None:  # type: ignore[no-untyped-def]
    ids = {s.section_id for s in sections}
    expected = {"1", "1.1", "1.2", "2", "3", "3.1", "4", "4.1", "4.2", "4.3", "4.4", "5.1"}
    expected |= {"5.2", "5.3", "6.1", "6.2", "7", "7.1", "7.2", "7.3", "8.1", "8.2", "8.3", "9"}
    expected |= {"10"}
    assert expected <= ids


def test_cover_and_page_furniture_are_dropped(sections) -> None:  # type: ignore[no-untyped-def]
    text = "\n".join(s.text for s in sections)
    assert "MANUAL DE POLÍTICAS" not in text and "Versão 2.1" not in text
    assert "Página " not in text and "Manual de Políticas e Procedimentos" not in text
    assert "\u200b" not in text


def test_table_cells_are_not_taken_as_headings(sections) -> None:  # type: ignore[no-untyped-def]
    shipping = next(s for s in sections if s.section_id == "5.2")
    assert "5 a 12 dias úteis" in shipping.text and "2 a 5 dias úteis" in shipping.text
    assert [s.section_id for s in sections].count("5.2") == 1


def test_key_facts_survive_extraction(index: PolicyIndex) -> None:
    def text(section_id: str) -> str:
        section = index.get(section_id)
        assert section is not None
        return section.text

    assert "7 (sete) dias corridos" in text("4.1")
    assert "30 (trinta) dias corridos" in text("4.2")
    assert "Boquilhas" in text("4.4")
    assert "taxa fixa de R$ 35,00" in text("5.1")
    assert "R$ 80,00" in text("3.1") and "R$ 2.000,00" in text("3.1")
    assert "Sábado\n09:00 às 13:00" in text("2")
    assert "90" in text("8.1")


def test_wrapped_bullets_are_joined(index: PolicyIndex) -> None:
    section = index.get("3.1")
    assert section is not None
    assert "(exceto abaixo de R$ 50,00)." in section.text


def test_heading_path_is_kept(index: PolicyIndex) -> None:
    section = index.get("4.2")
    assert section is not None
    assert section.path == "4. Política de Trocas e Devoluções > 4.2 Trocas por Defeito"


def test_errata_point_to_existing_sections(index: PolicyIndex) -> None:
    assert all(index.get(section_id) is not None for section_id in ERRATA)
