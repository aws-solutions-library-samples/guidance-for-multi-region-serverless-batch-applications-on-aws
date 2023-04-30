# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from aws_lambda_powertools.utilities.validation import validate
from aws_lambda_powertools.utilities.validation.exceptions import SchemaValidationError
import schemas

from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics()
tracer = Tracer()
logger = Logger()

@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    try:
        validate(event=event, schema=schemas.INPUT)
    except SchemaValidationError as e:
        return {"response": "failure", "error": e}

    return {"response": "success"}
