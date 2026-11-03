"""Turn domain objects into JSON-safe dicts. Money is a string with 2 decimals ("599.90")."""

from decimal import Decimal

from emporio.data import Store
from emporio.domain.models import Product
from emporio.services.catalog import Availability, availability_of, quote_for
from emporio.services.pricing import PriceQuote


def money_str(value: Decimal) -> str:
    return f"{value:.2f}"


def quote_payload(quote: PriceQuote) -> dict[str, object]:
    return {
        "list_price": money_str(quote.list_price),
        "price": money_str(quote.price),  # card, debit, boleto
        "pix_price": money_str(quote.pix_price),
        "pix_discount_applies": quote.pix_discount_applies,
        "promotion": (
            {"name": quote.promotion_name, "percent": quote.promotion_percent}
            if quote.has_promotion
            else None
        ),
    }


def product_payload(store: Store, product: Product) -> dict[str, object]:
    category = store.categories.get(product.category_id)
    availability = availability_of(product)
    return {
        "product_id": product.product_id,
        "name": product.name,
        "brand": product.brand,
        "category": category.name if category else None,
        "availability": availability,
        "stock_quantity": product.stock_quantity if availability == Availability.IN_STOCK else None,
        **quote_payload(quote_for(store, product)),
    }
