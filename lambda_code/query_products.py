from catalog import create_response, get_all_products, get_products_by_category


def handler(event, context):
    try:
        query_params = event.get("queryStringParameters") or {}
        category = query_params.get("category")

        if category:
            products = get_products_by_category(category)
        else:
            products = get_all_products()

        return create_response(200, products)

    except Exception as e:
        print(f"Error: {str(e)}")  # Log for debugging
        return create_response(500, {"error": "Internal server error"})