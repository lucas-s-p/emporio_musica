"""Domain models. Immutable, validated, and free of I/O."""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductStatus(StrEnum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class Category(_Model):
    category_id: int
    name: str
    description: str


class Product(_Model):
    product_id: int
    name: str
    brand: str | None
    category_id: int
    description: str
    price_brl: Decimal = Field(gt=0)
    stock_quantity: int = Field(ge=0)
    status: ProductStatus
    specs: dict[str, str]
    created_at: date

    @property
    def is_purchasable(self) -> bool:
        """True only when the product is sold and has stock."""
        return self.status is ProductStatus.ACTIVE and self.stock_quantity > 0


class Customer(_Model):
    customer_id: int
    name: str
    phone: str
    email: str
    city: str

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return value.strip().lower()

    @property
    def phone_digits(self) -> str:
        return "".join(ch for ch in self.phone if ch.isdigit())


class Order(_Model):
    order_id: int
    customer_id: int
    order_date: date
    status: OrderStatus
    total_brl: Decimal = Field(gt=0)
    payment_method: str = Field(pattern=r"^(pix|debit|boleto|credit_\d+x)$")
    tracking_code: str | None = None
    estimated_delivery: date | None = None
    notes: str | None = None

    @property
    def installments(self) -> int:
        """Number of installments (1 for non-credit payments)."""
        if self.payment_method.startswith("credit_"):
            return int(self.payment_method.removeprefix("credit_").removesuffix("x"))
        return 1


class OrderItem(_Model):
    order_id: int
    product_id: int
    quantity: int = Field(gt=0)


class Promotion(_Model):
    promotion_id: int
    product_id: int
    discount_percent: int = Field(gt=0, le=100)
    description: str
    is_active: bool