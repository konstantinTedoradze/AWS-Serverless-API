
from aws_cdk import (
    CfnOutput,
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
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

        # Lambda functions
        self.get_product = _lambda.Function(
            self,
            "GetProduct",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="get_product.handler",
            code=_lambda.Code.from_asset("lambda_code"),
        )

        self.query_products = _lambda.Function(
            self,
            "QueryProducts",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="query_products.handler",
            code=_lambda.Code.from_asset("lambda_code"),
        )

        self.insert_product = _lambda.Function(
            self,
            "InsertProduct",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="insert_product.handler",
            code=_lambda.Code.from_asset("lambda_code"),
        )

        self.update_product = _lambda.Function(
            self,
            "UpdateProduct",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="update_product.handler",
            code=_lambda.Code.from_asset("lambda_code"),
        )

        self.options = _lambda.Function(
            self,
            "Options",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="options.handler",
            code=_lambda.Code.from_asset("lambda_code"),
        )

        # API Gateway
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

        CfnOutput(
            self,
            "ProductsApiUrl",
            value=api.url,
        )
