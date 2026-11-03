from datetime import date

from emporio.data import Store
from emporio.services.orders import order_signals

TODAY = date(2026, 11, 3)


def signals(store: Store, order_id: int, today: date = TODAY):  # type: ignore[no-untyped-def]
    order = store.orders.get(order_id)
    assert order is not None
    return order_signals(order, today)


def test_overdue_estimate(store: Store) -> None:
    result = signals(store, 8)  # shipped, estimated 2026-02-28
    assert result.codes == ("DELIVERY_ESTIMATE_OVERDUE",)
    assert result.days_overdue == 248


def test_stalled_order(store: Store) -> None:
    assert signals(store, 9).codes == ("ORDER_STALLED",)  # confirmed in February, no estimate


def test_recent_open_order_has_no_signal(store: Store) -> None:
    assert signals(store, 16, today=date(2026, 3, 25)).codes == ()


def test_delivered_and_cancelled_have_no_signals(store: Store) -> None:
    assert signals(store, 4).codes == ()
    assert signals(store, 17).codes == ()
