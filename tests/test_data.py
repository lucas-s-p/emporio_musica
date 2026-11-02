from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from emporio.data import Store, load_store
from emporio.data.loaders import find_table_file
from emporio.data.quality import check_data_quality
from emporio.domain.models import OrderStatus, ProductStatus


def test_row_counts(store: Store) -> None:
    assert len(store.products.all()) == 65
    assert len(store.categories.all()) == 9
    assert len(store.customers.all()) == 50
    assert len(store.orders.all()) == 20
    assert len(store.promotions.all()) == 25


def test_product_parsing(store: Store) -> None:
    gd20 = store.products.get(95)
    assert gd20 is not None
    assert gd20.name == "Takamine GD20 Dreadnought Natural"
    assert gd20.brand == "Takamine"
    assert gd20.price_brl == Decimal("2199")
    assert gd20.is_purchasable
    assert store.products.get(145) is not None  # id listed out of order in the CSV


def test_specs_are_strings(store: Store) -> None:
    c40 = store.products.get(81)
    assert c40 is not None
    assert c40.specs["strings"] == "nylon"
    guitar = store.products.get(131)
    assert guitar is not None
    assert guitar.specs["strings"] == "6"


def test_non_purchasable_products(store: Store) -> None:
    assert not store.products.get(96).is_purchasable  # type: ignore[union-attr]  # stock 0
    assert store.products.get(113).status is ProductStatus.DISCONTINUED  # type: ignore[union-attr]
    assert store.products.get(130).status is ProductStatus.COMING_SOON  # type: ignore[union-attr]


def test_every_product_has_a_brand(store: Store) -> None:
    missing = [p.name for p in store.products.all() if p.brand is None]
    assert missing == []


def test_blank_order_fields_become_none(store: Store) -> None:
    confirmed = store.orders.get(9)
    assert confirmed is not None
    assert confirmed.status is OrderStatus.CONFIRMED
    assert confirmed.tracking_code is None
    assert confirmed.estimated_delivery is None
    shipped = store.orders.get(8)
    assert shipped is not None
    assert shipped.estimated_delivery == date(2026, 2, 28)


def test_order_installments(store: Store) -> None:
    assert store.orders.get(2).installments == 6  # type: ignore[union-attr]
    assert store.orders.get(1).installments == 1  # type: ignore[union-attr]


def test_order_items_and_customer_lookup(store: Store) -> None:
    assert [i.product_id for i in store.orders.items_of(15)] == [82, 106]
    assert {o.order_id for o in store.orders.by_customer(3)} == {1, 19}


def test_active_promotions(store: Store) -> None:
    active = [p for p in store.promotions.all() if p.is_active]
    assert {p.product_id for p in active} == {127, 121, 90, 94}
    assert store.promotions.active_for(127).discount_percent == 10  # type: ignore[union-attr]
    assert store.promotions.active_for(95) is None  # GD20 promo expired
    assert len(store.promotions.for_product(95)) == 1


def test_shared_email_returns_both_customers(store: Store) -> None:
    found = store.customers.find_by_email("  Bruno.Martins@jmail.com ")
    assert {c.customer_id for c in found} == {11, 43}


def test_phone_lookup_ignores_formatting(store: Store) -> None:
    found = store.customers.find_by_phone("67998123456")
    assert [c.customer_id for c in found] == [1]
    assert store.customers.find_by_phone("") == []


def test_quality_issues_match_known_problems(store: Store) -> None:
    issues = check_data_quality(store)
    codes = {i.code for i in issues}
    assert codes == {
        "ORDER_TOTAL_MISMATCH",
        "DUPLICATE_EMAIL",
        "EMPTY_CATEGORY",
        "COMING_SOON_ORDERED",
    }
    mismatches = {i.message.split(":")[0] for i in issues if i.code == "ORDER_TOTAL_MISMATCH"}
    assert mismatches == {"Order 3", "Order 20"}
    empty = {i.message for i in issues if i.code == "EMPTY_CATEGORY"}
    assert len(empty) == 3  # categories 6, 7, 8
    assert not any("@" in i.message for i in issues)  # no personal data in messages


def test_find_table_file_does_not_confuse_orders_and_order_items() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    assert find_table_file(data_dir, "orders").stem.endswith("- orders")
    assert find_table_file(data_dir, "order_items").stem.endswith("- order_items")


def test_missing_table_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_store(tmp_path)