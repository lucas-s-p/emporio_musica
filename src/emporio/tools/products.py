"""Catalog tools: search and product details."""

from decimal import Decimal
from typing import Literal

from pydantic import Field

from emporio.services.catalog import (
    Availability,
    availability_of,
    mentions_accessory,
    resolve_category,
    search_products,
    similar_products,
)
from emporio.tools.base import JsonDict, Tool, ToolError, ToolInput
from emporio.tools.context import ToolContext
from emporio.tools.serializers import product_payload


class SearchProductsInput(ToolInput):
    query: str | None = Field(
        default=None,
        description="Free text: instrument type, brand, model or features, "
        "e.g. 'violão aço', 'Takamine GD20'. Do not put prices here.",
    )
    category: str | None = Field(
        default=None, description="Category in Portuguese, e.g. 'violões', 'ukulele', 'baixos'."
    )
    brand: str | None = Field(default=None, description="Brand name, e.g. 'Yamaha'.")
    min_price_brl: float | None = Field(default=None, ge=0, description="Minimum price in BRL.")
    max_price_brl: float | None = Field(default=None, ge=0, description="Maximum price in BRL.")
    availability: Literal["available", "all"] = Field(
        default="available",
        description="'available' hides out of stock, discontinued and coming soon products "
        "(their count is reported). Use 'all' when asked about a specific product.",
    )
    limit: int = Field(default=8, ge=1, le=15)


class GetProductInput(ToolInput):
    product_id: int


def _search(ctx: ToolContext, args: SearchProductsInput) -> JsonDict:
    if not (args.query or args.category or args.brand):
        raise ToolError("EMPTY_SEARCH", hint="Provide query, category or brand.")

    if mentions_accessory(f"{args.query or ''} {args.category or ''}"):
        raise ToolError(
            "ACCESSORY_NOT_SOLD",
            hint="The store sells only musical instruments, not accessories.",
        )

    category_ids = None
    if args.category:
        category_ids = resolve_category(args.category, ctx.store)
        if category_ids is None:
            raise ToolError(
                "UNKNOWN_CATEGORY",
                categories=[c.name for c in ctx.store.categories.all()],
            )

    outcome = search_products(
        ctx.store,
        query=args.query,
        category_ids=category_ids,
        brand=args.brand,
        min_price=None if args.min_price_brl is None else Decimal(str(args.min_price_brl)),
        max_price=None if args.max_price_brl is None else Decimal(str(args.max_price_brl)),
        only_available=args.availability == "available",
    )
    shown = outcome.products[: args.limit]
    payload: JsonDict = {
        "total_matches": len(outcome.products),
        "returned": len(shown),
        "products": [product_payload(ctx.store, p) for p in shown],
        "hidden_unavailable_matches": outcome.hidden_unavailable,
        "relaxed_terms": outcome.relaxed_terms,
        "price_filter_basis": "price (card price, with the promotion when there is one)",
    }
    if len(shown) < len(outcome.products):
        # Models read "returned" as the number of matches; say it outright.
        payload["note"] = (
            f"{len(outcome.products)} products match, but only the first {len(shown)} are listed "
            f"here. Tell the customer there are {len(outcome.products)} and offer to show the rest."
        )
    return payload


def _get_product(ctx: ToolContext, args: GetProductInput) -> JsonDict:
    product = ctx.store.products.get(args.product_id)
    if product is None:
        raise ToolError("PRODUCT_NOT_FOUND", product_id=args.product_id)
    result: JsonDict = {
        **product_payload(ctx.store, product),
        "description": product.description,
        "specs": product.specs,
    }
    if availability_of(product) != Availability.IN_STOCK:
        result["alternatives"] = [
            product_payload(ctx.store, p) for p in similar_products(ctx.store, product)
        ]
    return result


def product_tools(ctx: ToolContext) -> list[Tool]:
    return [
        Tool(
            name="search_products",
            description=(
                "Search the store catalog. Returns products with current price, PIX price and "
                "stock availability. A product is on promotion only when its `promotion` field "
                "is not null (then the price already has the discount); otherwise the price is "
                "the regular price. Always use this before stating any price or stock. The "
                "store sells only musical instruments."
            ),
            input_model=SearchProductsInput,
            handler=lambda args: _search(ctx, args),
        ),
        Tool(
            name="get_product",
            description=(
                "Full details of one product by id (description, specs, price, stock). For "
                "out of stock or discontinued products it also returns available alternatives."
            ),
            input_model=GetProductInput,
            handler=lambda args: _get_product(ctx, args),
        ),
    ]
