import os

import redis

# Cache expiration times in seconds
CACHE_TTL = {
    "product_details": 3600,   # 1 hour
    "search_results": 1800,    # 30 minutes
    "category_lists": 7200,    # 2 hours
    "inventory_counts": 300,   # 5 minutes
    "user_sessions": 86400,    # 24 hours
    "popular_products": 3600,  # 1 hour
}

DEFAULT_CACHE_TTL = 3600
CACHE_TIMEOUT_SECONDS = 1

_valkey_client = None


def get_valkey_client():
    """Create and reuse the Valkey client within a Lambda environment."""
    global _valkey_client

    if _valkey_client is None:
        host = os.environ.get("VALKEY_HOST")
        port = os.environ.get("VALKEY_PORT")

        if not host or not port:
            raise RuntimeError("Valkey endpoint environment variables are missing")

        _valkey_client = redis.Redis(
            host=host,
            port=int(port),
            ssl=os.environ.get("VALKEY_TLS", "true").lower() == "true",
            decode_responses=True,
            socket_connect_timeout=CACHE_TIMEOUT_SECONDS,
            socket_timeout=CACHE_TIMEOUT_SECONDS,
        )

    return _valkey_client


def cache_with_appropriate_ttl(key, data, data_type):
    """Cache data using the TTL configured for its data type."""
    ttl = CACHE_TTL.get(data_type, DEFAULT_CACHE_TTL)

    try:
        import json

        get_valkey_client().setex(
            key,
            ttl,
            json.dumps(data, default=str),
        )
        print(f"Cached {key} with TTL {ttl} seconds")
        return True

    except Exception as cache_error:
        print(f"Valkey caching error for {key}: {cache_error}")
        return False


def invalidate_product_cache(product_id, *categories):
    """Invalidate product details and affected product-list caches."""
    try:
        client = get_valkey_client()

        # Remove cached details for this product.
        client.delete(f"product:{product_id}")

        # Remove the all-products list.
        client.delete("products:all")

        # Remove lists for the old and new categories.
        for category in set(categories):
            if category:
                client.delete(f"products:category:{category}")

        print(f"Cache invalidated for product {product_id}")
        return True

    except Exception as cache_error:
        # Cache failure should not undo a successful database write.
        print(f"Valkey cache invalidation error: {cache_error}")
        return False
