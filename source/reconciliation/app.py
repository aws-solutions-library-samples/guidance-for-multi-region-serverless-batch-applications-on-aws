import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics()
tracer = Tracer()
logger = Logger()
ddb_client = boto3.resource('dynamodb')
s3 = boto3.resource('s3')

@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    table_name = os.environ['BATCH_STATE_DDB']
    # runtime_region = os.environ['AWS_REGION']
    secondary_region_bucket = os.environ['SECONDARY_REGION_BUCKET']
    table = ddb_client.Table(table_name)
    resp = table.query(
        # Add the name of the index you want to use in your query.
        IndexName="status-index",
        KeyConditionExpression=Key('status').eq('INITIALIZED'))
    logger.info({"Number of total unprocessed files:", len(resp['Items'])})
    copied_files = []
    for item in resp['Items']:
        logger.info(item)
        record_obj = item['s3NotificationEvent']
        logger.info({'s3_event_record_obj: ', json.dumps(record_obj)})
        s3_event = json.loads(record_obj)
        key = s3_event['Records']['s3']['object']['key']
        try:
            copy_source = {
                'Bucket': secondary_region_bucket,
                'Key': key
            }
            bucket = s3.Bucket(secondary_region_bucket)
            response_data = bucket.copy(copy_source, key)
            logger.info({"----- file copied successfully: ", json.dumps(response_data)})

        except Exception as err:
            logger.exception({"Error while copying Input File:", key})

        else:
            copied_files.append(key)
            logger.info({"file submitted for processing": key, "response_data": json.dumps(response_data)})
    metrics.add_metric(name="ReconciledFiles", unit=MetricUnit.Count, value=len(copied_files))
    return {
        'num_files_submitted_for_reconciliation': len(copied_files),
        'file_list': copied_files
    }
