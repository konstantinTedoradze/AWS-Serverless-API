import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def notification_dispatcher_handler(event, context):
    """Dispatch notifications based on SNS messages."""

    for record in event.get("Records", []):
        sns_message = json.loads(record["Sns"]["Message"])
        message_attributes = record["Sns"].get("MessageAttributes", {})

        notification_type = (
            message_attributes.get("notification_type", {}).get("Value", "general")
        )

        if notification_type == "order_confirmation":
            logger.info("Dispatching order confirmation")

        elif notification_type == "inventory_alert":
            logger.info("Dispatching inventory alert")

        elif notification_type == "system_alert":
            logger.info("Dispatching system alert")

        else:
            logger.warning(
                "Unknown notification type: %s",
                notification_type,
            )

    return {
        "statusCode": 200,
        "body": "Notifications dispatched",
    }