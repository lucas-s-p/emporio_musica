"""Customer tools: identity verification, order status and return eligibility.

Authorization is enforced here, in code: an order is only readable through the conversation's
verifier, and a missing order and someone else's order look identical to the model.
"""

from pydantic import Field

from emporio.domain.models import Order
from emporio.services.identity import VerificationStatus
from emporio.services.orders import order_signals
from emporio.services.returns import ReturnKind, evaluate_return
from emporio.services.store import STORE_INFO
from emporio.tools.base import JsonDict, Tool, ToolError, ToolInput
from emporio.tools.context import ToolContext
from emporio.tools.serializers import money_str

_NEXT_STEP = {
    VerificationStatus.AMBIGUOUS: "ASK_ORDER_NUMBER",
    VerificationStatus.FAILED: "ASK_TO_CHECK_DATA",
    VerificationStatus.LOCKED: "REFER_TO_STORE_CONTACT",
}


class VerifyCustomerInput(ToolInput):
    contact: str = Field(min_length=5, description="Customer's email or phone number.")
    order_id: int | None = Field(
        default=None, description="Order number, if the customer gave one."
    )


class OrderStatusInput(ToolInput):
    order_id: int | None = Field(
        default=None, description="Order number. Omit to list the verified customer's orders."
    )


class ReturnEligibilityInput(ToolInput):
    order_id: int
    reason: ReturnKind = Field(
        description="regret = changed mind, defect = manufacturing defect, "
        "preference = exchange for another model."
    )


def _require_verified(ctx: ToolContext) -> None:
    if not ctx.verifier.is_verified:
        raise ToolError("NOT_VERIFIED", next_step="ASK_EMAIL_OR_PHONE")


def _own_order(ctx: ToolContext, order_id: int) -> Order:
    _require_verified(ctx)
    order = ctx.verifier.order_for(order_id)
    if order is None:
        raise ToolError("ORDER_NOT_FOUND")  # same answer for missing and for someone else's
    return order


def _order_payload(ctx: ToolContext, order: Order) -> JsonDict:
    signals = order_signals(order, ctx.clock.today())
    items = []
    for item in ctx.store.orders.items_of(order.order_id):
        product = ctx.store.products.get(item.product_id)
        items.append(
            {
                "product_id": item.product_id,
                "name": product.name if product else None,
                "quantity": item.quantity,
            }
        )
    payload: JsonDict = {
        "order_id": order.order_id,
        "status": order.status.value,
        "order_date": order.order_date.isoformat(),
        "total": money_str(order.total_brl),
        "payment_method": order.payment_method,
        "tracking_code": order.tracking_code,
        "estimated_delivery": order.estimated_delivery.isoformat()
        if order.estimated_delivery
        else None,
        "notes": order.notes,
        "items": items,
        "signals": list(signals.codes),
        "days_overdue": signals.days_overdue,
        "days_since_order": signals.days_since_order,
    }
    if signals.codes:
        payload["store_contact"] = {"phone": STORE_INFO.phone, "email": STORE_INFO.email}
    return payload


def _verify(ctx: ToolContext, args: VerifyCustomerInput) -> JsonDict:
    result = ctx.verifier.verify(args.contact, args.order_id)
    payload: JsonDict = {"status": result.status.value}
    if result.first_name:
        payload["first_name"] = result.first_name
    if result.status in _NEXT_STEP:
        payload["next_step"] = _NEXT_STEP[result.status]
    if result.status is VerificationStatus.LOCKED:
        payload["store_contact"] = {"phone": STORE_INFO.phone, "email": STORE_INFO.email}
    return payload


def _order_status(ctx: ToolContext, args: OrderStatusInput) -> JsonDict:
    if args.order_id is not None:
        return _order_payload(ctx, _own_order(ctx, args.order_id))
    _require_verified(ctx)
    orders = sorted(ctx.verifier.my_orders(), key=lambda o: o.order_date, reverse=True)
    return {"orders": [_order_payload(ctx, o) for o in orders]}


def _return_eligibility(ctx: ToolContext, args: ReturnEligibilityInput) -> JsonDict:
    order = _own_order(ctx, args.order_id)
    today = ctx.clock.today()
    decision = evaluate_return(order, args.reason, today)
    return {
        "order_id": order.order_id,
        "reason": decision.kind.value,
        "outcome": decision.outcome.value,
        "eligible": decision.eligible,
        "today": today.isoformat(),
        "order_date": order.order_date.isoformat(),
        "received_date_used": order.estimated_delivery.isoformat()
        if order.estimated_delivery
        else None,
        "deadline": decision.deadline.isoformat() if decision.deadline else None,
        "days_remaining": decision.days_remaining,
        "conditions": list(decision.conditions),
        "alternatives": list(decision.alternatives),
    }


def order_tools(ctx: ToolContext) -> list[Tool]:
    return [
        Tool(
            name="verify_customer",
            description=(
                "Verify the customer's identity with an email or phone number, optionally with "
                "an order number. Required before any order information or return check. "
                "Never reveal whether the order or the contact was the wrong part."
            ),
            input_model=VerifyCustomerInput,
            handler=lambda args: _verify(ctx, args),
        ),
        Tool(
            name="get_order_status",
            description=(
                "Status, items, tracking code and delivery estimate of one order of the verified "
                "customer, or a list of all their orders when order_id is omitted. "
                "'signals' flags late or stalled orders."
            ),
            input_model=OrderStatusInput,
            handler=lambda args: _order_status(ctx, args),
        ),
        Tool(
            name="check_return_eligibility",
            description=(
                "Check, with today's date, whether an order of the verified customer can still "
                "be returned or exchanged for a given reason. Returns deadline, days left and "
                "condition codes. Item-specific exclusions must be checked in the policies."
            ),
            input_model=ReturnEligibilityInput,
            handler=lambda args: _return_eligibility(ctx, args),
        ),
    ]
