
import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns = boto3.client("sns")

STORE_URL = os.environ.get(
    "STORE_URL",
    "https://store.example.com",
)


def send_order_confirmation(
    order_data: dict[str, Any],
    topic_arn: str,
) -> str:
    """Publish a multi-format order confirmation through SNS."""

    required_fields = [
        "order_id",
        "total_amount",
        "items",
    ]

    for field in required_fields:
        if field not in order_data:
            raise ValueError(f"Missing required field: {field}")

    order_id = str(order_data["order_id"])
    total_amount = float(order_data["total_amount"])

    # Create messages for different delivery protocols.
    message = {
        "default": (
            f"Order {order_id} confirmed. "
            f"Total: ${total_amount:.2f}"
        ),
        "email": create_email_message(order_data),
        "sms": create_sms_message(order_data),
    }

    # SNS message attributes allow subscription filtering.
    message_attributes = {
        "order_type": {
            "DataType": "String",
            "StringValue": str(
                order_data.get("order_type", "standard")
            ),
        },
        "customer_tier": {
            "DataType": "String",
            "StringValue": str(
                order_data.get("customer_tier", "regular")
            ),
        },
        "notification_preference": {
            "DataType": "String",
            "StringValue": str(
                order_data.get("notification_preference", "all")
            ),
        },
    }

    response = sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(message),
        MessageStructure="json",
        Subject=f"Order Confirmation - {order_id}",
        MessageAttributes=message_attributes,
    )

    message_id = response["MessageId"]

    logger.info(
        "Order confirmation published. Order ID: %s, Message ID: %s",
        order_id,
        message_id,
    )

    return message_id


def create_email_message(
    order_data: dict[str, Any],
) -> str:
    """Create a formatted email order confirmation."""

    items_list = "\n".join(
        [
            (
                f"- {item['title']} "
                f"(Qty: {item['quantity']}) "
                f"- ${float(item['price']):.2f}"
            )
            for item in order_data["items"]
        ]
    )

    order_id = order_data["order_id"]

    return f"""
Dear {order_data.get('customer_name', 'Customer')},

Thank you for your order! Here are the details:

Order ID: {order_id}
Order Date: {order_data.get('order_date', 'N/A')}

Items Ordered:
{items_list}

Total Amount: ${float(order_data['total_amount']):.2f}

Estimated Delivery: {order_data.get('estimated_delivery', 'TBD')}

You can track your order at:
{STORE_URL}/orders/{order_id}

Thank you for shopping with us!
""".strip()


def create_sms_message(
    order_data: dict[str, Any],
) -> str:
    """Create a concise SMS order confirmation."""

    order_id = order_data["order_id"]
    total_amount = float(order_data["total_amount"])

    return (
        f"Order {order_id} confirmed! "
        f"Total: ${total_amount:.2f}. "
        f"Track at: {STORE_URL}/track/{order_id}"
    )
