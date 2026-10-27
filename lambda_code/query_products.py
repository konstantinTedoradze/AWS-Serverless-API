from response_utils import create_success_response, create_error_response
from products_db import get_products_by_category, get_all_products
from cache_utils import (
    get_valkey_client,
    cache_with_appropriate_ttl,
)


def handler(event, context):
    try:
        query_parameters = event.get("queryStringParameters") or {}
        category = query_parameters.get("category")

        # Use separate cache keys for all products and each category.
        if category:
            cache_key = f"products:category:{category}"
            cache_type = "category_lists"
        else:
            cache_key = "products:all"
            cache_type = "search_results"

        # Try Valkey first. Cache failures must not break the API.
        try:
            cached_results = get_valkey_client().get(cache_key)

            if cached_results is not None:
                print(f"Valkey cache hit: {cache_key}")
                import json
                return create_success_response(200, json.loads(cached_results))

            print(f"Valkey cache miss: {cache_key}")

        except Exception as cache_error:
            print(
                "Valkey read error; falling back to DynamoDB: "
                f"{cache_error}"
            )

        # Retrieve products from DynamoDB.
        if category:
            products = get_products_by_category(category)
        else:
            products = get_all_products()

        # Cache results using the configured TTL.
        # Cache errors must not prevent a successful API response.
        cache_with_appropriate_ttl(
            cache_key,
            products,
            cache_type,
        )

        return create_success_response(200, products)

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(500, "Internal server error")
