from catalog import create_response


def handler(event, context):
    # Product creation requires persistent storage. You implement this
    # with Amazon DynamoDB in the data module of this learning plan.
    return create_response(501, {
        "error": "NotImplementedError",
        "message": "POST /products is implemented in the data module of this learning plan"
    })