"""Shipping rules (policy section 5)."""

from dataclasses import dataclass, field
from decimal import Decimal

from emporio.data.cleaning import normalize_text

FREE_SHIPPING_MIN_SUBTOTAL = Decimal(500)
FLAT_FEE = Decimal(35)
METRO_DELIVERY_DAYS = (1, 3)
# Business days. Prices for other cities depend on CEP, weight and size (not in the data).
CARRIER_OPTIONS: dict[str, tuple[int, int]] = {
    "PAC (Correios)": (5, 12),
    "SEDEX (Correios)": (2, 5),
    "Jadlog (.package)": (3, 8),
}
# The policy does not define "metropolitan region". Assumption: Campo Grande only.
METRO_CITIES = frozenset({"campo grande"})


@dataclass(frozen=True)
class ShippingEstimate:
    metro_area: bool
    fee: Decimal | None  # None when it depends on the destination CEP
    free: bool
    delivery_days_business: tuple[int, int] | None
    carrier_options: dict[str, tuple[int, int]] = field(default_factory=dict)
    special_quote_required: bool = False


def needs_special_freight(product_name: str) -> bool:
    """Large instruments (acoustic drums, digital pianos, double basses) need a custom quote."""
    name = normalize_text(product_name)
    return any(term in name for term in ("bateria acustica", "piano", "contrabaixo"))


def estimate_shipping(
    subtotal: Decimal, city: str, special_quote_required: bool = False
) -> ShippingEstimate:
    if normalize_text(city) in METRO_CITIES:
        # Boundary assumption: exactly R$ 500 ships free (the policy leaves it undefined).
        free = subtotal >= FREE_SHIPPING_MIN_SUBTOTAL
        return ShippingEstimate(
            metro_area=True,
            fee=Decimal(0) if free else FLAT_FEE,
            free=free,
            delivery_days_business=METRO_DELIVERY_DAYS,
            special_quote_required=special_quote_required,
        )
    return ShippingEstimate(
        metro_area=False,
        fee=None,
        free=False,
        delivery_days_business=None,
        carrier_options=dict(CARRIER_OPTIONS),
        special_quote_required=special_quote_required,
    )