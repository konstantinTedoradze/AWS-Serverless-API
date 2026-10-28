
from typing import Any, Callable

from lambda_code.retry_utils import retry_with_exponential_backoff


def process_order(
    order_data: dict[str, Any],
    *,
    process_payment: Callable[[dict[str, Any]], dict[str, Any]],
    get_shipping_rate: Callable[[str, dict[str, Any]], Any],
    get_estimated_shipping_rate: Callable[[dict[str, Any]], Any],
    update_inventory: Callable[[list[dict[str, Any]]], None],
    queue_inventory_update: Callable[[list[dict[str, Any]]], None],
    send_confirmation_email: Callable[[str, str], None],
    queue_email: Callable[[str, str], None],
) -> dict[str, Any]:
    """Process an order with retries and graceful degradation."""

    order_id = order_data["order_id"]
    warnings: list[str] = []

    # 1. Payment is critical: do not continue if it fails.
    try:
        payment_result = retry_with_exponential_backoff(
            lambda: process_payment(order_data["payment"]),
            max_retries=3,
        )
    except Exception:
        return {
            "status": "failed",
            "error": "Payment processing failed",
            "order_id": order_id,
        }

    # 2. Shipping: fall back to an estimated rate if the provider fails.
    try:
        shipping_rate = retry_with_exponential_backoff(
            lambda: get_shipping_rate(
                order_id, order_data["destination"]
            ),
            max_retries=2,
        )
    except Exception:
        try:
            shipping_rate = get_estimated_shipping_rate(
                order_data["destination"]
            )
            warnings.append("Estimated shipping rate used")
        except Exception:
            # Payment may already have succeeded. Do not report the
            # order as unpaid or encourage the customer to pay again.
            return {
                "status": "paid_pending_fulfillment",
                "order_id": order_id,
                "payment_id": payment_result["transaction_id"],
                "error": "Shipping rate unavailable; fulfillment is pending",
            }

    # 3. Inventory: try synchronously, then enqueue for later processing.
    try:
        update_inventory(order_data["items"])
    except Exception:
        try:
            queue_inventory_update(order_data["items"])
            warnings.append("Inventory update queued for retry")
        except Exception:
            warnings.append("Inventory update could not be queued")

    # 4. Confirmation email: try synchronously, then enqueue.
    try:
        send_confirmation_email(
            order_data["customer_email"], order_id
        )
    except Exception:
        try:
            queue_email(order_data["customer_email"], order_id)
            warnings.append("Confirmation email queued for retry")
        except Exception:
            warnings.append("Confirmation email could not be queued")

    return {
        "status": "success",
        "order_id": order_id,
        "payment_id": payment_result["transaction_id"],
        "shipping_rate": shipping_rate,
        "warnings": warnings,
    }
