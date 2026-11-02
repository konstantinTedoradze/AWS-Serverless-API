import json
from datetime import datetime, timezone
from typing import Any

import boto3


sqs = boto3.client("sqs")


def send_order_to_queue(
    order_data: dict[str, Any],
    queue_url: str,
) -> str:
    """Send an order to the background processing queue."""

    message_body = {
        "order_id": order_data["order_id"],
        "customer_id": order_data["customer_id"],
        "items": order_data["items"],
        "total_amount": order_data["total_amount"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "processing_steps": [
            "validate_inventory",
            "process_payment",
            "create_shipping_label",
            "send_confirmation",
        ],
    }

    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message_body),
        MessageAttributes={
            "order_priority": {
                "StringValue": order_data.get("priority", "standard"),
                "DataType": "String",
            },
            "customer_tier": {
                "StringValue": order_data.get("customer_tier", "regular"),
                "DataType": "String",
            },
        },
    )

    return response["MessageId"]