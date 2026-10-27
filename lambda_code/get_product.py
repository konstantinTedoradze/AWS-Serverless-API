import json
from uuid import UUID

from lambda_code import products_db
from lambda_code.response_utils import (
    create_success_response,
    create_error_response,
    ContextualErrorHandler,
)
from lambda_code.cache_utils import (
    get_valkey_client,
    cache_with_appropriate_ttl,
)


def handler(event, context):
    try:
        # Get and validate the product ID.
        path_parameters = event.get("pathParameters") or {}
        product_id = path_parameters.get("id")

        if not product_id or not product_id.strip():
            return create_error_response(400, "Product ID required")

        product_id = product_id.strip()

        try:
            UUID(product_id)
        except ValueError:
            return create_error_response(400, "Invalid product id format")

        cache_key = f"product:{product_id}"

        # Try Valkey first. Cache failures must not break the API.
        try:
            cached_product = get_valkey_client().get(cache_key)

            if cached_product is not None:
                print(f"Cache hit for product {product_id}")
                return create_success_response(
                    200,
                    json.loads(cached_product),
                )

            print(f"Cache miss for product {product_id}")

        except Exception as cache_error:
            print(
                "Valkey read error; falling back to DynamoDB: "
                f"{cache_error}"
            )

        # Cache miss or cache unavailable: read DynamoDB.
        product = products_db.get_product(product_id)

        if not product:
            error_handler = ContextualErrorHandler()
            return error_handler.handle_product_not_found(product_id)

        # Populate the cache using the shared 1-hour product-details TTL.
        cache_with_appropriate_ttl(
            cache_key,
            product,
            "product_details",
        )

        return create_success_response(200, product)

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(500, "Internal server error")
