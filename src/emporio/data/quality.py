"""Read-only data quality checks. They report problems, never fix them silently."""

from dataclasses import dataclass
from decimal import Decimal

from emporio.data.repositories import Store
from emporio.domain.models import ProductStatus


@dataclass(frozen=True)
class DataIssue:
    code: str
    message: str


def check_data_quality(store: Store) -> list[DataIssue]:
    """Messages carry ids only, never personal data, so they are safe to log."""
    issues: list[DataIssue] = []

    # Orders whose total differs from the sum of their items at current prices.
    for order in store.orders.all():
        expected = Decimal(0)
        for item in store.orders.items_of(order.order_id):
            product = store.products.get(item.product_id)
            if product:
                expected += product.price_brl * item.quantity
        if expected != order.total_brl:
            issues.append(
                DataIssue(
                    "ORDER_TOTAL_MISMATCH",
                    f"Order {order.order_id}: total {order.total_brl} vs items {expected}",
                )
            )

    # Customers sharing the same email (identity checks must not rely on email alone).
    by_email: dict[str, list[int]] = {}
    for customer in store.customers.all():
        by_email.setdefault(customer.email, []).append(customer.customer_id)
    for ids in by_email.values():
        if len(ids) > 1:
            issues.append(DataIssue("DUPLICATE_EMAIL", f"Customers {ids} share one email"))

    # Categories listed but with no products.
    for category in store.categories.all():
        if not store.products.by_category(category.category_id):
            issues.append(
                DataIssue("EMPTY_CATEGORY", f"Category {category.category_id} has no products")
            )

    # Orders containing products that are not sold yet.
    for order in store.orders.all():
        for item in store.orders.items_of(order.order_id):
            product = store.products.get(item.product_id)
            if product and product.status is ProductStatus.COMING_SOON:
                issues.append(
                    DataIssue(
                        "COMING_SOON_ORDERED",
                        f"Order {order.order_id} has coming_soon product {product.product_id}",
                    )
                )

    return issues