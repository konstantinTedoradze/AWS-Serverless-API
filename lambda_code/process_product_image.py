import json
import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3


# Initialize clients outside handler for reuse
s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

PRODUCTS_TABLE_NAME = os.environ["PRODUCTS_TABLE_NAME"]

product_table = dynamodb.Table(PRODUCTS_TABLE_NAME)


def handler(event, context):
    """
    Process product images uploaded to S3.

    Expected S3 key format:
        products/{product_id}/{image_type}.jpg

    Example:
        products/10f145c6-3c64-4506-a39d-6c6b570b3e85/main.jpg
    """

    for record in event.get("Records", []):
        try:
            # Get bucket name from S3 event
            bucket_name = record["s3"]["bucket"]["name"]

            # S3 event keys are URL encoded
            object_key = unquote_plus(
                record["s3"]["object"]["key"]
            )

            print(
                f"Processing uploaded image: "
                f"s3://{bucket_name}/{object_key}"
            )

            # Expected format:
            # products/{product_id}/{image_type}.jpg
            key_parts = object_key.split("/")

            if len(key_parts) != 3 or key_parts[0] != "products":
                print(
                    f"Skipping unexpected object key: {object_key}"
                )
                continue

            product_id = key_parts[1]
            image_name = key_parts[2]

            # Get metadata without downloading the image
            response = s3_client.head_object(
                Bucket=bucket_name,
                Key=object_key,
            )

            file_size = response["ContentLength"]
            content_type = response.get(
                "ContentType",
                "application/octet-stream",
            )

            upload_date = datetime.now(
                timezone.utc
            ).isoformat()

            # Update product record in DynamoDB
            product_table.update_item(
                Key={
                    "id": product_id,
                },
                UpdateExpression="""
                    SET image_key = :image_key,
                        image_name = :image_name,
                        image_file_size = :file_size,
                        image_content_type = :content_type,
                        image_upload_date = :upload_date
                """,
                ExpressionAttributeValues={
                    ":image_key": object_key,
                    ":image_name": image_name,
                    ":file_size": file_size,
                    ":content_type": content_type,
                    ":upload_date": upload_date,
                },
            )

            print(
                f"Successfully processed image for product "
                f"{product_id}"
            )

        except Exception as exc:
            print(
                f"Error processing S3 record: {exc}"
            )
            raise

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Image metadata processed successfully"
            }
        ),
    }