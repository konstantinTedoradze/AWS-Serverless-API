import json
from response_utils import create_success_response, create_error_response
from products_db import update_product
from product_schema import ProductInput
from pydantic import ValidationError

def handler(event, context):
    try:
        body = event.get('body') or ''
        product_id = event.get('pathParameters', {}).get('id')
        
        if not product_id:
            return create_error_response(400, 'Product id is required')
        
        raw_data = json.loads(body)
        
        # Validate input using Pydantic
        product_input = ProductInput(**raw_data)
        validated_data = product_input.model_dump()
        
        # Extract user ARN from request context
        user_arn = event.get('requestContext', {}).get('identity', {}).get('userArn', 'unknown')
        
        # Update in DynamoDB
        updated = update_product(product_id, validated_data, user_arn)
        return create_success_response(200, updated)
        
    except ValidationError as e:
        errors = e.errors()
        error_messages = [f"{err['loc'][0]}: {err['msg']}" for err in errors]
        return create_error_response(400, f'Validation failed: {", ".join(error_messages)}')
    except ValueError as e:
        return create_error_response(404, str(e))
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(500, f'Internal server error - {str(e)}')