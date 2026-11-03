from datetime import date

import pytest

from emporio.data import Store
from emporio.domain.models import Order
from emporio.services.returns import ReturnKind, ReturnOutcome, evaluate_return


@pytest.fixture
def delivered(store: Store) -> Order:
    # Order 7: bought 2026-02-03, estimated delivery 2026-02-17.
    order = store.orders.get(7)
    assert order is not None
    return order


def test_regret_within_deadline(delivered: Order) -> None:
    decision = evaluate_return(delivered, ReturnKind.REGRET, date(2026, 2, 20))
    assert decision.eligible
    assert decision.deadline == date(2026, 2, 24)
    assert decision.days_remaining == 4
    assert "RETURN_SHIPPING_PAID_BY_STORE" in decision.conditions


def test_regret_last_day_is_inclusive(delivered: Order) -> None:
    decision = evaluate_return(delivered, ReturnKind.REGRET, date(2026, 2, 24))
    assert decision.eligible and decision.days_remaining == 0


def test_regret_expired(delivered: Order) -> None:
    decision = evaluate_return(delivered, ReturnKind.REGRET, date(2026, 2, 25))
    assert decision.outcome is ReturnOutcome.EXPIRED
    assert decision.deadline == date(2026, 2, 24)
    assert decision.alternatives == ()


def test_real_today_is_outside_every_deadline(store: Store) -> None:
    today = date(2026, 11, 2)
    delivered = [o for o in store.orders.all() if o.status.value == "delivered"]
    assert delivered
    assert not any(evaluate_return(o, ReturnKind.REGRET, today).eligible for o in delivered)


def test_preference_has_stock_condition(delivered: Order) -> None:
    decision = evaluate_return(delivered, ReturnKind.PREFERENCE, date(2026, 2, 18))
    assert decision.eligible
    assert "SUBJECT_TO_STOCK_OF_DESIRED_PRODUCT" in decision.conditions


def test_defect_counts_from_purchase_date(delivered: Order) -> None:
    assert evaluate_return(delivered, ReturnKind.DEFECT, date(2026, 3, 5)).eligible
    expired = evaluate_return(delivered, ReturnKind.DEFECT, date(2026, 3, 6))
    assert expired.outcome is ReturnOutcome.EXPIRED
    assert expired.deadline == date(2026, 3, 5)


def test_defect_expired_inside_legal_warranty(delivered: Order) -> None:
    decision = evaluate_return(delivered, ReturnKind.DEFECT, date(2026, 4, 1))
    assert decision.alternatives == ("LEGAL_WARRANTY_90_DAYS", "MANUFACTURER_WARRANTY")


def test_defect_expired_after_legal_warranty(delivered: Order) -> None:
    decision = evaluate_return(delivered, ReturnKind.DEFECT, date(2026, 11, 2))
    assert decision.alternatives == ("MANUFACTURER_WARRANTY",)


@pytest.mark.parametrize(
    ("order_id", "outcome"),
    [
        (8, ReturnOutcome.NOT_DELIVERED),  # shipped
        (9, ReturnOutcome.NOT_DELIVERED),  # confirmed
        (13, ReturnOutcome.NOT_DELIVERED),  # pending
        (17, ReturnOutcome.ORDER_CANCELLED),
    ],
)
def test_orders_not_delivered(store: Store, order_id: int, outcome: ReturnOutcome) -> None:
    order = store.orders.get(order_id)
    assert order is not None
    assert evaluate_return(order, ReturnKind.REGRET, date(2026, 3, 1)).outcome is outcome


def test_missing_delivery_date_needs_human(delivered: Order) -> None:
    no_date = delivered.model_copy(update={"estimated_delivery": None})
    decision = evaluate_return(no_date, ReturnKind.REGRET, date(2026, 2, 20))
    assert decision.outcome is ReturnOutcome.UNKNOWN_DELIVERY_DATE