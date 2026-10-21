"""Shared data access and response utilities for the product API.

This is the in-memory catalog used throughout this course. You replace it
with Amazon DynamoDB in the data module of this learning plan.
"""
import json

PRODUCTS = {
    "prod_001": {"id": "prod_001", "name": "Wireless Headphones", "price": 199.99, "category": "Electronics"},
    "prod_002": {"id": "prod_002", "name": "USB-C Cable", "price": 12.99, "category": "Electronics"},
    "prod_003": {"id": "prod_003", "name": "Ceramic Mug", "price": 8.49, "category": "Home Goods"},
}


def create_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        },
        "body": json.dumps(body) if body else ""
    }


def get_product(product_id):
    # Returns product from catalog
    return PRODUCTS.get(product_id)


def get_all_products():
    # Returns all products in store
    return list(PRODUCTS.values())


def get_products_by_category(category):
    # Returns products matching category (Electronics, Home Goods, etc.)
    return [p for p in PRODUCTS.values() if p["category"].lower() == category.lower()]