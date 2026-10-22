# products_db.py - Database operations
import boto3
import boto3.dynamodb.conditions
from decimal import Decimal
from botocore.exceptions import ClientError
from datetime import datetime, timezone

table = boto3.resource('dynamodb').Table('Products')

def get_product(product_id):
    """Retrieve a single product by ID"""
    return table.get_item(Key={'id': product_id}).get('Item')

def insert_product(item, user_arn='unknown'):
    """Create a new product with generated UUID"""
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Add audit fields
    item['created_at'] = timestamp
    item['created_by'] = user_arn
    item['updated_at'] = timestamp
    item['updated_by'] = user_arn
    
    try:
        # Use condition to prevent overwriting existing products
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(id)'
        )
        return item
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise ValueError(f"Product with id {item['id']} already exists")
        raise
    # return upsert_product(str(uuid.uuid4()), item, user_arn)

def update_product(product_id, fields, user_arn):
    """Update an existing product. Fails if product doesn't exist."""
    from datetime import datetime, timezone
    
    # Fields are already validated by Pydantic before reaching this function
    timestamp = datetime.now(timezone.utc).isoformat()
    
    update_expression = """SET category = :category,
        title = :title,
        description = :description,
        price = :price,
        updated_at = :updated_at,
        updated_by = :updated_by"""
    
    expression_attribute_values = {
        ':category': fields['category'],
        ':title': fields['title'],
        ':description': fields['description'],
        ':price': fields['price'],
        ':updated_at': timestamp,
        ':updated_by': user_arn
    }
    
    try:
        # Use condition to ensure product exists before updating
        response = table.update_item(
            Key={'id': product_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ConditionExpression='attribute_exists(id)',
            ReturnValues='ALL_NEW'
        )
        return response['Attributes']
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise ValueError(f"Product with id {product_id} does not exist")
        raise

def update_product_with_version(product_id, fields, user_arn, expected_version):
    """Update product with optimistic locking using version number"""
    from datetime import datetime, timezone
    
    timestamp = datetime.now(timezone.utc).isoformat()
    new_version = expected_version + 1
    
    update_expression = """SET category = :category,
        title = :title,
        description = :description,
        price = :price,
        updated_at = :updated_at,
        updated_by = :updated_by,
        version = :new_version"""
    
    expression_attribute_values = {
        ':category': fields['category'],
        ':title': fields['title'],
        ':description': fields['description'],
        ':price': fields['price'],
        ':updated_at': timestamp,
        ':updated_by': user_arn,
        ':new_version': new_version,
        ':expected_version': expected_version
    }
    
    try:
        response = table.update_item(
            Key={'id': product_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ConditionExpression='attribute_exists(id) AND version = :expected_version',
            ReturnValues='ALL_NEW'
        )
        return response['Attributes']
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise ValueError(f"Product was modified by another user. Please refresh and try again.")
        raise

    
def get_all_products():
    """Retrieve all products from the table"""
    return table.scan()['Items']

def get_products_by_category(category):
    """Query products by category using GSI"""
    # Use GSI query instead of scan for better performance
    return table.query(
        IndexName='category-index',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('category').eq(category)
    ).get('Items')