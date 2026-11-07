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
    aws_lambda_event_sources as aws_lambda_event_sources,
    aws_iam as aws_iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_sns as aws_sns,
    aws_sns_subscriptions as aws_sns_subscriptions,
    aws_kinesisfirehose as firehose,
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

        # --------------------------------------------------
        # 1. VPC AND SECURITY GROUPS
        # --------------------------------------------------

        vpc = aws_ec2.Vpc(
            self,
            "ProductApiVpc",
            max_azs=2,
            nat_gateways=1,
        )

        valkey_security_group = aws_ec2.SecurityGroup(
            self,
            "ValkeySecurityGroup",
            vpc=vpc,
            description="Security group for Valkey ElastiCache",
            allow_all_outbound=True,
        )

        lambda_security_group = aws_ec2.SecurityGroup(
            self,
            "LambdaSecurityGroup",
            vpc=vpc,
            description="Security group for Lambda functions",
            allow_all_outbound=True,
        )

        # Allow Lambda to connect to Valkey
        valkey_security_group.add_ingress_rule(
            lambda_security_group,
            aws_ec2.Port.tcp(6379),
            "Allow Lambda to access Valkey",
        )


        
        # 5. Create an IAM role for the EC2 instance
        # This allows us to connect through AWS Systems Manager.
        ec2_role = aws_iam.Role(
            self,
            "ProductApiEc2Role",
            assumed_by=aws_iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                aws_iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        # 6. Create a security group for EC2
        ec2_security_group = aws_ec2.SecurityGroup(
            self,
            "ProductApiEc2SecurityGroup",
            vpc=vpc,
            description="Security group for Product API EC2 instance",
            allow_all_outbound=True,
        )

        # No inbound SSH rule is required.
        # We will connect through AWS Systems Manager (SSM).

        # 7. Define EC2 User Data commands
        user_data_script = aws_ec2.UserData.for_linux()

        user_data_script.add_commands(
            # Update system packages
            "dnf update -y",

            # Install Python, pip and Git
            "dnf install -y python3 python3-pip git",

            # Create application directory
            "mkdir -p /home/ec2-user/app",

            # Create Python virtual environment
            "python3 -m venv /home/ec2-user/app/venv",

            # Upgrade pip inside the virtual environment
            "/home/ec2-user/app/venv/bin/pip install --upgrade pip",

            # Install application dependencies
            "/home/ec2-user/app/venv/bin/pip install flask gunicorn boto3",

            # Set directory ownership
            "chown -R ec2-user:ec2-user /home/ec2-user/app",
        )


        # 8. Create EC2 instance
        self.product_api_ec2 = aws_ec2.Instance(
            self,
            "ProductApiEC2Instance",
            instance_type=aws_ec2.InstanceType("t3.micro"),
            machine_image=aws_ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=aws_ec2.SubnetSelection(
                subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_group=ec2_security_group,
            role=ec2_role,
            user_data=user_data_script,
            require_imdsv2=True,
        )


        # --------------------------------------------------
        # 2. VALKEY SUBNET GROUP AND REPLICATION GROUP
        # --------------------------------------------------

        valkey_subnet_group = aws_elasticache.CfnSubnetGroup(
            self,
            "ValkeySubnetGroup",
            description="Private subnets for Product API Valkey",
            subnet_ids=[
                subnet.subnet_id
                for subnet in vpc.private_subnets
            ],
        )

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

        valkey_cluster.add_dependency(valkey_subnet_group)

        # --------------------------------------------------
        # 3. SQS QUEUES
        # --------------------------------------------------

        dlq = aws_sqs.Queue(
            self,
            "ProductApiDlq",
            queue_name="product-api-dlq",
            retention_period=Duration.days(14),
            visibility_timeout=Duration.seconds(300),
            receive_message_wait_time=Duration.seconds(20),
        )

        order_processing_dlq = aws_sqs.Queue(
            self,
            "OrderProcessingDLQ",
            queue_name="order-processing-dlq",
            retention_period=Duration.days(14),
            visibility_timeout=Duration.seconds(60),
        )

        order_processing_queue = aws_sqs.Queue(
            self,
            "OrderProcessingQueue",
            queue_name="order-processing-queue",
            # 6 times the 5-minute Lambda timeout
            visibility_timeout=Duration.minutes(30),
            retention_period=Duration.days(14),
            receive_message_wait_time=Duration.seconds(20),
            dead_letter_queue=aws_sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=order_processing_dlq,
            ),
        )

        # --------------------------------------------------
        # 4. SNS TOPICS
        # --------------------------------------------------

        customer_notifications_topic = aws_sns.Topic(
            self,
            "CustomerNotificationsTopic",
            topic_name="customer-notifications",
            display_name="Customer Notifications",
        )

        system_alerts_topic = aws_sns.Topic(
            self,
            "SystemAlertsTopic",
            topic_name="system-alerts",
            display_name="System Alerts",
        )

        inventory_alerts_topic = aws_sns.Topic(
            self,
            "InventoryAlertsTopic",
            topic_name="inventory-alerts",
            display_name="Inventory Alerts",
        )

        # --------------------------------------------------
        # 5. SNS SUBSCRIPTIONS AND FILTER POLICIES
        # --------------------------------------------------

        # Premium customer email subscription
        premium_subscription = (
            customer_notifications_topic.add_subscription(
                aws_sns_subscriptions.EmailSubscription(
                    "premium@example.com"
                )
            )
        )

        premium_subscription.subscription_filter_policy = {
            "customer_tier": aws_sns.SubscriptionFilter.string_filter(
                allowlist=["premium", "vip"]
            )
        }

        # Express and same-day order SMS subscription
        urgent_subscription = (
            customer_notifications_topic.add_subscription(
                aws_sns_subscriptions.SmsSubscription(
                    "+1234567890"
                )
            )
        )

        urgent_subscription.subscription_filter_policy = {
            "order_type": aws_sns.SubscriptionFilter.string_filter(
                allowlist=["express", "same_day"]
            )
        }

        # Inventory team receives critical inventory alerts only
        inventory_subscription = (
            inventory_alerts_topic.add_subscription(
                aws_sns_subscriptions.EmailSubscription(
                    "inventory-team@example.com"
                )
            )
        )

        inventory_subscription.subscription_filter_policy = {
            "urgency": aws_sns.SubscriptionFilter.string_filter(
                allowlist=["high"]
            )
        }

        # --------------------------------------------------
        # 6. DYNAMODB PRODUCTS TABLE
        # --------------------------------------------------

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

        products_table.add_global_secondary_index(
            index_name="category-index",
            partition_key=aws_dynamodb.Attribute(
                name="category",
                type=aws_dynamodb.AttributeType.STRING,
            ),
        )

        # --------------------------------------------------
        # 7. S3 PRODUCT IMAGES AND CUSTOMER ACTIVITY BUCKETS
        # --------------------------------------------------

        product_images_bucket = aws_s3.Bucket(
            self,
            "ProductImagesBucket",
            versioned=True,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            encryption=aws_s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

        # Bucket used by Kinesis Data Firehose
        # to store customer activity events.
        customer_activity_bucket = aws_s3.Bucket(
            self,
            "CustomerActivityBucket",
            versioned=True,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            encryption=aws_s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

        # Firehose assumes this role to write data to S3.
        firehose_role = aws_iam.Role(
            self,
            "CustomerActivityFirehoseRole",
            assumed_by=aws_iam.ServicePrincipal(
                "firehose.amazonaws.com"
            ),
        )

        customer_activity_bucket.grant_read_write(
            firehose_role
        )

        # Kinesis Data Firehose delivery stream.
        #
        # DirectPut means application code sends records
        # directly to Firehose using PutRecord/PutRecordBatch.
        customer_activity_stream = firehose.CfnDeliveryStream(
            self,
            "CustomerActivityStream",
            delivery_stream_name="customer-activity-stream",
            delivery_stream_type="DirectPut",
            s3_destination_configuration=(
                firehose.CfnDeliveryStream.S3DestinationConfigurationProperty(
                    bucket_arn=customer_activity_bucket.bucket_arn,
                    role_arn=firehose_role.role_arn,
                    prefix="customer-activity/",
                    buffering_hints=(
                        firehose.CfnDeliveryStream.BufferingHintsProperty(
                            size_in_m_bs=5,
                            interval_in_seconds=300,
                        )
                    ),
                    compression_format="GZIP",
                )
            ),
        )

        # --------------------------------------------------
        # 8. LAMBDA CONFIGURATION
        # --------------------------------------------------

        lambda_runtime = aws_lambda.Runtime.PYTHON_3_13
        code_location = "lambda_code"

        redis_layer = aws_lambda.LayerVersion(
            self,
            "RedisLayer",
            code=aws_lambda.Code.from_asset("layers/redis"),
            compatible_runtimes=[lambda_runtime],
            description="Redis Python client for Valkey integration",
        )

        valkey_environment = {
            "VALKEY_HOST": (
                valkey_cluster.attr_primary_end_point_address
            ),
            "VALKEY_PORT": (
                valkey_cluster.attr_primary_end_point_port
            ),
            "VALKEY_TLS": "true",
            "PRODUCT_CACHE_TTL": "3600",
            "SEARCH_CACHE_TTL": "1800",
            "CATEGORY_CACHE_TTL": "7200",
        }

        # --------------------------------------------------
        # 9. PRODUCT IMAGE LAMBDAS
        # --------------------------------------------------

        self.upload_product_image = aws_lambda.Function(
            self,
            "UploadProductImage",
            runtime=lambda_runtime,
            handler="upload_product_image.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        self.get_product_image = aws_lambda.Function(
            self,
            "GetProductImage",
            runtime=lambda_runtime,
            handler="get_product_image.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

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

        # --------------------------------------------------
        # 10. PRODUCT API LAMBDAS
        # --------------------------------------------------

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

        self.options = aws_lambda.Function(
            self,
            "Options",
            runtime=lambda_runtime,
            handler="options.handler",
            code=aws_lambda.Code.from_asset(code_location),
        )

        # --------------------------------------------------
        # 11. ORDER PROCESSOR LAMBDA
        # --------------------------------------------------

        self.order_processor = aws_lambda.Function(
            self,
            "OrderProcessor",
            runtime=lambda_runtime,
            handler="order_processor.handler",
            code=aws_lambda.Code.from_asset(code_location),
            timeout=Duration.seconds(300),
            memory_size=512,
            vpc=vpc,
            security_groups=[lambda_security_group],
            vpc_subnets=aws_ec2.SubnetSelection(
                subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            layers=[redis_layer],
            environment={
                **valkey_environment,
                "PRODUCTS_TABLE_NAME": products_table.table_name,
                "CUSTOMER_NOTIFICATIONS_TOPIC_ARN": (
                    customer_notifications_topic.topic_arn
                ),
                "SYSTEM_ALERTS_TOPIC_ARN": (
                    system_alerts_topic.topic_arn
                ),
                "INVENTORY_ALERTS_TOPIC_ARN": (
                    inventory_alerts_topic.topic_arn
                ),
                "CUSTOMER_ACTIVITY_STREAM_NAME": (
                    customer_activity_stream.ref
                ),
            },
        )

        # Connect OrderProcessor to SQS
        order_processing_queue.grant_consume_messages(
            self.order_processor
        )

        self.order_processor.add_event_source(
            aws_lambda_event_sources.SqsEventSource(
                order_processing_queue,
                batch_size=1,
                report_batch_item_failures=False,
            )
        )

        # Allow OrderProcessor to send customer activity
        # records directly to Kinesis Data Firehose.
        self.order_processor.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "firehose:PutRecord",
                    "firehose:PutRecordBatch",
                ],
                resources=[
                    customer_activity_stream.attr_arn,
                ],
            )
        )

        # --------------------------------------------------
        # 12. QUEUE MONITOR LAMBDA
        # --------------------------------------------------

        self.queue_monitor = aws_lambda.Function(
            self,
            "QueueMonitor",
            runtime=lambda_runtime,
            handler="queue_monitor.handler",
            code=aws_lambda.Code.from_asset(code_location),
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "ORDER_PROCESSING_QUEUE_URL": (
                    order_processing_queue.queue_url
                ),
            },
        )

        # --------------------------------------------------
        # 13. INVENTORY MONITOR LAMBDA
        # --------------------------------------------------

        self.inventory_monitor = aws_lambda.Function(
            self,
            "InventoryMonitor",
            runtime=lambda_runtime,
            handler="inventory_monitor.inventory_monitor_handler",
            code=aws_lambda.Code.from_asset(code_location),
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "PRODUCTS_TABLE_NAME": products_table.table_name,
                "INVENTORY_ALERTS_TOPIC_ARN": (
                    inventory_alerts_topic.topic_arn
                ),
            },
        )

        # --------------------------------------------------
        # 14. NOTIFICATION DISPATCHER LAMBDA
        # --------------------------------------------------

        self.notification_dispatcher = aws_lambda.Function(
            self,
            "NotificationDispatcher",
            runtime=lambda_runtime,
            handler=(
                "notification_dispatcher."
                "notification_dispatcher_handler"
            ),
            code=aws_lambda.Code.from_asset(code_location),
            timeout=Duration.seconds(60),
            memory_size=256,
        )

        # Subscribe dispatcher to system and inventory topics
        system_alerts_topic.add_subscription(
            aws_sns_subscriptions.LambdaSubscription(
                self.notification_dispatcher
            )
        )

        inventory_alerts_topic.add_subscription(
            aws_sns_subscriptions.LambdaSubscription(
                self.notification_dispatcher
            )
        )

        # --------------------------------------------------
        # 15. DYNAMODB ENVIRONMENT VARIABLES
        # --------------------------------------------------

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

        # --------------------------------------------------
        # 16. S3 ENVIRONMENT VARIABLES
        # --------------------------------------------------

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

        # --------------------------------------------------
        # 17. DYNAMODB PERMISSIONS
        # --------------------------------------------------

        products_table.grant_read_data(
            self.get_product
        )

        products_table.grant_read_data(
            self.query_products
        )

        products_table.grant_read_write_data(
            self.insert_product
        )

        products_table.grant_read_write_data(
            self.update_product
        )

        products_table.grant_write_data(
            self.update_product_images
        )

        products_table.grant_write_data(
            self.process_product_image
        )

        products_table.grant_read_write_data(
            self.order_processor
        )

        products_table.grant_read_write_data(
            self.inventory_monitor
        )

        # --------------------------------------------------
        # 18. SNS PUBLISH PERMISSIONS
        # --------------------------------------------------

        customer_notifications_topic.grant_publish(
            self.order_processor
        )

        system_alerts_topic.grant_publish(
            self.order_processor
        )

        inventory_alerts_topic.grant_publish(
            self.order_processor
        )

        inventory_alerts_topic.grant_publish(
            self.inventory_monitor
        )

        # --------------------------------------------------
        # 19. S3 PERMISSIONS
        # --------------------------------------------------

        product_images_bucket.grant_read(
            self.get_product
        )

        product_images_bucket.grant_read_write(
            self.insert_product
        )

        product_images_bucket.grant_read_write(
            self.update_product
        )

        product_images_bucket.grant_put(
            self.upload_product_image
        )

        product_images_bucket.grant_read(
            self.get_product_image
        )

        product_images_bucket.grant_read_write(
            self.process_product_image
        )

        # --------------------------------------------------
        # 20. QUEUE MONITOR PERMISSIONS
        # --------------------------------------------------

        order_processing_queue.grant(
            self.queue_monitor,
            "sqs:GetQueueAttributes",
        )

        self.queue_monitor.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "cloudwatch:GetMetricStatistics"
                ],
                resources=["*"],
            )
        )

        # --------------------------------------------------
        # 21. EVENTBRIDGE SCHEDULES
        # --------------------------------------------------

        # Monitor order queue every 5 minutes
        monitoring_schedule = events.Rule(
            self,
            "QueueMonitoringSchedule",
            schedule=events.Schedule.rate(
                Duration.minutes(5)
            ),
        )

        monitoring_schedule.add_target(
            targets.LambdaFunction(
                self.queue_monitor
            )
        )

        # Monitor inventory every 15 minutes
        inventory_monitor_schedule = events.Rule(
            self,
            "InventoryMonitorSchedule",
            schedule=events.Schedule.rate(
                Duration.minutes(15)
            ),
        )

        inventory_monitor_schedule.add_target(
            targets.LambdaFunction(
                self.inventory_monitor
            )
        )

        # --------------------------------------------------
        # 22. S3 EVENT NOTIFICATION
        # --------------------------------------------------

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

        # --------------------------------------------------
        # 23. API GATEWAY
        # --------------------------------------------------

        api = apigw.RestApi(
            self,
            "ProductsAPI",
            deploy_options=apigw.StageOptions(
                stage_name="dev"
            ),
        )

        products = api.root.add_resource("products")

        # GET /products
        products.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.query_products
            ),
        )

        # POST /products
        products.add_method(
            "POST",
            apigw.LambdaIntegration(
                self.insert_product
            ),
        )

        products.add_method(
            "OPTIONS",
            apigw.LambdaIntegration(
                self.options
            ),
        )

        # /products/{id}
        product_by_id = products.add_resource("{id}")

        product_by_id.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.get_product
            ),
        )

        product_by_id.add_method(
            "PUT",
            apigw.LambdaIntegration(
                self.update_product
            ),
        )

        product_by_id.add_method(
            "OPTIONS",
            apigw.LambdaIntegration(
                self.options
            ),
        )

        # /products/{id}/image
        image = product_by_id.add_resource("image")

        image.add_method(
            "POST",
            apigw.LambdaIntegration(
                self.upload_product_image
            ),
        )

        image.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.get_product_image
            ),
        )

        image.add_method(
            "PUT",
            apigw.LambdaIntegration(
                self.update_product_images
            ),
        )

        image.add_method(
            "OPTIONS",
            apigw.LambdaIntegration(
                self.options
            ),
        )

        # --------------------------------------------------
        # 24. CLOUDFORMATION OUTPUTS
        # --------------------------------------------------

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
            "OrderProcessingQueueUrl",
            value=order_processing_queue.queue_url,
            description=(
                "SQS queue URL for background order processing"
            ),
        )

        CfnOutput(
            self,
            "OrderProcessingDlqUrl",
            value=order_processing_dlq.queue_url,
            description="SQS dead-letter queue URL",
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
            description="Valkey primary endpoint port",
        )

        CfnOutput(
            self,
            "CustomerActivityStreamName",
            value=customer_activity_stream.ref,
            description=(
                "Kinesis Data Firehose delivery stream "
                "for customer activity"
            ),
        )

        CfnOutput(
            self,
            "CustomerActivityBucketName",
            value=customer_activity_bucket.bucket_name,
            description=(
                "S3 bucket containing customer activity data"
            ),
        )

        CfnOutput(
            self,
            "ProductApiEC2InstanceId",
            value=self.product_api_ec2.instance_id,
            description="Product API EC2 instance ID",
        )

        CfnOutput(
            self,
            "ProductApiEC2PrivateIp",
            value=self.product_api_ec2.instance_private_ip,
            description="Product API EC2 private IP address",
        )