from catalog import create_response, get_product


def handler(event, context):
    try:
        product_id = (event.get("pathParameters") or {}).get("id")

        if not product_id:
            return create_response(400, {"error": "Product ID required"})

        product = get_product(product_id)
        if not product:
            return create_response(404, {"error": "Product not found"})

        return create_response(200, product)

    except Exception as e:
        print(f"Error: {str(e)}")  # Log for debugging
        return create_response(500, {"error": "Internal server error"})