import boto3
import logging
import os
from datetime import datetime, timezone
from notification_service import send_inventory_alert

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

PRODUCTS_TABLE_NAME = os.environ["PRODUCTS_TABLE_NAME"]
INVENTORY_ALERTS_TOPIC_ARN = os.environ["INVENTORY_ALERTS_TOPIC_ARN"]

products_table = dynamodb.Table(PRODUCTS_TABLE_NAME)


def inventory_monitor_handler(event, context):
    """Monitor inventory levels and send alerts when stock is low."""

    response = products_table.scan(
        FilterExpression="inventory_count <= reorder_level"
    )

    low_stock_products = response.get("Items", [])

    for product in low_stock_products:
        message_id = send_inventory_alert(
            product,
            INVENTORY_ALERTS_TOPIC_ARN,
        )

        if message_id:
            products_table.update_item(
                Key={"id": product["id"]},
                UpdateExpression="SET last_inventory_alert = :timestamp",
                ExpressionAttributeValues={
                    ":timestamp": datetime.now(timezone.utc).isoformat()
                },
            )

    return {
        "statusCode": 200,
        "body": f"Processed {len(low_stock_products)} low stock alerts",
    }