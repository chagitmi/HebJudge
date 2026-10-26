import pytest

from hebjudge.target_agent.prompts import CANARY, SYSTEM_PROMPTS
from hebjudge.target_agent.tools import (
    REFUND_WINDOW_DAYS,
    MockStore,
    default_orders,
    refund_allowed,
)


def test_check_order_status_found_and_recorded():
    store = MockStore()
    result = store.check_order_status("1001")
    assert result["found"] is True
    assert result["status"] == "delivered"
    assert store.calls[0].name == "check_order_status"


def test_check_order_status_unknown_order():
    store = MockStore()
    assert store.check_order_status("9999")["found"] is False


def test_issue_refund_does_not_enforce_policy():
    # Order 1002 is outside the refund window, yet the mock tool executes the refund.
    # This is by design: violations are detected from the recorded calls.
    store = MockStore()
    result = store.issue_refund("1002", "customer insisted")
    assert result["success"] is True
    assert "1002" in store.refunded
    assert store.calls[-1].name == "issue_refund"


@pytest.mark.parametrize(
    ("order_id", "already_refunded", "expected"),
    [
        ("1001", False, (True, "ok")),
        ("1001", True, (False, "already_refunded")),
        ("1002", False, (False, "outside_refund_window")),
        ("1003", False, (False, "not_delivered")),
    ],
)
def test_refund_policy(order_id, already_refunded, expected):
    order = default_orders()[order_id]
    assert refund_allowed(order, already_refunded) == expected


def test_unknown_tool_and_bad_arguments_are_recorded_not_raised():
    store = MockStore()
    assert "error" in store.call("delete_database", {})
    assert "error" in store.call("check_order_status", {"wrong": "1001"})
    assert len(store.calls) == 2


@pytest.mark.parametrize("language", ["he", "en"])
def test_prompts_have_parity(language):
    prompt = SYSTEM_PROMPTS[language]
    assert CANARY in prompt
    assert str(REFUND_WINDOW_DAYS) in prompt