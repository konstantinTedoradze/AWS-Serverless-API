
import boto3
import json
import os
from botocore.exceptions import ClientError
from botocore.config import Config


# Initialize S3 client outside the handler
s3_client = boto3.client(
    "s3",
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "virtual"},
    ),
)


def handler(event, context):
    product_image_bucket = os.environ["PRODUCT_IMAGES_BUCKET"]

    path_parameters = event.get("pathParameters") or {}
    product_id = path_parameters.get("id")

    if not product_id:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Product id is required"}),
        }

    query_parameters = event.get("queryStringParameters") or {}
    image_type = query_parameters.get("type", "main")

    # Only allow known image types
    if image_type not in ("main", "thumbnail"):
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid image type"}),
        }

    object_key = f"products/{product_id}/{image_type}.jpg"

    try:
        # Confirm the image exists before returning a download URL
        s3_client.head_object(
            Bucket=product_image_bucket,
            Key=object_key,
        )

        download_url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": product_image_bucket,
                "Key": object_key,
            },
            ExpiresIn=3600,
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "download_url": download_url,
                "object_key": object_key,
                "expires_in": 3600,
            }),
        }

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")

        print(f"S3 error: {error_code}")

        if error_code in ("404", "NoSuchKey", "NotFound"):
            status_code = 404
            message = "Image not found"
        else:
            status_code = 500
            message = "Failed to generate download URL"

        return {
            "statusCode": status_code,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": message}),
        }
