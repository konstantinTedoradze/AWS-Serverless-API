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
    aws_ec2 as aws_ec2,
    aws_elasticache as aws_elasticache,
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

        # 1. Create VPC for Lambda and ElastiCache
        vpc = aws_ec2.Vpc(
            self,
            "ProductApiVpc",
            max_azs=2,
            nat_gateways=1,
        )

        # 2. Create security group for Valkey
        valkey_security_group = aws_ec2.SecurityGroup(
            self,
            "ValkeySecurityGroup",
            vpc=vpc,
            description="Security group for Valkey ElastiCache",
            allow_all_outbound=True,
        )

        # 3. Create security group for Lambda
        lambda_security_group = aws_ec2.SecurityGroup(
            self,
            "LambdaSecurityGroup",
            vpc=vpc,
            description="Security group for Lambda functions",
            allow_all_outbound=True,
        )

        # 4. Allow Lambda to connect to Valkey on port 6379
        valkey_security_group.add_ingress_rule(
            lambda_security_group,
            aws_ec2.Port.tcp(6379),
            "Allow Lambda to access Valkey",
        )

        # 5. Create a subnet group for Valkey
        valkey_subnet_group = aws_elasticache.CfnSubnetGroup(
            self,
            "ValkeySubnetGroup",
            description="Private subnets for the Product API Valkey cache",
            subnet_ids=[
                subnet.subnet_id
                for subnet in vpc.private_subnets
            ],
        )

        # 6. Create a single-node Valkey replication group
        # Valkey uses CfnReplicationGroup, not CfnCacheCluster.
        valkey_cluster = aws_elasticache.CfnReplicationGroup(
            self,
            "ValkeyReplicationGroup",
            replication_group_id="online-store-valkey-cache",
            replication_group_description=(
                "Valkey cache for the online store Product API"
            ),
            engine="valkey",
            cache_node_type="cache.t3.micro",
            num_cache_clusters=1,
            port=6379,
            cache_subnet_group_name=valkey_subnet_group.ref,
            security_group_ids=[
                valkey_security_group.security_group_id
            ],
            at_rest_encryption_enabled=True,
            transit_encryption_enabled=True,
        )

        # Ensure the subnet group exists before Valkey is created
        valkey_cluster.add_dependency(valkey_subnet_group)

        # 7. Create a dead-letter queue
        dlq = aws_sqs.Queue(
            self,
            "ProductApiDlq",
            queue_name="product-api-dlq",
            retention_period=Duration.days(14),
            visibility_timeout=Duration.seconds(300),
            receive_message_wait_time=Duration.seconds(20),
        )

        # 8. Create the DynamoDB table
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

        # 9. Add a Global Secondary Index
        products_table.add_global_secondary_index(
            index_name="category-index",
            partition_key=aws_dynamodb.Attribute(
                name="category",
                type=aws_dynamodb.AttributeType.STRING,
            ),
        )

        # 10. Create S3 bucket for product images
        product_images_bucket = aws_s3.Bucket(
            self,
            "ProductImagesBucket",
            versioned=True,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            encryption=aws_s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

        # 11. Configure Lambda functions
        lambda_runtime = aws_lambda.Runtime.PYTHON_3_13
        code_location = "lambda_code"

        # Shared Lambda Layer containing the Redis/Valkey Python client
        redis_layer = aws_lambda.LayerVersion(
            self,
            "RedisLayer",
            code=aws_lambda.Code.from_asset("layers/redis"),
            compatible_runtimes=[lambda_runtime],
            description="Redis Python client for Valkey integration",
        )

        # Shared Valkey configuration for cache-enabled Lambdas
        valkey_environment = {
            "VALKEY_HOST": valkey_cluster.attr_primary_end_point_address,
            "VALKEY_PORT": valkey_cluster.attr_primary_end_point_port,
            "VALKEY_TLS": "true",
            "PRODUCT_CACHE_TTL": "3600",
            "SEARCH_CACHE_TTL": "1800",
            "CATEGORY_CACHE_TTL": "7200",
        }

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
                "PRODUCT_IMAGES_BUCKET": (
                    product_images_bucket.bucket_name
                ),
                "PRODUCTS_TABLE_NAME": products_table.table_name,
            },
        )

        # Get one product by ID
        # This Lambda needs VPC access to connect to Valkey
        self.get_product = aws_lambda.Function(
            self,
            "GetProduct",
            runtime=lambda_runtime,
            handler="get_product.handler",
            code=aws_lambda.Code.from_asset(code_location),
            dead_letter_queue=dlq,
            vpc=vpc,
            security_groups=[lambda_security_group],
            vpc_subnets=aws_ec2.SubnetSelection(
                subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            layers=[redis_layer],
            environment=valkey_environment,
        )

        # Query products
        self.query_products = aws_lambda.Function(
            self,
            "QueryProducts",
            runtime=lambda_runtime,
            handler="query_products.handler",
            code=aws_lambda.Code.from_asset(code_location),
            dead_letter_queue=dlq,
            vpc=vpc,
            security_groups=[lambda_security_group],
            vpc_subnets=aws_ec2.SubnetSelection(
                subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            layers=[redis_layer],
            environment=valkey_environment,
        )

        # Create a product
        self.insert_product = aws_lambda.Function(
            self,
            "InsertProduct",
            runtime=lambda_runtime,
            handler="insert_product.handler",
            code=aws_lambda.Code.from_asset(code_location),
            dead_letter_queue=dlq,
            vpc=vpc,
            security_groups=[lambda_security_group],
            vpc_subnets=aws_ec2.SubnetSelection(
                subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            layers=[redis_layer],
            environment=valkey_environment,
        )

        # Update a product
        self.update_product = aws_lambda.Function(
            self,
            "UpdateProduct",
            runtime=lambda_runtime,
            handler="update_product.handler",
            code=aws_lambda.Code.from_asset(code_location),
            dead_letter_queue=dlq,
            vpc=vpc,
            security_groups=[lambda_security_group],
            vpc_subnets=aws_ec2.SubnetSelection(
                subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            layers=[redis_layer],
            environment=valkey_environment,
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
                "PRODUCT_IMAGES_BUCKET": (
                    product_images_bucket.bucket_name
                ),
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

        # 12. Configure DynamoDB environment variables
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

        # 13. Configure S3 environment variables
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

        # 15. Grant DynamoDB permissions
        products_table.grant_read_data(self.get_product)
        products_table.grant_read_data(self.query_products)

        products_table.grant_read_write_data(self.insert_product)
        products_table.grant_read_write_data(self.update_product)

        # Image key update Lambda only needs DynamoDB write access
        products_table.grant_write_data(self.update_product_images)

        # Image processing Lambda updates product information
        products_table.grant_write_data(self.process_product_image)

        # 16. Grant S3 permissions
        product_images_bucket.grant_read(self.get_product)
        product_images_bucket.grant_read_write(self.insert_product)
        product_images_bucket.grant_read_write(self.update_product)

        # Upload Lambda: permission to upload objects
        product_images_bucket.grant_put(self.upload_product_image)

        # Download Lambda: permission to inspect and read objects
        product_images_bucket.grant_read(self.get_product_image)

        # Image processing Lambda: read and write objects
        product_images_bucket.grant_read_write(
            self.process_product_image
        )

        # 17. Configure S3 event notification
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

        # 18. Configure API Gateway
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
        image.add_method(
            "POST",
            apigw.LambdaIntegration(self.upload_product_image),
        )

        # GET /products/{id}/image
        image.add_method(
            "GET",
            apigw.LambdaIntegration(self.get_product_image),
        )

        # PUT /products/{id}/image
        image.add_method(
            "PUT",
            apigw.LambdaIntegration(self.update_product_images),
        )

        image.add_method(
            "OPTIONS",
            apigw.LambdaIntegration(self.options),
        )

        # 19. Outputs
        CfnOutput(
            self,
            "ProductsApiUrl",
            value=api.url,
        )

        CfnOutput(
            self,
            "ProductImagesBucketName",
            value=product_images_bucket.bucket_name,
        )

        CfnOutput(
            self,
            "ValkeyClusterEndpoint",
            value=valkey_cluster.attr_primary_end_point_address,
            description="Valkey primary endpoint",
        )

        CfnOutput(
            self,
            "ValkeyClusterPort",
            value=valkey_cluster.attr_primary_end_point_port,
            description="Valkey cluster port",
        )