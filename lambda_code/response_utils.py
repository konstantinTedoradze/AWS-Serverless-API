# response_utils.py - Response formatting

import json
from datetime import datetime, timezone
from decimal import Decimal


def create_success_response(status_code, data):
    """Create a standardized success response for API Gateway."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(data, default=decimal_serializer)
    }


def decimal_serializer(obj):
    """Handle non-JSON-native values in API responses."""
    if isinstance(obj, Decimal):
        return float(obj)

    if isinstance(obj, Exception):
        return str(obj)

    raise TypeError(
        f"Object of type {type(obj)} is not JSON serializable"
    )


def create_error_response(status_code, message):
    """Create a legacy error response for backward compatibility."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({'error': message})
    }


def create_structured_error_response(
    status_code,
    error_type,
    message,
    details=None,
    suggestions=None,
    request_id=None
):
    """Create a consistent, structured API Gateway error response."""
    error = {
        'type': error_type,
        'message': message,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }

    if request_id:
        error['request_id'] = request_id

    if details is not None:
        error['details'] = details

    if suggestions:
        error['suggestions'] = suggestions

    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({'error': error}, default=decimal_serializer)
    }


def handle_product_validation_error(validation_errors, request_id=None):
    """Create a helpful structured response for product validation failures."""
    return create_structured_error_response(
        status_code=400,
        error_type='validation_error',
        message='Product data validation failed',
        details=validation_errors,
        suggestions=[
            'Check that all required fields are provided.',
            'Ensure price is a positive number.',
            'Verify that category is from the allowed list.'
        ],
        request_id=request_id
    )


def handle_inventory_insufficient_error(
    product_id,
    requested,
    available,
    request_id=None
):
    """Create a structured response for insufficient inventory."""
    return create_structured_error_response(
        status_code=409,
        error_type='insufficient_inventory',
        message='Not enough inventory for the requested quantity.',
        details={
            'product_id': product_id,
            'requested_quantity': requested,
            'available_quantity': available
        },
        suggestions=[
            f'Reduce the quantity to {available} or less.',
            'Check back later for restocked inventory.',
            'Consider similar products in the same category.'
        ],
        request_id=request_id
    )



class ContextualErrorHandler:
    """Generate context-aware error messages for better user experience."""

    def __init__(self, user_context=None):
        self.user_context = user_context or {}

    def handle_product_not_found(self, product_id):
        """Generate helpful message for missing products."""
        suggestions = ['Verify the product ID is correct']

        search_term = self.user_context.get('search_term')
        if search_term:
            suggestions.append(
                f'Try searching for "{search_term}" to find similar products'
            )

        category = self.user_context.get('category')
        if category:
            suggestions.append(
                f'Browse other products in the {category} category'
            )

        return create_structured_error_response(
            status_code=404,
            error_type='product_not_found',
            message=f'Product {product_id} is not available',
            suggestions=suggestions
        )

    def handle_checkout_error(self, error_details):
        """Generate helpful checkout error messages."""
        if error_details.get('payment_failed'):
            return create_structured_error_response(
                status_code=400,
                error_type='payment_error',
                message='Payment processing failed',
                suggestions=[
                    'Verify your payment information is correct',
                    'Check that your card has sufficient funds',
                    'Try a different payment method',
                    'Contact your bank if the problem persists'
                ]
            )

        if error_details.get('address_invalid'):
            return create_structured_error_response(
                status_code=400,
                error_type='address_error',
                message='Shipping address validation failed',
                details=error_details.get('address_errors', []),
                suggestions=[
                    'Verify your address is complete and accurate',
                    'Check that the postal code matches your city or state',
                    'Ensure we deliver to your location'
                ]
            )

        return create_structured_error_response(
            status_code=400,
            error_type='checkout_error',
            message='Checkout could not be completed',
            suggestions=[
                'Review your checkout information and try again'
            ]
        )
