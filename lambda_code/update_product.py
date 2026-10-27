import json

from response_utils import create_success_response, create_error_response
from products_db import get_product, update_product
from product_schema import ProductInput
from pydantic import ValidationError
from cache_utils import invalidate_product_cache


def handler(event, context):
    try:
        body = event.get("body") or ""
        path_parameters = event.get("pathParameters") or {}
        product_id = path_parameters.get("id")

        if not product_id:
            return create_error_response(400, "Product id is required")

        # Parse JSON body
        raw_data = json.loads(body)

        # Validate input using Pydantic
        product_input = ProductInput(**raw_data)
        validated_data = product_input.model_dump()

        # Extract user ARN from request context
        user_arn = (
            event.get("requestContext", {})
            .get("identity", {})
            .get("userArn", "unknown")
        )

        # Retrieve the existing product to capture its current category
        previous_product = get_product(product_id)

        if not previous_product:
            return create_error_response(404, "Product not found")

        previous_category = previous_product.get("category")

        # Update the product in DynamoDB
        updated = update_product(product_id, validated_data, user_arn)

        # Invalidate product and both old and new category caches
        invalidate_product_cache(
            product_id,
            previous_category,
            updated.get("category"),
        )

        return create_success_response(200, updated)

    except json.JSONDecodeError:
        return create_error_response(400, "Invalid JSON body")

    except ValidationError as e:
        errors = e.errors()
        error_messages = [
            f"{err['loc'][0]}: {err['msg']}" for err in errors
        ]
        return create_error_response(
            400,
            f"Validation failed: {', '.join(error_messages)}",
        )

    except ValueError as e:
        return create_error_response(404, str(e))

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(500, "Internal server error")
