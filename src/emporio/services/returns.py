"""Return, exchange and warranty eligibility (policy sections 4 and 8)."""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from emporio.domain.models import Order, OrderStatus

REGRET_DAYS = 7
PREFERENCE_DAYS = 7
DEFECT_EXCHANGE_DAYS = 30  # counted from the purchase date
LEGAL_WARRANTY_DAYS = 90  # counted from receipt


class ReturnKind(StrEnum):
    REGRET = "regret"  # direito de arrependimento
    DEFECT = "defect"  # troca por defeito
    PREFERENCE = "preference"  # troca por preferência


class ReturnOutcome(StrEnum):
    ELIGIBLE = "eligible"
    EXPIRED = "expired"
    NOT_DELIVERED = "not_delivered"
    ORDER_CANCELLED = "order_cancelled"
    UNKNOWN_DELIVERY_DATE = "unknown_delivery_date"


_CONDITIONS: dict[ReturnKind, tuple[str, ...]] = {
    ReturnKind.REGRET: (
        "ORIGINAL_PACKAGING_UNUSED_WITH_ACCESSORIES",
        "REFUND_SAME_PAYMENT_METHOD_10_BUSINESS_DAYS",
        "RETURN_SHIPPING_PAID_BY_STORE",
    ),
    ReturnKind.PREFERENCE: (
        "ORIGINAL_PACKAGING_PERFECT_CONDITION",
        "SUBJECT_TO_STOCK_OF_DESIRED_PRODUCT",
        "PRICE_DIFFERENCE_CHARGED_OR_REFUNDED",
    ),
    ReturnKind.DEFECT: (
        "MANUFACTURING_DEFECT_ONLY",
        "MISUSE_DROPS_MOISTURE_MODIFICATIONS_NOT_COVERED",
    ),
}


@dataclass(frozen=True)
class ReturnDecision:
    kind: ReturnKind
    outcome: ReturnOutcome
    deadline: date | None = None
    days_remaining: int | None = None
    conditions: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return self.outcome is ReturnOutcome.ELIGIBLE


def evaluate_return(order: Order, kind: ReturnKind, today: date) -> ReturnDecision:
    """Decide whether an order can be returned or exchanged today.

    Assumptions: the data has no real delivery date, so estimated_delivery stands in for the
    receipt date; and every order in the data is treated as an online purchase.
    """
    if order.status is OrderStatus.CANCELLED:
        return ReturnDecision(kind, ReturnOutcome.ORDER_CANCELLED)
    if order.status is not OrderStatus.DELIVERED:
        return ReturnDecision(kind, ReturnOutcome.NOT_DELIVERED)

    delivery = order.estimated_delivery
    if kind is ReturnKind.DEFECT:
        deadline = order.order_date + timedelta(days=DEFECT_EXCHANGE_DAYS)
    elif delivery is None:
        return ReturnDecision(kind, ReturnOutcome.UNKNOWN_DELIVERY_DATE)
    else:
        days = REGRET_DAYS if kind is ReturnKind.REGRET else PREFERENCE_DAYS
        deadline = delivery + timedelta(days=days)

    if today <= deadline:
        return ReturnDecision(
            kind,
            ReturnOutcome.ELIGIBLE,
            deadline=deadline,
            days_remaining=(deadline - today).days,
            conditions=_CONDITIONS[kind],
        )

    alternatives: tuple[str, ...] = ()
    if kind is ReturnKind.DEFECT:
        within_legal = delivery is not None and today <= delivery + timedelta(
            days=LEGAL_WARRANTY_DAYS
        )
        alternatives = (
            ("LEGAL_WARRANTY_90_DAYS", "MANUFACTURER_WARRANTY")
            if within_legal
            else ("MANUFACTURER_WARRANTY",)
        )
    return ReturnDecision(kind, ReturnOutcome.EXPIRED, deadline=deadline, alternatives=alternatives)