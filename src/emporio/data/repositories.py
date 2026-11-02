"""In-memory repositories. Lookups only: business rules live in the services layer."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from emporio.data import loaders
from emporio.data.cleaning import normalize_text
from emporio.domain.models import Category, Customer, Order, OrderItem, Product, Promotion

logger = logging.getLogger(__name__)


class CategoryRepository:
    def __init__(self, categories: list[Category]) -> None:
        self._by_id = {c.category_id: c for c in categories}

    def get(self, category_id: int) -> Category | None:
        return self._by_id.get(category_id)

    def all(self) -> list[Category]:
        return list(self._by_id.values())


class ProductRepository:
    def __init__(self, products: list[Product]) -> None:
        self._by_id = {p.product_id: p for p in products}

    def get(self, product_id: int) -> Product | None:
        return self._by_id.get(product_id)

    def all(self) -> list[Product]:
        return list(self._by_id.values())

    def by_category(self, category_id: int) -> list[Product]:
        return [p for p in self._by_id.values() if p.category_id == category_id]


class CustomerRepository:
    def __init__(self, customers: list[Customer]) -> None:
        self._by_id = {c.customer_id: c for c in customers}

    def get(self, customer_id: int) -> Customer | None:
        return self._by_id.get(customer_id)

    def all(self) -> list[Customer]:
        return list(self._by_id.values())

    def find_by_email(self, email: str) -> list[Customer]:
        """Returns a list: the source data has an email shared by two customers."""
        target = normalize_text(email)
        return [c for c in self._by_id.values() if c.email == target]

    def find_by_phone(self, phone: str) -> list[Customer]:
        digits = "".join(ch for ch in phone if ch.isdigit())
        return [c for c in self._by_id.values() if digits and c.phone_digits == digits]


class OrderRepository:
    def __init__(self, orders: list[Order], items: list[OrderItem]) -> None:
        self._by_id = {o.order_id: o for o in orders}
        self._items: dict[int, list[OrderItem]] = defaultdict(list)
        for item in items:
            self._items[item.order_id].append(item)

    def get(self, order_id: int) -> Order | None:
        return self._by_id.get(order_id)

    def all(self) -> list[Order]:
        return list(self._by_id.values())

    def items_of(self, order_id: int) -> list[OrderItem]:
        return list(self._items.get(order_id, []))

    def by_customer(self, customer_id: int) -> list[Order]:
        return [o for o in self._by_id.values() if o.customer_id == customer_id]


class PromotionRepository:
    def __init__(self, promotions: list[Promotion]) -> None:
        self._all = promotions

    def all(self) -> list[Promotion]:
        return list(self._all)

    def for_product(self, product_id: int) -> list[Promotion]:
        return [p for p in self._all if p.product_id == product_id]

    def active_for(self, product_id: int) -> Promotion | None:
        """The active promotion of a product. The data has at most one per product."""
        active = [p for p in self.for_product(product_id) if p.is_active]
        return active[0] if active else None


@dataclass(frozen=True)
class Store:
    """All repositories, loaded once and shared by services and tools."""

    categories: CategoryRepository
    products: ProductRepository
    customers: CustomerRepository
    orders: OrderRepository
    promotions: PromotionRepository


def load_store(data_dir: Path) -> Store:
    """Load every CSV in data_dir into validated, in-memory repositories."""
    store = Store(
        categories=CategoryRepository(loaders.load_categories(data_dir)),
        products=ProductRepository(loaders.load_products(data_dir)),
        customers=CustomerRepository(loaders.load_customers(data_dir)),
        orders=OrderRepository(loaders.load_orders(data_dir), loaders.load_order_items(data_dir)),
        promotions=PromotionRepository(loaders.load_promotions(data_dir)),
    )
    logger.info(
        "Store loaded: %d products, %d customers, %d orders",
        len(store.products.all()),
        len(store.customers.all()),
        len(store.orders.all()),
    )
    return store