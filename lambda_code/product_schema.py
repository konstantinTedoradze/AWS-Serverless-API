from pydantic import BaseModel, Field, field_validator
from decimal import Decimal

class ProductInput(BaseModel):
    """Schema for creating or updating products"""
    title: str = Field(min_length=1, max_length=200, description="Product title")
    category: str = Field(min_length=1, description="Product category")
    description: str = Field(min_length=1, max_length=1000, description="Product description")
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2, description="Product price")
    
    @field_validator('price')
    @classmethod
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Price must be greater than zero')
        return v
    
    @field_validator('category')
    @classmethod
    def category_must_be_valid(cls, v):
        valid_categories = ['Electronics', 'Audio', 'Computers', 'Accessories', 'Home']
        if v not in valid_categories:
            raise ValueError(f'Invalid category: {v}. Must be one of {valid_categories}')
        return v