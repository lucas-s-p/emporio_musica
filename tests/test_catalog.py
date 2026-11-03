from decimal import Decimal

import pytest

from emporio.data import Store
from emporio.services.catalog import (
    Availability,
    availability_of,
    mentions_accessory,
    resolve_category,
    search_products,
    similar_products,
)


def names(store: Store, **kwargs: object) -> list[str]:
    return [p.name for p in search_products(store, **kwargs).products]  # type: ignore[arg-type]


def test_instrument_type_maps_to_category(store: Store) -> None:
    result = search_products(store, query="violão")
    assert result.products
    assert {p.category_id for p in result.products} == {5}


@pytest.mark.parametrize("query", ["violao", "VIOLÕES", "Violões", "violoes"])
def test_accents_case_and_plural_are_equivalent(store: Store, query: str) -> None:
    assert names(store, query=query) == names(store, query="violão")


def test_model_lookup(store: Store) -> None:
    assert names(store, query="Takamine GD20") == ["Takamine GD20 Dreadnought Natural"]


def test_hyphenated_model_code(store: Store) -> None:
    assert names(store, query="GN-15") == ["Giannini GN-15 Nylon Cedr Natural"]


def test_unknown_model_never_falls_back_to_the_brand(store: Store) -> None:
    assert names(store, query="Takamine GD99") == []


def test_brand_does_not_match_a_longer_brand(store: Store) -> None:
    result = search_products(store, query="kala")
    assert result.products and all(p.brand == "Kala" for p in result.products)


def test_modifier_narrows_when_it_matches(store: Store) -> None:
    result = search_products(store, query="violão nylon")
    assert result.products and all(p.specs["strings"] == "nylon" for p in result.products)


def test_modifier_is_dropped_when_nothing_matches(store: Store) -> None:
    result = search_products(store, query="guitarra elétrica")
    assert len(result.products) == 5
    assert result.relaxed_terms == ["eletrica"]


def test_max_price_uses_the_promotional_price(store: Store) -> None:
    # Product 121 lists at 549.00 but is 20% off (439.20).
    assert "Ohana CK-20 Concert Natural" in names(store, query="ukulele", max_price=Decimal(440))
    assert "Ohana CK-20 Concert Natural" not in names(
        store, query="ukulele", max_price=Decimal(430)
    )


def test_results_are_sorted_by_price(store: Store) -> None:
    prices = [
        p.price_brl for p in search_products(store, query="violão", max_price=Decimal(700)).products
    ]
    assert prices == sorted(prices) and prices


def test_unavailable_products_are_hidden_and_counted(store: Store) -> None:
    default = search_products(store, query="violão", max_price=Decimal(800))
    everything = search_products(
        store, query="violão", max_price=Decimal(800), only_available=False
    )
    assert all(availability_of(p) is not None for p in default.products)
    assert default.hidden_unavailable == len(everything.products) - len(default.products) > 0
    assert all(availability_of(p) == Availability.IN_STOCK for p in default.products)


def test_availability_codes(store: Store) -> None:
    def code(pid: int) -> str:
        product = store.products.get(pid)
        assert product is not None
        return availability_of(product)

    assert code(95) == Availability.IN_STOCK
    assert code(96) == Availability.OUT_OF_STOCK  # active, zero stock
    assert code(113) == Availability.DISCONTINUED
    assert code(130) == Availability.COMING_SOON  # has stock but is not sold yet


def test_similar_products_are_available_and_same_category(store: Store) -> None:
    product = store.products.get(96)
    assert product is not None
    similar = similar_products(store, product)
    assert len(similar) == 3
    assert all(p.category_id == 5 and p.product_id != 96 for p in similar)
    assert all(availability_of(p) == Availability.IN_STOCK for p in similar)
    assert abs(similar[0].price_brl - product.price_brl) <= abs(
        similar[-1].price_brl - product.price_brl
    )


def test_resolve_category(store: Store) -> None:
    assert resolve_category("violões", store) == (5,)
    assert resolve_category("Teclados e Pianos", store) == (4,)
    assert resolve_category("acessórios", store) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("cordas de nylon para violão", True),
        ("cabo P10", True),
        ("pedal de efeito", True),
        ("amplificador", True),
        ("violão 7 cordas", False),
        ("Yamaha C40", False),
    ],
)
def test_mentions_accessory(text: str, expected: bool) -> None:
    assert mentions_accessory(text) is expected
