import json
import os
import boto3
from aws_lambda_powertools import Logger, Tracer, Metrics

logger = Logger()
tracer = Tracer()
metrics = Metrics()
sfn_client = boto3.client("stepfunctions")


@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def handler(event, context):
    """Fire-and-forget trigger for delayed reconciliation state machine."""
    state_machine_arn = os.environ["STATE_MACHINE_ARN"]

    response = sfn_client.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps({"trigger": "arc-region-switch", "event": event}),
    )

    logger.info({"execution_arn": response["executionArn"]})

    return {
        "statusCode": 200,
        "executionArn": response["executionArn"],
    }
