import os
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer, Metrics

metrics = Metrics()
tracer = Tracer()
logger = Logger()

dynamodb = boto3.resource("dynamodb")


@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def handler(event: dict, context) -> dict:
    """
    Region Writer Lambda handler.

    Invoked by the ARC Region Switch Plan to write the active region record
    to the DynamoDB global table.

    Returns:
    {
        "statusCode": 200,
        "region": "us-east-1",
        "updatedAt": "2024-01-15T10:30:00Z"
    }
    """
    region = os.environ["AWS_REGION"]
    table_name = os.environ["ACTIVE_REGION_TABLE"]
    # Build updatedBy from event context — use executionId if present, fall back to
    # planArn, or the full event as a last resort for traceability.
    updated_by = (
        event.get("executionId")
        or event.get("planArn")
        or str(event)
    )
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    table = dynamodb.Table(table_name)

    # Write the active region record
    item = {
        "pk": "ACTIVE_REGION",
        "region": region,
        "updatedAt": updated_at,
        "updatedBy": updated_by,
    }

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            table.put_item(Item=item)

            logger.info(
                "Active region record written",
                extra={
                    "region": region,
                    "updatedAt": updated_at,
                    "updatedBy": updated_by,
                    "tableName": table_name,
                },
            )

            return {
                "statusCode": 200,
                "region": region,
                "updatedAt": updated_at,
            }
        except ClientError as exc:
            logger.error(
                "Failed to write active region record",
                extra={
                    "attempt": attempt,
                    "maxAttempts": max_attempts,
                    "exceptionType": type(exc).__name__,
                    "tableName": table_name,
                    "error": str(exc),
                },
            )
            if attempt < max_attempts:
                backoff = 2 ** (attempt - 1)
                time.sleep(backoff)

    return {
        "statusCode": 500,
        "error": f"Failed to write active region record after {max_attempts} attempts",
        "region": region,
        "tableName": table_name,
    }
