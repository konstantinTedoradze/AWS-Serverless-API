
import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from notification_service import send_order_confirmation

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

PRODUCTS_TABLE_NAME = os.environ["PRODUCTS_TABLE_NAME"]
CUSTOMER_NOTIFICATIONS_TOPIC_ARN = os.environ.get(
    "CUSTOMER_NOTIFICATIONS_TOPIC_ARN"
)

products_table = dynamodb.Table(PRODUCTS_TABLE_NAME)


class OrderProcessingError(Exception):
    """Raised when an order cannot be processed."""


def handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """
    Process orders received from SQS.

    Each SQS message represents one order.
    Failed order processing is retried by SQS.
    """

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")

        try:
            order_data = json.loads(record["body"])
            order_id = order_data["order_id"]

            logger.info(
                "Starting order processing",
                extra={
                    "order_id": order_id,
                    "message_id": message_id,
                },
            )

            result = process_order_workflow(order_data)

            if not result["success"]:
                raise OrderProcessingError(result["error"])

            logger.info(
                "Order processed successfully: %s",
                order_id,
            )

            # Publish customer confirmation after successful processing.
            publish_order_confirmation(order_data)

        except Exception:
            logger.exception(
                "Failed to process SQS message: %s",
                message_id,
            )

            # Failed order processing is retried by SQS.
            raise

    return {
        "statusCode": 200,
        "body": json.dumps("Orders processed successfully"),
    }


def publish_order_confirmation(
    order_data: dict[str, Any],
) -> None:
    """
    Publish an order confirmation through SNS.

    Notification failures are logged separately so that an
    already-processed order is not processed again just because
    the notification service is temporarily unavailable.
    """

    if not CUSTOMER_NOTIFICATIONS_TOPIC_ARN:
        logger.warning(
            "Customer notification topic ARN is not configured. "
            "Skipping order confirmation."
        )
        return

    try:
        message_id = send_order_confirmation(
            order_data=order_data,
            topic_arn=CUSTOMER_NOTIFICATIONS_TOPIC_ARN,
        )

        logger.info(
            "Order confirmation published. Order ID: %s, "
            "SNS Message ID: %s",
            order_data["order_id"],
            message_id,
        )

    except Exception:
        logger.exception(
            "Failed to publish confirmation for order %s",
            order_data.get("order_id", "unknown"),
        )


def process_order_workflow(
    order_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute the order-processing workflow.

    Current implementation:
    1. Validate inventory.
    2. Payment integration (not implemented).
    3. Shipping integration (not implemented).

    Payment and shipping integrations must be implemented
    before production use.
    """

    try:
        order_id = order_data["order_id"]

        inventory_result = validate_inventory(
            order_data["items"]
        )

        if not inventory_result["available"]:
            return {
                "success": False,
                "error": inventory_result["reason"],
            }

        # TODO: Integrate a real payment provider.
        logger.warning(
            "Payment integration is not implemented for order %s",
            order_id,
        )

        # TODO: Integrate a real shipping provider.
        logger.warning(
            "Shipping integration is not implemented for order %s",
            order_id,
        )

        return {
            "success": False,
            "error": (
                "Payment and shipping integrations "
                "are not implemented yet"
            ),
        }

    except Exception as exc:
        logger.exception(
            "Order workflow failed: %s",
            order_data.get("order_id", "unknown"),
        )

        return {
            "success": False,
            "error": str(exc),
        }


def validate_inventory(
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Check whether all requested products have sufficient inventory.
    """

    try:
        for item in items:
            product_id = item["id"]
            requested_quantity = item["quantity"]

            response = products_table.get_item(
                Key={"id": product_id}
            )

            product = response.get("Item")

            if not product:
                return {
                    "available": False,
                    "reason": f"Product {product_id} was not found",
                }

            available_quantity = int(
                product.get("inventory_count", 0)
            )

            if available_quantity < requested_quantity:
                return {
                    "available": False,
                    "reason": (
                        f"Insufficient inventory for product "
                        f"{product_id}"
                    ),
                }

        return {"available": True}

    except ClientError:
        logger.exception(
            "DynamoDB inventory validation failed"
        )
        raise
