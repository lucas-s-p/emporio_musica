from decimal import Decimal

from emporio.services.shipping import estimate_shipping, needs_special_freight


def test_metro_free_above_500() -> None:
    est = estimate_shipping(Decimal("899"), "Campo Grande")
    assert est.metro_area and est.free and est.fee == Decimal(0)
    assert est.delivery_days_business == (1, 3)


def test_metro_flat_fee_below_500() -> None:
    est = estimate_shipping(Decimal("499.99"), "campo grande")
    assert not est.free and est.fee == Decimal(35)


def test_exactly_500_is_free_by_assumption() -> None:
    assert estimate_shipping(Decimal("500"), "Campo Grande").free


def test_other_city_has_no_fixed_fee() -> None:
    est = estimate_shipping(Decimal("899"), "Dourados")
    assert not est.metro_area and est.fee is None
    assert est.carrier_options["SEDEX (Correios)"] == (2, 5)


def test_special_freight_detection() -> None:
    assert needs_special_freight("Bateria Acústica Yamaha Kit 1 Studio")
    assert not needs_special_freight("Yamaha C40 Nylon Natural")