import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

firehose = boto3.client("firehose")

CUSTOMER_ACTIVITY_STREAM_NAME = os.environ[
    "CUSTOMER_ACTIVITY_STREAM_NAME"
]

MAX_BATCH_RECORDS = 500
MAX_BATCH_SIZE_BYTES = 4 * 1024 * 1024


def create_activity_record(
    event_type: str,
    user_id: str,
    product_id: str | None = None,
    session_id: str | None = None,
    **extra_data: Any,
) -> dict[str, Any]:
    """Create a standardized customer activity event."""

    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "session_id": session_id or "unknown",
    }

    if product_id:
        record["product_id"] = product_id

    record.update(extra_data)

    return record


def send_customer_activity(
    event_type: str,
    user_id: str,
    product_id: str | None = None,
    session_id: str | None = None,
    **extra_data: Any,
) -> dict[str, Any]:
    """Send a single customer activity event to Firehose."""

    record = create_activity_record(
        event_type=event_type,
        user_id=user_id,
        product_id=product_id,
        session_id=session_id,
        **extra_data,
    )

    try:
        response = firehose.put_record(
            DeliveryStreamName=CUSTOMER_ACTIVITY_STREAM_NAME,
            Record={
                "Data": (
                    json.dumps(record) + "\n"
                ).encode("utf-8"),
            },
        )

        logger.info(
            "Customer activity sent: event_type=%s user_id=%s",
            event_type,
            user_id,
        )

        return response

    except Exception:
        logger.exception(
            "Failed to send customer activity: event_type=%s user_id=%s",
            event_type,
            user_id,
        )
        raise


def send_batch_activities(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Send multiple customer activity events using Firehose batches.

    Firehose allows up to 500 records and 4 MiB per request.
    Failed records are logged individually.
    """

    if not events:
        return {
            "total_records": 0,
            "successful_records": 0,
            "failed_records": 0,
        }

    records = []

    for event in events:
        record_data = create_activity_record(
            event_type=event["event_type"],
            user_id=event["user_id"],
            product_id=event.get("product_id"),
            session_id=event.get("session_id"),
            **{
                key: value
                for key, value in event.items()
                if key not in {
                    "event_type",
                    "user_id",
                    "product_id",
                    "session_id",
                }
            },
        )

        record_bytes = (
            json.dumps(record_data) + "\n"
        ).encode("utf-8")

        if len(record_bytes) > 1_000 * 1024:
            raise ValueError(
                "A Firehose record exceeds the 1000 KiB limit"
            )

        records.append({
            "Data": record_bytes,
        })

    total_records = len(records)
    successful_records = 0
    failed_records = 0

    try:
        # Split records into batches of at most 500,
        # while keeping each request within 4 MiB.
        batch = []
        batch_size = 0

        for record in records:
            record_size = len(record["Data"])

            if (
                len(batch) >= MAX_BATCH_RECORDS
                or batch_size + record_size > MAX_BATCH_SIZE_BYTES
            ):
                response = _put_record_batch(batch)

                successful_records += (
                    len(batch) - response["FailedPutCount"]
                )
                failed_records += response["FailedPutCount"]

                batch = []
                batch_size = 0

            batch.append(record)
            batch_size += record_size

        # Send remaining records.
        if batch:
            response = _put_record_batch(batch)

            successful_records += (
                len(batch) - response["FailedPutCount"]
            )
            failed_records += response["FailedPutCount"]

        logger.info(
            "Batch publishing completed: total=%s successful=%s failed=%s",
            total_records,
            successful_records,
            failed_records,
        )

        return {
            "total_records": total_records,
            "successful_records": successful_records,
            "failed_records": failed_records,
        }

    except Exception:
        logger.exception("Failed to publish customer activity batch")
        raise


def _put_record_batch(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send one Firehose batch and log individual failures."""

    response = firehose.put_record_batch(
        DeliveryStreamName=CUSTOMER_ACTIVITY_STREAM_NAME,
        Records=records,
    )

    if response["FailedPutCount"] > 0:
        logger.error(
            "Firehose failed to publish %s records",
            response["FailedPutCount"],
        )

        for index, result in enumerate(
            response["RequestResponses"]
        ):
            if "ErrorCode" in result:
                logger.error(
                    "Record %s failed: %s - %s",
                    index,
                    result["ErrorCode"],
                    result.get("ErrorMessage", "Unknown error"),
                )

    return response