from uuid import UUID
from lambda_code import products_db
from lambda_code.response_utils import (
    create_success_response,
    create_error_response,
)

def handler(event, context):
    try:
        # Get path parameters
        path_parameters = event.get("pathParameters") or {}
        product_id = path_parameters.get("id")

        # Validate that product ID was provided
        if not product_id or not product_id.strip():
            return create_error_response(400, "Product ID required")

        product_id = product_id.strip()

        # Validate UUID format
        try:
            UUID(product_id)
        except ValueError:
            return create_error_response(400, "Invalid product id format")

        # Get product from DynamoDB
        product = products_db.get_product(product_id)

        if not product:
            return create_error_response(404, "Product not found")

        return create_success_response(200, product)

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(500, "Internal server error")