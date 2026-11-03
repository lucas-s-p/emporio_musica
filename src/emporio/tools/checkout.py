"""Payment and shipping tools. Totals are computed in code from the cart, never by the model."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from emporio.services.catalog import Availability, availability_of, quote_for
from emporio.services.installments import can_combine_payment_methods, installment_options
from emporio.services.pricing import money
from emporio.services.shipping import estimate_shipping, needs_special_freight
from emporio.tools.base import JsonDict, Tool, ToolError, ToolInput
from emporio.tools.context import ToolContext
from emporio.tools.serializers import money_str


class CartItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int
    quantity: int = Field(default=1, ge=1, le=20)


class PaymentOptionsInput(ToolInput):
    items: list[CartItem] = Field(min_length=1, max_length=10, description="Products to buy.")


class ShippingInput(ToolInput):
    items: list[CartItem] = Field(min_length=1, max_length=10, description="Products to buy.")
    city: str = Field(min_length=2, description="Delivery city, e.g. 'Campo Grande'.")


class _Cart:
    """Cart totals computed from current prices."""

    def __init__(self, ctx: ToolContext, items: list[CartItem]) -> None:
        self.card_total = Decimal(0)
        self.pix_total = Decimal(0)
        self.names: list[str] = []
        self.unavailable: list[int] = []
        for item in items:
            product = ctx.store.products.get(item.product_id)
            if product is None:
                raise ToolError("PRODUCT_NOT_FOUND", product_id=item.product_id)
            quote = quote_for(ctx.store, product)
            self.card_total += quote.price * item.quantity
            self.pix_total += quote.pix_price * item.quantity
            self.names.append(product.name)
            if availability_of(product) != Availability.IN_STOCK:
                self.unavailable.append(product.product_id)
        self.card_total = money(self.card_total)
        self.pix_total = money(self.pix_total)


def _payment_options(ctx: ToolContext, args: PaymentOptionsInput) -> JsonDict:
    cart = _Cart(ctx, args.items)
    return {
        "card_total": money_str(cart.card_total),
        "pix_total": money_str(cart.pix_total),
        "installments_interest_free": [
            {"count": o.count, "value": money_str(o.value)}
            for o in installment_options(cart.card_total)
        ],
        "can_combine_payment_methods": can_combine_payment_methods(cart.card_total),
        "unavailable_product_ids": cart.unavailable,
    }


def _shipping(ctx: ToolContext, args: ShippingInput) -> JsonDict:
    cart = _Cart(ctx, args.items)
    special = any(needs_special_freight(name) for name in cart.names)
    estimate = estimate_shipping(cart.card_total, args.city, special_quote_required=special)
    return {
        "subtotal": money_str(cart.card_total),
        "metro_area": estimate.metro_area,
        "free_shipping": estimate.free,
        "fee": None if estimate.fee is None else money_str(estimate.fee),
        "delivery_business_days": (
            list(estimate.delivery_days_business) if estimate.delivery_days_business else None
        ),
        "carrier_options": {name: list(days) for name, days in estimate.carrier_options.items()},
        "special_quote_required": estimate.special_quote_required,
        "unavailable_product_ids": cart.unavailable,
    }


def checkout_tools(ctx: ToolContext) -> list[Tool]:
    return [
        Tool(
            name="get_payment_options",
            description=(
                "Payment conditions for a cart: card total, PIX total, every allowed "
                "interest-free installment option and whether payment methods can be combined. "
                "Use this instead of doing any price arithmetic."
            ),
            input_model=PaymentOptionsInput,
            handler=lambda args: _payment_options(ctx, args),
        ),
        Tool(
            name="estimate_shipping",
            description=(
                "Shipping fee and delivery time for a cart and a destination city. Outside "
                "Campo Grande there is no fixed fee, only carrier options and deadlines."
            ),
            input_model=ShippingInput,
            handler=lambda args: _shipping(ctx, args),
        ),
    ]
