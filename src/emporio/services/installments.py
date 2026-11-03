"""Credit card installment rules (policy section 3)."""

from dataclasses import dataclass
from decimal import Decimal

from emporio.services.pricing import money

MAX_INSTALLMENTS = 12
COMBINED_PAYMENT_MIN_TOTAL = Decimal(2000)

# (up to N installments, minimum installment value). Source: policy 3.1, which is more
# specific than the summary table (that one says R$ 100 for any count).
_MIN_INSTALLMENT_BY_RANGE: tuple[tuple[int, Decimal], ...] = (
    (3, Decimal(50)),
    (6, Decimal(80)),
    (12, Decimal(100)),
)


@dataclass(frozen=True)
class InstallmentOption:
    count: int
    value: Decimal  # rounded to cents; interest-free, so count * value is about the total


def min_installment_value(count: int) -> Decimal:
    for upper, minimum in _MIN_INSTALLMENT_BY_RANGE:
        if count <= upper:
            return minimum
    raise ValueError(f"Installment count above {MAX_INSTALLMENTS}: {count}")


def is_installment_allowed(total: Decimal, count: int) -> bool:
    if count < 1 or count > MAX_INSTALLMENTS:
        return False
    if count == 1:
        return True
    return total / count >= min_installment_value(count)


def installment_options(total: Decimal) -> list[InstallmentOption]:
    """All allowed interest-free options, from 1x up to the maximum the rules permit."""
    return [
        InstallmentOption(count, money(total / count))
        for count in range(1, MAX_INSTALLMENTS + 1)
        if is_installment_allowed(total, count)
    ]


def can_combine_payment_methods(total: Decimal) -> bool:
    """Combining payment methods (e.g. PIX + card) is allowed above R$ 2.000,00."""
    return total > COMBINED_PAYMENT_MIN_TOTAL