import json
import uuid

from lambda_code import products_db
from lambda_code.response_utils import (
    create_success_response,
    create_error_response,
    handle_product_validation_error,
)
from lambda_code.product_schema import ProductInput
from pydantic import ValidationError
from lambda_code.cache_utils import invalidate_product_cache


def handler(event, context):
    body = event.get("body") or ""

    try:
        # Parse JSON body
        raw_data = json.loads(body)

        # Prevent clients from specifying their own ID
        if "id" in raw_data:
            return create_error_response(400, "Product id is not allowed")

        # Validate input using Pydantic
        product_input = ProductInput(**raw_data)

        # Convert validated model to dict for database storage
        validated_data = product_input.model_dump()

        # Generate unique ID
        product_id = str(uuid.uuid4())
        validated_data["id"] = product_id

        # Extract user ARN from request context
        user_arn = (
            event.get("requestContext", {})
            .get("identity", {})
            .get("userArn", "unknown")
        )

        # Store in DynamoDB
        inserted = products_db.insert_product(validated_data, user_arn)

        # Invalidate product-list caches after a successful insert
        invalidate_product_cache(
            inserted["id"],
            inserted.get("category"),
        )

        # Return created product
        return create_success_response(201, inserted)

    except json.JSONDecodeError as e:
        return create_error_response(400, f"Invalid JSON: {str(e)}")

    except ValidationError as e:
        request_context = event.get("requestContext") or {}
        request_id = request_context.get("requestId")

        return handle_product_validation_error(
            validation_errors=e.errors(),
            request_id=request_id,
        )

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(500, "Internal server error")
