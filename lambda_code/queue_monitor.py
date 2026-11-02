
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client("sqs")
cloudwatch = boto3.client("cloudwatch")

ORDER_QUEUE_URL = os.environ["ORDER_PROCESSING_QUEUE_URL"]


def monitor_queue_metrics(queue_url: str) -> dict[str, Any]:
    """Monitor SQS queue metrics for scaling decisions."""

    queue_name = queue_url.rstrip("/").split("/")[-1]

    # Get current SQS queue attributes
    response = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ],
    )

    attributes = response["Attributes"]

    visible_messages = int(
        attributes["ApproximateNumberOfMessages"]
    )

    in_flight_messages = int(
        attributes["ApproximateNumberOfMessagesNotVisible"]
    )

    # Retrieve CloudWatch metrics for the last 15 minutes
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=15)

    metrics = cloudwatch.get_metric_statistics(
        Namespace="AWS/SQS",
        MetricName="ApproximateNumberOfMessagesVisible",
        Dimensions=[
            {
                "Name": "QueueName",
                "Value": queue_name,
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=300,
        Statistics=["Average", "Maximum"],
    )

    datapoints = metrics.get("Datapoints", [])

    # Sort datapoints chronologically
    datapoints.sort(key=lambda point: point["Timestamp"])

    average_queue_depth = (
        sum(point["Average"] for point in datapoints)
        / len(datapoints)
        if datapoints
        else 0
    )

    max_queue_depth = (
        max(point["Maximum"] for point in datapoints)
        if datapoints
        else 0
    )

    return {
        "queue_name": queue_name,
        "visible_messages": visible_messages,
        "in_flight_messages": in_flight_messages,
        "average_queue_depth": average_queue_depth,
        "max_queue_depth": max_queue_depth,
    }


def scale_processing_capacity(
    queue_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Determine recommended processing capacity."""

    recommendations = []

    visible_messages = queue_metrics["visible_messages"]
    max_queue_depth = queue_metrics["max_queue_depth"]

    if visible_messages > 100:
        recommendations.append({
            "action": "scale_up",
            "reason": f"High queue depth: {visible_messages} messages",
            "suggested_capacity": min(
                visible_messages // 10,
                50,
            ),
        })

    elif max_queue_depth < 5 and visible_messages < 10:
        recommendations.append({
            "action": "scale_down",
            "reason": "Low queue utilization",
            "suggested_capacity": 2,
        })

    else:
        recommendations.append({
            "action": "maintain",
            "reason": "Queue utilization is within normal limits",
            "suggested_capacity": None,
        })

    return {
        "recommendations": recommendations,
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point for scheduled queue monitoring."""

    metrics = monitor_queue_metrics(ORDER_QUEUE_URL)

    scaling_decision = scale_processing_capacity(metrics)

    logger.info("Queue metrics: %s", metrics)
    logger.info("Scaling recommendations: %s", scaling_decision)

    return {
        "queue_metrics": metrics,
        "scaling_decision": scaling_decision,
    }
