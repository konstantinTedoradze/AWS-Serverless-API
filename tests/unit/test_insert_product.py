import unittest
import json
from unittest.mock import patch


class TestInsertProduct(unittest.TestCase):

    @patch('lambda_code.products_db.insert_product')
    def test_insert_product_success(self, mock_insert_product):
        """Test successful product creation."""

        # Arrange
        new_product_data = {
            'title': 'Gaming Mouse',
            'price': 79.99,
            'category': 'Electronics',
            'description': 'Gaming mouse with adjustable sensitivity'
        }

        mock_insert_product.return_value = {
            'id': 'prod_456',
            **new_product_data
        }

        create_event = {
            'httpMethod': 'POST',
            'body': json.dumps(new_product_data)
        }

        # Act
        from lambda_code.insert_product import handler

        response = handler(create_event, None)

        # Assert
        self.assertEqual(response['statusCode'], 201)

        body = json.loads(response['body'])

        self.assertEqual(body['title'], 'Gaming Mouse')
        self.assertIn('id', body)

    @patch('lambda_code.products_db.insert_product')
    def test_insert_product_validation_error(self, mock_insert_product):
        """Test product creation with invalid data."""

        # Arrange
        invalid_product = {
            'title': '',
            'price': -10,
            'category': 'InvalidCategory'
        }

        create_event = {
            'httpMethod': 'POST',
            'body': json.dumps(invalid_product)
        }

        # Act
        from lambda_code.insert_product import handler

        response = handler(create_event, None)

        # Assert
        self.assertEqual(response['statusCode'], 400)

        body = json.loads(response['body'])

        self.assertIn('error', body)
        self.assertEqual(
            body['error']['type'],
            'validation_error'
        )
        self.assertEqual(
            body['error']['message'],
            'Product data validation failed'
        )
        self.assertIn('details', body['error'])
        self.assertTrue(body['error']['details'])
        self.assertIn('suggestions', body['error'])

        # Verify database was not called with invalid data
        mock_insert_product.assert_not_called()