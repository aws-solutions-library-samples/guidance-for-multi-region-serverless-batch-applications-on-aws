import os
import time

import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer, Metrics

metrics = Metrics()
tracer = Tracer()
logger = Logger()

# S3 MRAP failover control endpoints — requests must go through one of these regions
FAILOVER_CONTROL_REGIONS = [
    "us-east-1",
    "us-west-2",
    "ap-southeast-2",
    "ap-northeast-1",
    "eu-west-1",
]


@tracer.capture_method
def _get_s3control_client():
    """Return an S3Control client targeting the nearest failover control endpoint."""
    current_region = os.environ.get("AWS_REGION", "us-east-1")
    region = current_region if current_region in FAILOVER_CONTROL_REGIONS else "us-east-1"
    return boto3.client("s3control", region_name=region)


@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def handler(event: dict, context) -> dict:
    """
    MRAP Routing Lambda handler.

    Invoked by the ARC Region Switch Plan to update the S3 Multi-Region
    Access Point routing configuration so that requests are directed to
    the region becoming active.

    Environment variables:
        ACCOUNT_ID          – AWS account ID that owns the MRAP
        MRAP_ARN            – The MRAP ARN (e.g. arn:aws:s3::123456789012:accesspoint/alias)
        PRIMARY_REGION      – Primary region identifier
        SECONDARY_REGION    – Secondary region identifier
        PRIMARY_BUCKET      – S3 bucket name in the primary region
        SECONDARY_BUCKET    – S3 bucket name in the secondary region

    Event payload:
        {
            "region": "us-east-1",       # region becoming active
            "executionId": "exec-123"
        }

    Returns:
        {
            "statusCode": 200,
            "activeRegion": "us-east-1",
            "message": "MRAP routing updated"
        }
    """
    target_region = event.get("region") or os.environ["AWS_REGION"]
    account_id = os.environ["ACCOUNT_ID"]
    mrap_alias = os.environ["MRAP_ARN"]  # This is actually the MRAP alias from the secret
    primary_region = os.environ["PRIMARY_REGION"]
    secondary_region = os.environ["SECONDARY_REGION"]
    primary_bucket = os.environ["PRIMARY_BUCKET"]
    secondary_bucket = os.environ["SECONDARY_BUCKET"]

    # Build the full MRAP ARN from the alias and account ID
    mrap_arn = f"arn:aws:s3::{account_id}:accesspoint/{mrap_alias}"

    # Build route updates: active region gets 100, other gets 0
    if target_region == primary_region:
        route_updates = [
            {"Bucket": primary_bucket, "Region": primary_region, "TrafficDialPercentage": 100},
            {"Bucket": secondary_bucket, "Region": secondary_region, "TrafficDialPercentage": 0},
        ]
    else:
        route_updates = [
            {"Bucket": primary_bucket, "Region": primary_region, "TrafficDialPercentage": 0},
            {"Bucket": secondary_bucket, "Region": secondary_region, "TrafficDialPercentage": 100},
        ]

    client = _get_s3control_client()

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            client.submit_multi_region_access_point_routes(
                AccountId=account_id,
                Mrap=mrap_arn,
                RouteUpdates=route_updates,
            )

            logger.info(
                "MRAP routing updated",
                extra={
                    "activeRegion": target_region,
                    "mrapArn": mrap_arn,
                    "routeUpdates": route_updates,
                },
            )

            return {
                "statusCode": 200,
                "activeRegion": target_region,
                "message": "MRAP routing updated",
            }
        except ClientError as exc:
            logger.error(
                "Failed to update MRAP routing",
                extra={
                    "attempt": attempt,
                    "maxAttempts": max_attempts,
                    "exceptionType": type(exc).__name__,
                    "mrapArn": mrap_arn,
                    "error": str(exc),
                },
            )
            if attempt < max_attempts:
                time.sleep(2 ** (attempt - 1))

    return {
        "statusCode": 500,
        "error": f"Failed to update MRAP routing after {max_attempts} attempts",
        "activeRegion": target_region,
        "mrapArn": mrap_arn,
    }
