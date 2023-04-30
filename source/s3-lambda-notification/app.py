# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import os
import boto3
import time
import logging
from datetime import date, datetime
import dns.resolver
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics()
tracer = Tracer()
logger = Logger()

state_machine_client = boto3.client('stepfunctions')
dynamodb = boto3.resource('dynamodb')

@tracer.capture_method
def write_to_ddb(fileName, status, process_date, start_time, param):
    table_name = os.environ['BATCH_STATE_DDB']
    table = dynamodb.Table(table_name)
    runtime_region = os.environ['AWS_REGION']
    event_object = json.dumps(param)
    response = table.put_item(
        Item={
            'fileName': fileName,
            'status': status,
            'processDate': process_date,
            'startTime': start_time,
            'processingInitializedRegion': runtime_region,
            's3NotificationEvent': event_object

        }
    )
    return response

@tracer.capture_method
def resolve_secret_value(param):
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=os.environ['AWS_REGION'],
    )
    get_secret_value_response = client.get_secret_value(
        SecretId=param
    )
    return get_secret_value_response['SecretString']

@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    domain_name = resolve_secret_value(os.environ['DNS_RECORD_SECRET'])
    answers = dns.resolver.query(domain_name, 'TXT')
    primary_region = answers[0].to_text().replace('"', '')
    current_region = os.environ['AWS_REGION']
    logger.info({"Primary Region": primary_region, "Current Region": current_region})
    if current_region == primary_region:
        for record in event['Records']:
            param = {
                "Records": record,
                "inputArchiveFolder": os.environ['INPUT_ARCHIVE_FOLDER'],
                "fileChunkSize": int(os.environ['FILE_CHUNK_SIZE']),
                "fileDelimiter": os.environ['FILE_DELIMITER']

            }
            state_machine_arn = os.environ['STATE_MACHINE_ARN']
            state_machine_execution_name = os.environ['STATE_MACHINE_EXECUTION_NAME'] + str(time.time())
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            current_date = date.today().strftime('%m/%d/%Y')
            current_time = datetime.now().strftime("%H:%M:%S")
            responseData = {}
            try:
                responseData['step_function_response'] = state_machine_client.start_execution(
                    stateMachineArn=state_machine_arn,
                    name=state_machine_execution_name,
                    input=json.dumps(param)
                )
                write_to_ddb(key, 'INITIALIZED', current_date, current_time, param)
                responseData['ddb_state_table_put'] = 'SUCCESS'
                logging.info({"File": key, "Bucket": bucket, "Status": "Initialized", "Response Data": responseData})
            except Exception as err:
                logger.exception({"Input File Processing Error":  key})
                write_to_ddb(key, 'FAILED', current_date, current_time, param)
                responseData['ddb_state_table_put'] = 'FAILED'
                logging.info({"File": key, "Bucket": bucket, "Status": "Failed", "Response Data": responseData})
    else:
        logger.info("Current Region is not primary region, hence skipping the processing")
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            logging.info({"File": key, "Bucket": bucket, "Status": "Skipped"})