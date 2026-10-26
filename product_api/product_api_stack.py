from aws_cdk import (
    CfnOutput,
    Stack,
    Duration,
    RemovalPolicy,
    aws_lambda as aws_lambda,
    aws_apigateway as apigw,
    aws_dynamodb as aws_dynamodb,
    aws_sqs as aws_sqs,
    aws_s3 as aws_s3,
    aws_s3_notifications as aws_s3_notifications,
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

        # 1. Create a dead-letter queue
        dlq = aws_sqs.Queue(
            self,
            "ProductApiDlq",
            queue_name="product-api-dlq",
            retention_period=Duration.days(14),
            visibility_timeout=Duration.seconds(300),
            receive_message_wait_time=Duration.seconds(20),
        )

        # 2. Create the DynamoDB table
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

        # 3. Add a Global Secondary Index
        products_table.add_global_secondary_index(
            index_name="category-index",
            partition_key=aws_dynamodb.Attribute(
                name="category",
                type=aws_dynamodb.AttributeType.STRING,
            ),
        )

        # 4. Create S3 bucket for product images
        product_images_bucket = aws_s3.Bucket(
            self,
            "ProductImagesBucket",
            versioned=True,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            encryption=aws_s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

        # 5. Configure Lambda functions
        lambda_runtime = aws_lambda.Runtime.PYTHON_3_13
        code_location = "lambda_code"

        # Generate presigned URLs for image uploads
        self.upload_product_image = aws_lambda.Function(
            self,
            "UploadProductImage",
            runtime=lambda_runtime,
            handler="upload_product_image.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        # Generate presigned URLs for image downloads
        self.get_product_image = aws_lambda.Function(
            self,
            "GetProductImage",
            runtime=lambda_runtime,
            handler="get_product_image.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        # Process product images after they are uploaded to S3
        self.process_product_image = aws_lambda.Function(
            self,
            "ProcessProductImage",
            runtime=lambda_runtime,
            handler="process_product_image.handler",
            code=aws_lambda.Code.from_asset(code_location),
            environment={
                "PRODUCT_IMAGES_BUCKET": product_images_bucket.bucket_name,
                "PRODUCTS_TABLE_NAME": products_table.table_name,
            },
        )

        # Get one product by ID
        self.get_product = aws_lambda.Function(
            self,
            "GetProduct",
            runtime=lambda_runtime,
            handler="get_product.handler",
            code=aws_lambda.Code.from_asset(code_location),
            dead_letter_queue=dlq,
        )

        # Query products
        self.query_products = aws_lambda.Function(
            self,
            "QueryProducts",
            runtime=lambda_runtime,
            handler="query_products.handler",
            code=aws_lambda.Code.from_asset(code_location),
            dead_letter_queue=dlq,
        )

        # Create a product
        self.insert_product = aws_lambda.Function(
            self,
            "InsertProduct",
            runtime=lambda_runtime,
            handler="insert_product.handler",
            code=aws_lambda.Code.from_asset(code_location),
            dead_letter_queue=dlq,
        )

        # Update a product
        self.update_product = aws_lambda.Function(
            self,
            "UpdateProduct",
            runtime=lambda_runtime,
            handler="update_product.handler",
            code=aws_lambda.Code.from_asset(code_location),
            dead_letter_queue=dlq,
        )

        # Save an uploaded image key to the product in DynamoDB
        self.update_product_images = aws_lambda.Function(
            self,
            "UpdateProductImages",
            runtime=lambda_runtime,
            handler="update_product_images.handler",
            code=aws_lambda.Code.from_asset(code_location),
            environment={
                "PRODUCT_TABLE": products_table.table_name,
                "PRODUCT_IMAGES_BUCKET": product_images_bucket.bucket_name,
            },
        )

        # Handle CORS preflight requests
        self.options = aws_lambda.Function(
            self,
            "Options",
            runtime=lambda_runtime,
            handler="options.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        # 6. Configure DynamoDB environment variables
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

        # 7. Configure S3 environment variables
        for function in [
            self.get_product,
            self.insert_product,
            self.update_product,
            self.upload_product_image,
            self.get_product_image,
        ]:
            function.add_environment(
                "PRODUCT_IMAGES_BUCKET",
                product_images_bucket.bucket_name,
            )

        # 8. Grant DynamoDB permissions
        products_table.grant_read_data(self.get_product)
        products_table.grant_read_data(self.query_products)

        products_table.grant_read_write_data(self.insert_product)
        products_table.grant_read_write_data(self.update_product)

        # Image key update Lambda only needs DynamoDB write access
        products_table.grant_write_data(self.update_product_images)

        # Image processing Lambda updates product information
        products_table.grant_write_data(self.process_product_image)

        # 9. Grant S3 permissions

        # Existing product handlers
        product_images_bucket.grant_read(self.get_product)
        product_images_bucket.grant_read_write(self.insert_product)
        product_images_bucket.grant_read_write(self.update_product)

        # Upload Lambda: permission to upload objects
        product_images_bucket.grant_put(self.upload_product_image)

        # Download Lambda: permission to inspect and read objects
        product_images_bucket.grant_read(self.get_product_image)

        # Image processing Lambda:
        # read original images and write thumbnails/processed images
        product_images_bucket.grant_read_write(
            self.process_product_image
        )

        # 10. Configure S3 event notification
        #
        # When a .jpg file is created under products/,
        # invoke ProcessProductImage Lambda.
        product_images_bucket.add_event_notification(
            aws_s3.EventType.OBJECT_CREATED,
            aws_s3_notifications.LambdaDestination(
                self.process_product_image
            ),
            aws_s3.NotificationKeyFilter(
                prefix="products/",
                suffix=".jpg",
            ),
        )

        # 11. Configure API Gateway
        api = apigw.RestApi(
            self,
            "ProductsAPI",
            deploy_options=apigw.StageOptions(stage_name="dev"),
        )

        products = api.root.add_resource("products")

        # GET /products
        products.add_method(
            "GET",
            apigw.LambdaIntegration(self.query_products),
        )

        # POST /products
        products.add_method(
            "POST",
            apigw.LambdaIntegration(self.insert_product),
        )

        products.add_method(
            "OPTIONS",
            apigw.LambdaIntegration(self.options),
        )

        # /products/{id}
        product_by_id = products.add_resource("{id}")

        # GET /products/{id}
        product_by_id.add_method(
            "GET",
            apigw.LambdaIntegration(self.get_product),
        )

        # PUT /products/{id}
        product_by_id.add_method(
            "PUT",
            apigw.LambdaIntegration(self.update_product),
        )

        product_by_id.add_method(
            "OPTIONS",
            apigw.LambdaIntegration(self.options),
        )

        # /products/{id}/image
        image = product_by_id.add_resource("image")

        # POST /products/{id}/image
        # Generate a presigned upload URL
        image.add_method(
            "POST",
            apigw.LambdaIntegration(self.upload_product_image),
        )

        # GET /products/{id}/image
        # Generate a presigned download URL
        image.add_method(
            "GET",
            apigw.LambdaIntegration(self.get_product_image),
        )

        # PUT /products/{id}/image
        # Save the uploaded image key to DynamoDB
        image.add_method(
            "PUT",
            apigw.LambdaIntegration(self.update_product_images),
        )

        image.add_method(
            "OPTIONS",
            apigw.LambdaIntegration(self.options),
        )

        # 12. Output the API URL
        CfnOutput(
            self,
            "ProductsApiUrl",
            value=api.url,
        )

        # 13. Output the S3 bucket name
        CfnOutput(
            self,
            "ProductImagesBucketName",
            value=product_images_bucket.bucket_name,
        )
