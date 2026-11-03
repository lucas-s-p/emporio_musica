"""Customer identity verification. Authorization lives in code, never in the prompt."""

from dataclasses import dataclass
from enum import StrEnum

from emporio.data import Store
from emporio.data.cleaning import normalize_text
from emporio.domain.models import Customer, Order

MAX_FAILED_ATTEMPTS = 3


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"  # contact matches more than one customer: ask for an order number
    LOCKED = "locked"  # too many failed attempts in this conversation


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    first_name: str | None = None


def _is_email(contact: str) -> bool:
    return "@" in contact


def _phone_digits(contact: str) -> str:
    digits = "".join(ch for ch in contact if ch.isdigit())
    return digits[2:] if len(digits) == 13 and digits.startswith("55") else digits


def _contact_matches(customer: Customer, contact: str) -> bool:
    if _is_email(contact):
        return normalize_text(contact) == customer.email
    digits = _phone_digits(contact)
    return bool(digits) and digits == customer.phone_digits


class CustomerVerifier:
    """Per-conversation state: who (if anyone) has proven their identity."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._customer_id: int | None = None
        self._failed_attempts = 0

    @property
    def is_verified(self) -> bool:
        return self._customer_id is not None

    @property
    def customer_id(self) -> int | None:
        return self._customer_id

    def verify(self, contact: str, order_id: int | None = None) -> VerificationResult:
        """Verify with an email or phone, optionally tied to an order number.

        With an order number the contact must belong to that order's owner. Without one,
        the contact must match exactly one customer (an email shared by two customers
        is reported as ambiguous). Failures never say whether the order or the contact
        was the wrong part.
        """
        if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
            return VerificationResult(VerificationStatus.LOCKED)

        candidates = self._candidates(contact, order_id)
        if len(candidates) > 1:
            return VerificationResult(VerificationStatus.AMBIGUOUS)
        if not candidates:
            self._failed_attempts += 1
            return VerificationResult(VerificationStatus.FAILED)

        customer = candidates[0]
        self._customer_id = customer.customer_id
        return VerificationResult(VerificationStatus.VERIFIED, customer.name.split()[0])

    def order_for(self, order_id: int) -> Order | None:
        """The order, only if it belongs to the verified customer."""
        if self._customer_id is None:
            return None
        order = self._store.orders.get(order_id)
        return order if order and order.customer_id == self._customer_id else None

    def my_orders(self) -> list[Order]:
        if self._customer_id is None:
            return []
        return self._store.orders.by_customer(self._customer_id)

    def _candidates(self, contact: str, order_id: int | None) -> list[Customer]:
        if order_id is not None:
            order = self._store.orders.get(order_id)
            owner = self._store.customers.get(order.customer_id) if order else None
            return [owner] if owner and _contact_matches(owner, contact) else []
        if _is_email(contact):
            return self._store.customers.find_by_email(contact)
        return self._store.customers.find_by_phone(_phone_digits(contact))