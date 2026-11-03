import json
from datetime import date

import pytest

from emporio.data import Store
from emporio.services.clock import build_clock
from emporio.tools import ToolRegistry, build_registry
from emporio.tools.base import Tool, ToolInput


def make(store: Store, today: date = date(2026, 11, 3)) -> ToolRegistry:
    return build_registry(store, build_clock(today))


@pytest.fixture
def registry(store: Store) -> ToolRegistry:
    return make(store)


def verified(store: Store, customer_id: int, today: date = date(2026, 11, 3)) -> ToolRegistry:
    reg = make(store, today)
    customer = store.customers.get(customer_id)
    assert customer is not None
    assert reg.execute("verify_customer", {"contact": customer.phone})["status"] == "verified"
    return reg


# --- framework ------------------------------------------------------------------------------


def test_all_tools_are_exposed_with_valid_specs(registry: ToolRegistry) -> None:
    assert set(registry.names) == {
        "search_products", "get_product", "get_payment_options", "estimate_shipping",
        "get_store_info", "verify_customer", "get_order_status", "check_return_eligibility",
    }  # fmt: skip
    for spec in registry.specs():
        function = spec["function"]
        assert spec["type"] == "function" and function["description"]
        assert function["parameters"]["type"] == "object"
        json.dumps(spec)  # serializable, with no $ref left behind
        assert "$ref" not in json.dumps(spec)


def test_unknown_tool(registry: ToolRegistry) -> None:
    result = registry.execute("drop_tables", {})
    assert result["error"] == "UNKNOWN_TOOL" and "search_products" in result["available_tools"]


def test_invalid_json_and_wrong_types(registry: ToolRegistry) -> None:
    assert registry.execute("get_product", "{not json")["error"] == "INVALID_ARGUMENTS"
    assert registry.execute("get_product", "[1]")["error"] == "INVALID_ARGUMENTS"
    bad = registry.execute("get_product", {"product_id": "abc"})
    assert bad["error"] == "INVALID_ARGUMENTS" and bad["problems"][0]["field"] == "product_id"


def test_unknown_arguments_are_rejected(registry: ToolRegistry) -> None:
    assert registry.execute("get_product", {"product_id": 95, "x": 1})["error"] == (
        "INVALID_ARGUMENTS"
    )


def test_string_arguments_are_accepted_and_coerced(registry: ToolRegistry) -> None:
    result = registry.execute("get_product", '{"product_id": "95"}')
    assert result["product_id"] == 95


def test_internal_errors_do_not_leak(store: Store) -> None:
    class Empty(ToolInput):
        pass

    def boom(_: object) -> dict[str, object]:
        raise RuntimeError("secret internals")

    reg = ToolRegistry([Tool("boom", "x", Empty, boom)])
    assert reg.execute("boom") == {"error": "INTERNAL_ERROR"}


def test_execute_json_is_complete_utf8(registry: ToolRegistry) -> None:
    text = registry.execute_json("search_products", {"query": "violão", "limit": 15})
    assert "Violões" in text and "\\u" not in text
    assert json.loads(text)["returned"] == 15


# --- products -------------------------------------------------------------------------------


def test_price_query(registry: ToolRegistry) -> None:
    result = registry.execute("search_products", {"query": "Takamine GD20"})
    (product,) = result["products"]
    assert product["price"] == "2199.00" and product["pix_price"] == "2089.05"
    assert product["pix_discount_applies"] is True and product["promotion"] is None


def test_promotion_is_applied_and_pix_does_not_stack(registry: ToolRegistry) -> None:
    product = registry.execute("get_product", {"product_id": 121})
    assert product["price"] == "439.20" and product["pix_price"] == "439.20"
    assert product["promotion"] == {"name": "Desconto Exclusivo", "percent": 20}
    assert product["pix_discount_applies"] is False


def test_inactive_promotion_is_not_offered(registry: ToolRegistry) -> None:
    product = registry.execute("get_product", {"product_id": 102})  # promotion 1 is inactive
    assert product["promotion"] is None and product["price"] == product["list_price"]


def test_catalog_query_with_budget(registry: ToolRegistry) -> None:
    result = registry.execute("search_products", {"query": "violão", "max_price_brl": 1000})
    assert result["products"]
    assert all(float(p["price"]) <= 1000 for p in result["products"])
    assert all(p["availability"] == "in_stock" for p in result["products"])
    assert result["hidden_unavailable_matches"] >= 1


def test_out_of_stock_product_gets_alternatives(registry: ToolRegistry) -> None:
    product = registry.execute("get_product", {"product_id": 96})
    assert product["availability"] == "out_of_stock" and product["stock_quantity"] is None
    assert len(product["alternatives"]) == 3
    assert all(a["availability"] == "in_stock" for a in product["alternatives"])


def test_in_stock_product_has_no_alternatives(registry: ToolRegistry) -> None:
    assert "alternatives" not in registry.execute("get_product", {"product_id": 95})


def test_search_errors(registry: ToolRegistry) -> None:
    assert registry.execute("search_products", {})["error"] == "EMPTY_SEARCH"
    assert registry.execute("get_product", {"product_id": 9999})["error"] == "PRODUCT_NOT_FOUND"
    unknown = registry.execute("search_products", {"category": "cavaquinhos"})
    assert unknown["error"] == "UNKNOWN_CATEGORY" and "Violões" in unknown["categories"]


def test_accessories_are_refused_by_the_tool(registry: ToolRegistry) -> None:
    result = registry.execute("search_products", {"query": "cordas de nylon"})
    assert result["error"] == "ACCESSORY_NOT_SOLD"
    assert "error" not in registry.execute("search_products", {"query": "violão 7 cordas"})


# --- payment and shipping -------------------------------------------------------------------


def test_installments_respect_the_minimum_value(registry: ToolRegistry) -> None:
    result = registry.execute("get_payment_options", {"items": [{"product_id": 119}]})
    assert result["card_total"] == "159.90"
    assert [o["count"] for o in result["installments_interest_free"]] == [1, 2, 3]
    assert result["can_combine_payment_methods"] is False


def test_cart_total_is_computed_in_code(registry: ToolRegistry) -> None:
    result = registry.execute(
        "get_payment_options", {"items": [{"product_id": 119, "quantity": 2}]}
    )
    assert (
        result["card_total"] == "319.80" and result["pix_total"] == "303.82"
    )  # 2 x 151.91 (PIX rounded per unit)


def test_high_value_cart_gets_12x_and_combined_payment(registry: ToolRegistry) -> None:
    result = registry.execute("get_payment_options", {"items": [{"product_id": 94}]})
    assert result["card_total"] == "5519.08"  # 8% promotion
    assert result["installments_interest_free"][-1] == {"count": 12, "value": "459.92"}
    assert result["can_combine_payment_methods"] is True


def test_shipping_in_campo_grande(registry: ToolRegistry) -> None:
    cheap = registry.execute(
        "estimate_shipping", {"items": [{"product_id": 119}], "city": "campo grande"}
    )
    assert cheap["fee"] == "35.00" and cheap["free_shipping"] is False
    big = registry.execute(
        "estimate_shipping", {"items": [{"product_id": 95}], "city": "Campo Grande"}
    )
    assert big["fee"] == "0.00" and big["free_shipping"] is True


def test_shipping_to_another_city_has_no_fixed_fee(registry: ToolRegistry) -> None:
    result = registry.execute(
        "estimate_shipping", {"items": [{"product_id": 95}], "city": "Dourados"}
    )
    assert result["fee"] is None and result["metro_area"] is False
    assert "SEDEX (Correios)" in result["carrier_options"]


def test_large_instrument_needs_special_quote(registry: ToolRegistry) -> None:
    result = registry.execute(
        "estimate_shipping", {"items": [{"product_id": 140}], "city": "Campo Grande"}
    )
    assert result["special_quote_required"] is True


def test_cart_with_unknown_or_unavailable_product(registry: ToolRegistry) -> None:
    missing = registry.execute("get_payment_options", {"items": [{"product_id": 9999}]})
    assert missing["error"] == "PRODUCT_NOT_FOUND"
    flagged = registry.execute("get_payment_options", {"items": [{"product_id": 96}]})
    assert flagged["unavailable_product_ids"] == [96]


# --- store info -----------------------------------------------------------------------------


def test_store_open_on_a_business_day(registry: ToolRegistry) -> None:
    info = registry.execute("get_store_info")
    assert info["today"] == "2026-11-03" and info["weekday"] == "tuesday"
    assert info["is_open_now"] is True and info["closed_reason"] is None
    assert info["weekly_hours"]["saturday"] == "09:00-13:00"
    assert info["weekly_hours"]["sunday"] == "closed"
    assert info["phone"] == "(67) 3341-4444"


def test_store_closed_on_holiday(store: Store) -> None:
    info = make(store, date(2026, 11, 2)).execute("get_store_info")  # Finados
    assert info["is_open_now"] is False and info["closed_reason"] == "HOLIDAY"
    assert (
        info["next_opens_at"].startswith("2026-11-03T09:00")
        and info["next_opens_weekday"] == "tuesday"
    )


def test_store_closed_on_sunday(store: Store) -> None:
    info = make(store, date(2026, 11, 1)).execute("get_store_info")
    assert info["closed_reason"] == "NON_BUSINESS_DAY"


# --- identity and orders --------------------------------------------------------------------


def test_orders_require_verification(registry: ToolRegistry) -> None:
    assert registry.execute("get_order_status", {"order_id": 4})["error"] == "NOT_VERIFIED"
    assert registry.execute("get_order_status")["error"] == "NOT_VERIFIED"
    assert (
        registry.execute("check_return_eligibility", {"order_id": 4, "reason": "regret"})["error"]
        == "NOT_VERIFIED"
    )


def test_verify_never_leaks_personal_data(store: Store, registry: ToolRegistry) -> None:
    result = registry.execute("verify_customer", {"contact": "(67) 99812-3456"})
    assert result == {"status": "verified", "first_name": "Lucas"}


def test_shared_email_asks_for_the_order_number(registry: ToolRegistry) -> None:
    result = registry.execute("verify_customer", {"contact": "bruno.martins@jmail.com"})
    assert result == {"status": "ambiguous", "next_step": "ASK_ORDER_NUMBER"}
    resolved = registry.execute(
        "verify_customer", {"contact": "bruno.martins@jmail.com", "order_id": 10}
    )
    assert resolved["status"] == "verified"


def test_other_customers_order_looks_like_a_missing_one(store: Store) -> None:
    reg = verified(store, 1)
    assert reg.execute("get_order_status", {"order_id": 4})["order_id"] == 4
    foreign = reg.execute("get_order_status", {"order_id": 1})  # belongs to customer 3
    missing = reg.execute("get_order_status", {"order_id": 9999})
    assert foreign == missing == {"error": "ORDER_NOT_FOUND"}
    assert reg.execute("check_return_eligibility", {"order_id": 1, "reason": "regret"}) == foreign


def test_order_status_payload(store: Store) -> None:
    order = verified(store, 1).execute("get_order_status", {"order_id": 4})
    assert order["status"] == "delivered" and order["total"] == "799.90"
    assert order["items"] == [
        {"product_id": 96, "name": "Giannini GF-3D Dreadnought Sunburst", "quantity": 1}
    ]
    assert order["signals"] == []


def test_order_list_and_signals(store: Store) -> None:
    result = verified(store, 2).execute("get_order_status")  # customer 2 owns order 8 (shipped)
    (order,) = result["orders"]
    assert order["signals"] == ["DELIVERY_ESTIMATE_OVERDUE"] and order["days_overdue"] == 248
    assert order["store_contact"]["phone"] == "(67) 3341-4444"


def test_verification_locks_after_repeated_failures(registry: ToolRegistry) -> None:
    for _ in range(3):
        assert (
            registry.execute("verify_customer", {"contact": "ninguem@jmail.com"})["status"]
            == "failed"
        )
    locked = registry.execute("verify_customer", {"contact": "(67) 99812-3456"})
    assert locked["status"] == "locked" and locked["next_step"] == "REFER_TO_STORE_CONTACT"


def test_return_within_regret_window(store: Store) -> None:
    reg = verified(store, 14, today=date(2026, 2, 20))  # order 7, estimated delivery 2026-02-17
    result = reg.execute("check_return_eligibility", {"order_id": 7, "reason": "regret"})
    assert result["eligible"] is True and result["deadline"] == "2026-02-24"
    assert result["days_remaining"] == 4 and result["today"] == "2026-02-20"
    assert "RETURN_SHIPPING_PAID_BY_STORE" in result["conditions"]


def test_return_expired_with_today_from_the_clock(store: Store) -> None:
    reg = verified(store, 14)  # today = 2026-11-03
    result = reg.execute("check_return_eligibility", {"order_id": 7, "reason": "defect"})
    assert result["eligible"] is False and result["outcome"] == "expired"
    assert result["alternatives"] == ["MANUFACTURER_WARRANTY"]


def test_return_reason_must_be_valid(store: Store) -> None:
    reg = verified(store, 14)
    assert reg.execute("check_return_eligibility", {"order_id": 7, "reason": "boredom"})[
        "error"
    ] == ("INVALID_ARGUMENTS")


def test_conversations_do_not_share_identity(store: Store) -> None:
    first = verified(store, 1)
    second = make(store)
    assert first.execute("get_order_status", {"order_id": 4})["order_id"] == 4
    assert second.execute("get_order_status", {"order_id": 4})["error"] == "NOT_VERIFIED"
