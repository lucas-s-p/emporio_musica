import pytest

from emporio.data import Store
from emporio.services.identity import (
    MAX_FAILED_ATTEMPTS,
    CustomerVerifier,
    VerificationStatus,
)

SHARED_EMAIL = "bruno.martins@jmail.com"  # customers 11 and 43


@pytest.fixture
def verifier(store: Store) -> CustomerVerifier:
    return CustomerVerifier(store)


def test_unverified_sees_nothing(verifier: CustomerVerifier) -> None:
    assert not verifier.is_verified
    assert verifier.order_for(4) is None
    assert verifier.my_orders() == []


def test_verify_with_phone_only(store: Store, verifier: CustomerVerifier) -> None:
    result = verifier.verify("(67) 99812-3456")
    assert result.status is VerificationStatus.VERIFIED
    assert result.first_name == "Lucas"
    assert verifier.customer_id == 1
    assert [o.order_id for o in verifier.my_orders()] == [4]


def test_phone_with_country_code_and_no_formatting(verifier: CustomerVerifier) -> None:
    assert verifier.verify("+55 67 99812-3456").status is VerificationStatus.VERIFIED


def test_shared_email_alone_is_ambiguous(verifier: CustomerVerifier) -> None:
    assert verifier.verify(SHARED_EMAIL).status is VerificationStatus.AMBIGUOUS
    assert not verifier.is_verified


def test_shared_email_with_order_resolves_owner(verifier: CustomerVerifier) -> None:
    result = verifier.verify(SHARED_EMAIL.upper(), order_id=10)  # order 10 is customer 11's
    assert result.status is VerificationStatus.VERIFIED
    assert verifier.customer_id == 11
    assert verifier.order_for(10) is not None


def test_cannot_read_someone_elses_order(verifier: CustomerVerifier) -> None:
    verifier.verify("(67) 99812-3456")  # customer 1
    assert verifier.order_for(4) is not None
    assert verifier.order_for(1) is None  # belongs to customer 3
    assert verifier.order_for(9999) is None


def test_wrong_contact_for_order_fails(verifier: CustomerVerifier) -> None:
    result = verifier.verify("lucas.mendes@jmail.com", order_id=1)  # order 1 is customer 3's
    assert result.status is VerificationStatus.FAILED
    assert not verifier.is_verified


def test_unknown_order_fails_like_wrong_contact(verifier: CustomerVerifier) -> None:
    assert verifier.verify("lucas.mendes@jmail.com", order_id=9999).status is (
        VerificationStatus.FAILED
    )


def test_lockout_after_repeated_failures(store: Store, verifier: CustomerVerifier) -> None:
    for _ in range(MAX_FAILED_ATTEMPTS):
        assert verifier.verify("nobody@example.com").status is VerificationStatus.FAILED
    # Even correct credentials are refused once locked.
    assert verifier.verify("(67) 99812-3456").status is VerificationStatus.LOCKED
    assert not verifier.is_verified


def test_ambiguous_does_not_count_as_failure(verifier: CustomerVerifier) -> None:
    for _ in range(MAX_FAILED_ATTEMPTS + 1):
        assert verifier.verify(SHARED_EMAIL).status is VerificationStatus.AMBIGUOUS