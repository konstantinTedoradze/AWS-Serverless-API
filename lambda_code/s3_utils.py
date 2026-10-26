import boto3
import os
import uuid

s3_client = boto3.client("s3")


def upload_image(image_bytes, content_type):
    bucket_name = os.environ["PRODUCT_IMAGES_BUCKET"]

    extension = content_type.split("/")[-1]

    key = f"products/{uuid.uuid4()}.{extension}"

    s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=image_bytes,
        ContentType=content_type,
    )

    return key