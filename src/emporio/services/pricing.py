"""Price rules: active promotion and PIX discount."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from emporio.domain.models import Product, Promotion

CENT = Decimal("0.01")
PIX_DISCOUNT_PERCENT = Decimal(5)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PriceQuote:
    product_id: int
    list_price: Decimal
    promotion_percent: int | None
    promotion_name: str | None
    price: Decimal  # card, debit and boleto (promotion applied, if any)
    pix_price: Decimal
    pix_discount_applies: bool

    @property
    def has_promotion(self) -> bool:
        return self.promotion_percent is not None


def build_quote(product: Product, promotion: Promotion | None) -> PriceQuote:
    """Build the price quote of a product.

    Policy: promotions do not stack and the PIX discount does not apply to promotional prices.
    An inactive promotion (or one from another product) is ignored, so an expired
    discount can never be offered.
    """
    active = (
        promotion
        if promotion and promotion.is_active and promotion.product_id == product.product_id
        else None
    )
    if active:
        price = money(product.price_brl * (100 - active.discount_percent) / 100)
        return PriceQuote(
            product_id=product.product_id,
            list_price=product.price_brl,
            promotion_percent=active.discount_percent,
            promotion_name=active.description,
            price=price,
            pix_price=price,
            pix_discount_applies=False,
        )
    return PriceQuote(
        product_id=product.product_id,
        list_price=product.price_brl,
        promotion_percent=None,
        promotion_name=None,
        price=product.price_brl,
        pix_price=money(product.price_brl * (100 - PIX_DISCOUNT_PERCENT) / 100),
        pix_discount_applies=True,
    )