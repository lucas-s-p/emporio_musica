"""Order health signals that depend on today's date."""

from dataclasses import dataclass
from datetime import date

from emporio.domain.models import Order, OrderStatus

STALLED_AFTER_DAYS = 30  # assumption: the manual defines no limit for a stuck order
_OPEN_STATUSES = frozenset({OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.SHIPPED})


@dataclass(frozen=True)
class OrderSignals:
    codes: tuple[str, ...] = ()
    days_overdue: int | None = None
    days_since_order: int = 0


def order_signals(order: Order, today: date) -> OrderSignals:
    """Flags for orders that look wrong today: late delivery estimate or a stalled order."""
    since = (today - order.order_date).days
    if order.status not in _OPEN_STATUSES:
        return OrderSignals(days_since_order=since)

    codes: list[str] = []
    overdue: int | None = None
    if order.estimated_delivery and order.estimated_delivery < today:
        codes.append("DELIVERY_ESTIMATE_OVERDUE")
        overdue = (today - order.estimated_delivery).days
    if order.status in (OrderStatus.PENDING, OrderStatus.CONFIRMED) and since > STALLED_AFTER_DAYS:
        codes.append("ORDER_STALLED")
    return OrderSignals(tuple(codes), overdue, since)
