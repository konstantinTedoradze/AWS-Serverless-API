import boto3
import json
import os
from botocore.exceptions import ClientError
from botocore.config import Config


# Initialize S3 client outside handler for reuse
s3_client = boto3.client(
    "s3",
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "virtual"},
    ),
)


def handler(event, context):
    try:
        product_images_bucket = os.environ["PRODUCT_IMAGES_BUCKET"]

        # Extract product ID from the URL
        path_parameters = event.get("pathParameters") or {}
        product_id = path_parameters.get("id")

        if not product_id:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({
                    "error": "Product id is required"
                }),
            }

        # Extract image type from query parameters
        query_parameters = event.get("queryStringParameters") or {}
        image_type = query_parameters.get("type", "main")

        # Generate S3 object key
        object_key = f"products/{product_id}/{image_type}.jpg"

        # Generate presigned URL
        expires_in = 3600

        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": product_images_bucket,
                "Key": object_key,
                "ContentType": "image/jpeg",
            },
            ExpiresIn=expires_in,
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "upload_url": presigned_url,
                "object_key": object_key,
                "expires_in": expires_in,
            }),
        }

    except ClientError as e:
        print(f"S3 error: {str(e)}")

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "error": "Failed to generate upload URL",
            }),
        }

    except Exception as e:
        print(f"Unexpected error: {str(e)}")

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "error": "Internal server error",
            }),
        }