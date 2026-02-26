"""
Active Region Monitor Lambda.

Periodically reads the active region from DynamoDB and the MRAP routing
configuration, then publishes custom CloudWatch metrics so the dashboard
can display which region is active according to each source.

Metrics published (namespace: MultiRegionBatch{Env}):
  - ActiveRegionDynamo: 1 for the active region, 0 for the other
  - ActiveRegionMRAP:   traffic dial percentage per region (100=active, 0=passive)
"""

import os

import boto3
from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

logger = Logger()
metrics = Metrics()

dynamodb = boto3.resource("dynamodb")

FAILOVER_CONTROL_REGIONS = ["us-east-1", "us-west-2", "ap-southeast-2", "ap-northeast-1", "eu-west-1"]


def _get_dynamo_active_region(table_name: str) -> str:
    table = dynamodb.Table(table_name)
    resp = table.get_item(Key={"pk": "ACTIVE_REGION"}, ConsistentRead=True)
    item = resp.get("Item")
    return item["region"] if item else ""


def _get_mrap_routes(account_id: str, mrap_arn: str) -> list:
    region = os.environ.get("AWS_REGION", "us-east-1")
    ctrl_region = region if region in FAILOVER_CONTROL_REGIONS else "us-east-1"
    client = boto3.client("s3control", region_name=ctrl_region)
    resp = client.get_multi_region_access_point_routes(
        AccountId=account_id, Mrap=mrap_arn,
    )
    return resp.get("Routes", [])


@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
def handler(event, context):
    table_name = os.environ["ACTIVE_REGION_TABLE"]
    account_id = os.environ["ACCOUNT_ID"]
    mrap_alias = os.environ["MRAP_ALIAS"]
    primary_region = os.environ["PRIMARY_REGION"]
    secondary_region = os.environ["SECONDARY_REGION"]
    regions = [primary_region, secondary_region]

    mrap_arn = f"arn:aws:s3::{account_id}:accesspoint/{mrap_alias}"

    cw = boto3.client("cloudwatch")

    # --- DynamoDB active region ---
    dynamo_region = _get_dynamo_active_region(table_name)
    logger.info("DynamoDB active region", extra={"activeRegion": dynamo_region})

    dynamo_metrics = []
    for r in regions:
        dynamo_metrics.append({
            "MetricName": "ActiveRegionDynamo",
            "Dimensions": [{"Name": "Region", "Value": r}],
            "Value": 1.0 if r == dynamo_region else 0.0,
            "Unit": "None",
        })

    # --- MRAP routing ---
    mrap_metrics = []
    try:
        routes = _get_mrap_routes(account_id, mrap_arn)
        for route in routes:
            r = route.get("Region", "")
            dial = route.get("TrafficDialPercentage", 0)
            logger.info("MRAP route", extra={"region": r, "trafficDial": dial})
            if r in regions:
                mrap_metrics.append({
                    "MetricName": "ActiveRegionMRAP",
                    "Dimensions": [{"Name": "Region", "Value": r}],
                    "Value": float(dial),
                    "Unit": "None",
                })
    except Exception as exc:
        logger.error("Failed to read MRAP routes", extra={"error": str(exc)})

    namespace = os.environ.get("POWERTOOLS_METRICS_NAMESPACE", "MultiRegionBatch")
    all_metrics = dynamo_metrics + mrap_metrics
    if all_metrics:
        cw.put_metric_data(Namespace=namespace, MetricData=all_metrics)

    return {"statusCode": 200, "dynamoActiveRegion": dynamo_region}
