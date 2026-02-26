import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

logger = Logger()
metrics = Metrics()

dynamodb = boto3.resource("dynamodb")


class ActiveRegionNotFoundError(Exception):
    """Raised when the active region record does not exist in the table."""


class DynamoDBReadError(Exception):
    """Raised when a DynamoDB read operation fails."""


def get_active_region(table_name: str) -> str:
    """
    Read the active region from DynamoDB with strong consistency.

    Args:
        table_name: Name of the ActiveRegion DynamoDB table.

    Returns:
        AWS region string (e.g., "us-east-1").

    Raises:
        ActiveRegionNotFoundError: If no active region record exists.
        DynamoDBReadError: If the read operation fails.
    """
    table = dynamodb.Table(table_name)

    try:
        response = table.get_item(
            Key={"pk": "ACTIVE_REGION"},
            ConsistentRead=True,
        )
    except ClientError as exc:
        logger.error(
            "Failed to read active region record",
            extra={
                "exceptionType": type(exc).__name__,
                "tableName": table_name,
                "error": str(exc),
            },
        )
        raise DynamoDBReadError(
            f"Failed to read from {table_name}: {exc}"
        ) from exc

    item = response.get("Item")
    if item is None:
        metrics.add_metric(
            name="ActiveRegionNotFound",
            unit=MetricUnit.Count,
            value=1,
        )
        logger.warning(
            "Active region record not found",
            extra={"tableName": table_name},
        )
        raise ActiveRegionNotFoundError(
            f"No active region record found in {table_name}"
        )

    return item["region"]
