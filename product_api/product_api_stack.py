
# from aws_cdk import (
#     CfnOutput,
#     Stack,
#     aws_lambda as _lambda,
#     aws_apigateway as apigw,
# )
# from constructs import Construct


# class ProductApiStack(Stack):
#     def __init__(
#         self,
#         scope: Construct,
#         construct_id: str,
#         **kwargs,
#     ) -> None:
#         super().__init__(scope, construct_id, **kwargs)

#         # Lambda functions
#         self.get_product = _lambda.Function(
#             self,
#             "GetProduct",
#             runtime=_lambda.Runtime.PYTHON_3_13,
#             handler="get_product.handler",
#             code=_lambda.Code.from_asset("lambda_code"),
#         )

#         self.query_products = _lambda.Function(
#             self,
#             "QueryProducts",
#             runtime=_lambda.Runtime.PYTHON_3_13,
#             handler="query_products.handler",
#             code=_lambda.Code.from_asset("lambda_code"),
#         )

#         self.insert_product = _lambda.Function(
#             self,
#             "InsertProduct",
#             runtime=_lambda.Runtime.PYTHON_3_13,
#             handler="insert_product.handler",
#             code=_lambda.Code.from_asset("lambda_code"),
#         )

#         self.update_product = _lambda.Function(
#             self,
#             "UpdateProduct",
#             runtime=_lambda.Runtime.PYTHON_3_13,
#             handler="update_product.handler",
#             code=_lambda.Code.from_asset("lambda_code"),
#         )

#         self.options = _lambda.Function(
#             self,
#             "Options",
#             runtime=_lambda.Runtime.PYTHON_3_13,
#             handler="options.handler",
#             code=_lambda.Code.from_asset("lambda_code"),
#         )

#         # API Gateway
#         api = apigw.RestApi(
#             self,
#             "ProductsAPI",
#             deploy_options=apigw.StageOptions(stage_name="dev"),
#         )

#         products = api.root.add_resource("products")

#         products.add_method(
#             "GET",
#             apigw.LambdaIntegration(self.query_products),
#         )
#         products.add_method(
#             "POST",
#             apigw.LambdaIntegration(self.insert_product),
#         )
#         products.add_method(
#             "OPTIONS",
#             apigw.LambdaIntegration(self.options),
#         )

#         product_by_id = products.add_resource("{id}")

#         product_by_id.add_method(
#             "GET",
#             apigw.LambdaIntegration(self.get_product),
#         )
#         product_by_id.add_method(
#             "PUT",
#             apigw.LambdaIntegration(self.update_product),
#         )
#         product_by_id.add_method(
#             "OPTIONS",
#             apigw.LambdaIntegration(self.options),
#         )

#         CfnOutput(
#             self,
#             "ProductsApiUrl",
#             value=api.url,
#         )


from aws_cdk import (
    CfnOutput,
    Stack,
    aws_lambda as aws_lambda,
    aws_apigateway as apigw,
    aws_dynamodb as aws_dynamodb,
)
from constructs import Construct


class ProductApiStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Create the DynamoDB table
        products_table = aws_dynamodb.Table(
            self,
            "ProductsTable",
            table_name="Products",
            partition_key=aws_dynamodb.Attribute(
                name="id",
                type=aws_dynamodb.AttributeType.STRING,
            ),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        # 2. Add a Global Secondary Index for category queries
        products_table.add_global_secondary_index(
            index_name="category-index",
            partition_key=aws_dynamodb.Attribute(
                name="category",
                type=aws_dynamodb.AttributeType.STRING,
            ),
        )

        # 3. Configure Lambda functions
        lambda_runtime = aws_lambda.Runtime.PYTHON_3_13
        code_location = "lambda_code"
        

        self.get_product = aws_lambda.Function(
            self,
            "GetProduct",
            runtime=lambda_runtime,
            handler="get_product.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        self.query_products = aws_lambda.Function(
            self,
            "QueryProducts",
            runtime=lambda_runtime,
            handler="query_products.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        self.insert_product = aws_lambda.Function(
            self,
            "InsertProduct",
            runtime=lambda_runtime,
            handler="insert_product.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        self.update_product = aws_lambda.Function(
            self,
            "UpdateProduct",
            runtime=lambda_runtime,
            handler="update_product.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        self.options = aws_lambda.Function(
            self,
            "Options",
            runtime=lambda_runtime,
            handler="options.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        # 4. Pass the DynamoDB table name to the relevant Lambdas
        for function in [
            self.get_product,
            self.query_products,
            self.insert_product,
            self.update_product,
        ]:
            function.add_environment(
                "PRODUCTS_TABLE_NAME",
                products_table.table_name,
            )

        # 5. Grant least-privilege DynamoDB permissions
        products_table.grant_read_data(self.get_product)
        products_table.grant_read_data(self.query_products)

        products_table.grant_read_write_data(self.insert_product)
        products_table.grant_read_write_data(self.update_product)

        # 6. Configure API Gateway
        api = apigw.RestApi(
            self,
            "ProductsAPI",
            deploy_options=apigw.StageOptions(stage_name="dev"),
        )

        products = api.root.add_resource("products")

        products.add_method(
            "GET",
            apigw.LambdaIntegration(self.query_products),
        )

        products.add_method(
            "POST",
            apigw.LambdaIntegration(self.insert_product),
        )

        products.add_method(
            "OPTIONS",
            apigw.LambdaIntegration(self.options),
        )

        product_by_id = products.add_resource("{id}")

        product_by_id.add_method(
            "GET",
            apigw.LambdaIntegration(self.get_product),
        )

        product_by_id.add_method(
            "PUT",
            apigw.LambdaIntegration(self.update_product),
        )

        product_by_id.add_method(
            "OPTIONS",
            apigw.LambdaIntegration(self.options),
        )

        # 7. Output the API URL
        CfnOutput(
            self,
            "ProductsApiUrl",
            value=api.url,
        )
