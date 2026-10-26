
import json
import os

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
product_table = dynamodb.Table(os.environ["PRODUCT_TABLE"])


def handler(event, context):
    try:
        product_id = event["pathParameters"]["id"]

        body = event.get("body")
        if isinstance(body, str):
            body = json.loads(body)
        elif body is None:
            body = {}

        image_key = body.get("image_key")

        if not image_key:
            return response(400, {"error": "image_key is required"})

        expected_prefix = f"products/{product_id}/"
        if not image_key.startswith(expected_prefix):
            return response(400, {"error": "Invalid image key"})

        result = product_table.update_item(
            Key={"id": product_id},
            UpdateExpression="SET image_keys = list_append("
                             "if_not_exists(image_keys, :empty), :new)",
            ExpressionAttributeValues={
                ":empty": [],
                ":new": [image_key],
            },
            ConditionExpression="attribute_exists(id)",
            ReturnValues="UPDATED_NEW",
        )

        return response(200, {
            "message": "Product image updated successfully",
            "image_keys": result["Attributes"]["image_keys"],
        })

    except ClientError as exc:
        code = exc.response["Error"]["Code"]

        if code == "ConditionalCheckFailedException":
            return response(404, {"error": "Product not found"})

        print(f"DynamoDB error: {exc}")
        return response(500, {"error": "Failed to update product"})

    except (KeyError, ValueError, TypeError):
        return response(400, {"error": "Invalid request"})

    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return response(500, {"error": "Internal server error"})


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
