from decimal import Decimal

import pytest

from emporio.services.installments import (
    can_combine_payment_methods,
    installment_options,
    is_installment_allowed,
    min_installment_value,
)


def _max_count(total: str) -> int:
    return max(o.count for o in installment_options(Decimal(total)))


@pytest.mark.parametrize(
    ("total", "expected_max"),
    [
        ("40", 1),  # 2x would be R$ 20 per installment
        ("159.90", 3),  # 4x would be R$ 39.98
        ("349.90", 4),  # 5x would be R$ 69.98, below the R$ 80 minimum
        ("599", 6),  # 7x would be R$ 85.57, below the R$ 100 minimum
        ("1000", 10),
        ("2199", 12),
    ],
)
def test_max_installments(total: str, expected_max: int) -> None:
    assert _max_count(total) == expected_max


def test_option_values_are_rounded_to_cents() -> None:
    options = {o.count: o.value for o in installment_options(Decimal("2199"))}
    assert options[1] == Decimal("2199.00")
    assert options[12] == Decimal("183.25")


def test_minimums_by_range() -> None:
    assert [min_installment_value(n) for n in (2, 3, 4, 6, 7, 12)] == [
        Decimal(50),
        Decimal(50),
        Decimal(80),
        Decimal(80),
        Decimal(100),
        Decimal(100),
    ]


def test_boundary_is_inclusive() -> None:
    assert is_installment_allowed(Decimal("600"), 6)  # exactly R$ 100
    assert is_installment_allowed(Decimal("100"), 2)  # exactly R$ 50


def test_invalid_counts() -> None:
    assert not is_installment_allowed(Decimal("5000"), 13)
    assert not is_installment_allowed(Decimal("5000"), 0)


def test_combined_payment_only_above_two_thousand() -> None:
    assert can_combine_payment_methods(Decimal("2000.01"))
    assert not can_combine_payment_methods(Decimal("2000"))