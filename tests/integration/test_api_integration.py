# Complete API Gateway event structure for product API
api_gateway_event = {
    'httpMethod': 'GET',
    'path': '/products/prod_123',
    'pathParameters': {
        'id': 'prod_123'
    },
    'queryStringParameters': {
        'category': 'Electronics',
        'limit': '10'
    },
    'headers': {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer token123',
        'User-Agent': 'Mozilla/5.0...'
    },
    'body': None,
    'isBase64Encoded': False,
    'requestContext': {
        'requestId': 'test-request-id',
        'stage': 'dev',
        'httpMethod': 'GET'
    }
}