
import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns = boto3.client("sns")


def publish_notification(
    topic_arn: str,
    subject: str,
    message: dict[str, Any],
) -> str:
    """Publish a notification to an SNS topic."""

    if not topic_arn:
        raise ValueError("SNS topic ARN is required")

    response = sns.publish(
        TopicArn=topic_arn,
        Subject=subject[:100],
        Message=json.dumps(message),
    )

    message_id = response["MessageId"]

    logger.info(
        "SNS notification published: %s",
        message_id,
    )

    return message_id


def send_customer_notification(
    order_id: str,
    customer_email: str,
    status: str,
) -> str:
    topic_arn = os.environ["CUSTOMER_NOTIFICATIONS_TOPIC_ARN"]

    return publish_notification(
        topic_arn=topic_arn,
        subject=f"Order {order_id} update",
        message={
            "type": "order_update",
            "order_id": order_id,
            "customer_email": customer_email,
            "status": status,
        },
    )


def send_system_alert(
    title: str,
    description: str,
) -> str:
    topic_arn = os.environ["SYSTEM_ALERTS_TOPIC_ARN"]

    return publish_notification(
        topic_arn=topic_arn,
        subject=title,
        message={
            "type": "system_alert",
            "title": title,
            "description": description,
        },
    )


def send_inventory_alert(
    product_data: dict[str, Any],
    topic_arn: str,
) -> str:
    """Publish a low-inventory alert through SNS."""

    required_fields = ["title", "inventory_count", "category"]

    for field in required_fields:
        if field not in product_data:
            raise ValueError(f"Missing required field: {field}")

    inventory_count = int(product_data["inventory_count"])

    alert_message = {
        "default": (
            f"Low stock: {product_data['title']} "
            f"({inventory_count} remaining)"
        ),
        "email": (
            f"Inventory alert for {product_data['title']}: "
            f"{inventory_count} units remaining. "
            f"Reorder level: {product_data.get('reorder_level', 10)}."
        ),
    }

    message_attributes = {
        "alert_type": {
            "DataType": "String",
            "StringValue": "inventory_low",
        },
        "product_category": {
            "DataType": "String",
            "StringValue": str(product_data["category"]),
        },
        "urgency": {
            "DataType": "String",
            "StringValue": (
                "high" if inventory_count == 0 else "medium"
            ),
        },
    }

    response = sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(alert_message),
        MessageStructure="json",
        Subject=f"Inventory Alert: {product_data['title']}",
        MessageAttributes=message_attributes,
    )

    message_id = response["MessageId"]

    logger.info(
        "Inventory alert published. Product: %s, Message ID: %s",
        product_data["title"],
        message_id,
    )

    return message_id