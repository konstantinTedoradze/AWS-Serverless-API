import unittest
import json
from unittest.mock import patch


class TestGetProduct(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures before each test method."""

        self.sample_product = {
            'id': 'prod_123',
            'title': 'Wireless Headphones',
            'price': 199.99,
            'category': 'Electronics',
            'inventory_count': 50
        }

        self.valid_event = {
            'httpMethod': 'GET',
            'pathParameters': {
                'id': '00000000-0000-4000-8000-000000000001'
            },
            'queryStringParameters': None,
            'body': None
        }

    @patch('lambda_code.products_db.get_product')
    def test_get_product_success(self, mock_get_product):
        """Test successful product retrieval."""

        # Arrange
        mock_get_product.return_value = self.sample_product

        # Act
        from lambda_code.get_product import handler

        response = handler(self.valid_event, None)

        # Assert
        self.assertEqual(response['statusCode'], 200)

        body = json.loads(response['body'])

        self.assertEqual(body['id'], 'prod_123')
        self.assertEqual(body['title'], 'Wireless Headphones')

        # Verify database was called correctly
        mock_get_product.assert_called_once_with('00000000-0000-4000-8000-000000000001')

    @patch('lambda_code.products_db.get_product')
    def test_get_product_not_found(self, mock_get_product):
        """Test handling of non-existent product requests."""

        # Arrange
        mock_get_product.return_value = None

        event = {
            'httpMethod': 'GET',
            'pathParameters': {
                'id': '00000000-0000-4000-8000-000000000002'
            }
        }

        # Act
        from lambda_code.get_product import handler

        response = handler(event, None)

        # Assert
        self.assertEqual(response['statusCode'], 404)

        body = json.loads(response['body'])

        self.assertIn('error', body)
        self.assertIn('Product not found', body['error'])

    def test_missing_path_parameters(self):
        """Test handling of malformed requests."""

        # Arrange
        invalid_event = {
            'httpMethod': 'GET',
            'pathParameters': None
        }

        # Act
        from lambda_code.get_product import handler

        response = handler(invalid_event, None)

        # Assert
        self.assertEqual(response['statusCode'], 400)

        body = json.loads(response['body'])

        self.assertIn('error', body)
        self.assertIn('Product ID required', body['error'])