from decimal import Decimal

from emporio.data import Store
from emporio.services.pricing import build_quote


def test_no_promotion_applies_pix_discount(store: Store) -> None:
    gd20 = store.products.get(95)
    assert gd20 is not None
    quote = build_quote(gd20, store.promotions.active_for(95))
    assert not quote.has_promotion
    assert quote.price == Decimal("2199")
    assert quote.pix_price == Decimal("2089.05")
    assert quote.pix_discount_applies


def test_pix_rounds_half_up(store: Store) -> None:
    c40 = store.products.get(81)
    assert c40 is not None
    assert build_quote(c40, None).pix_price == Decimal("569.91")  # 599.9 * 0.95 = 569.905


def test_active_promotion_blocks_pix_discount(store: Store) -> None:
    product = store.products.get(127)
    assert product is not None
    quote = build_quote(product, store.promotions.active_for(127))
    assert quote.promotion_percent == 10
    assert quote.list_price == Decimal("359")
    assert quote.price == Decimal("323.10")
    assert quote.pix_price == quote.price
    assert not quote.pix_discount_applies


def test_larger_promotion(store: Store) -> None:
    product = store.products.get(90)
    assert product is not None
    assert build_quote(product, store.promotions.active_for(90)).price == Decimal("1967.18")


def test_inactive_promotion_is_ignored(store: Store) -> None:
    gd20 = store.products.get(95)
    expired = store.promotions.for_product(95)[0]
    assert gd20 is not None and not expired.is_active
    quote = build_quote(gd20, expired)
    assert not quote.has_promotion
    assert quote.price == Decimal("2199")


def test_promotion_of_another_product_is_ignored(store: Store) -> None:
    gd20 = store.products.get(95)
    other = store.promotions.active_for(127)
    assert gd20 is not None and other is not None
    assert not build_quote(gd20, other).has_promotion