
from unittest.mock import Mock

from lambda_code.order_processing import process_order


def make_order():
    return {
        "order_id": "order-001",
        "payment": {"amount": 100},
        "destination": {"country": "Georgia"},
        "items": [{"product_id": "prod-001", "quantity": 1}],
        "customer_email": "customer@example.com",
    }


def make_services():
    return {
        "process_payment": Mock(
            return_value={"transaction_id": "txn-001"}
        ),
        "get_shipping_rate": Mock(return_value=12.5),
        "get_estimated_shipping_rate": Mock(return_value=15.0),
        "update_inventory": Mock(),
        "queue_inventory_update": Mock(),
        "send_confirmation_email": Mock(),
        "queue_email": Mock(),
    }


def test_successful_order():
    services = make_services()

    result = process_order(make_order(), **services)

    assert result["status"] == "success"
    assert result["payment_id"] == "txn-001"
    assert result["shipping_rate"] == 12.5
    assert result["warnings"] == []


def test_payment_failure_stops_order():
    services = make_services()
    services["process_payment"].side_effect = RuntimeError("Payment failed")

    result = process_order(make_order(), **services)

    assert result["status"] == "failed"
    services["get_shipping_rate"].assert_not_called()
    services["update_inventory"].assert_not_called()


def test_shipping_uses_estimate_when_provider_fails():
    services = make_services()
    services["get_shipping_rate"].side_effect = RuntimeError("Unavailable")

    result = process_order(make_order(), **services)

    assert result["status"] == "success"
    assert result["shipping_rate"] == 15.0
    assert "Estimated shipping rate used" in result["warnings"]


def test_inventory_failure_queues_update():
    services = make_services()
    services["update_inventory"].side_effect = RuntimeError("Unavailable")

    result = process_order(make_order(), **services)

    assert result["status"] == "success"
    services["queue_inventory_update"].assert_called_once()
    assert "Inventory update queued for retry" in result["warnings"]


def test_email_failure_queues_email():
    services = make_services()
    services["send_confirmation_email"].side_effect = RuntimeError(
        "Unavailable"
    )

    result = process_order(make_order(), **services)

    assert result["status"] == "success"
    services["queue_email"].assert_called_once()
    assert "Confirmation email queued for retry" in result["warnings"]
