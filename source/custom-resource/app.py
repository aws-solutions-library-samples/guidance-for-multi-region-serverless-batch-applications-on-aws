# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import csv
import json

import boto3
from aws_lambda_powertools import Logger, Tracer, Metrics

import cfnresponse

s3Client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

metrics = Metrics()
tracer = Tracer()
logger = Logger()


@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    logger.info('Received event: %s' % json.dumps(event))

    status = cfnresponse.FAILED
    new_physical_id = None

    try:
        properties = event.get('ResourceProperties')
        physical_id = event.get('PhysicalResourceId')

        status, new_physical_id = {
            'Create': create,
            'Update': update,
            'Delete': delete
        }.get(event['RequestType'], lambda x, y: (cfnresponse.FAILED, None))(properties, physical_id)
    except Exception as e:
        logger.exception('Exception: %s' % e)
        status = cfnresponse.FAILED
    finally:
        cfnresponse.send(event, context, status, {}, new_physical_id)


@tracer.capture_method
def add_bucket_notification(bucket_name, notification_id, function_arn):
    notification_response = s3Client.put_bucket_notification_configuration(
        Bucket=bucket_name,
        NotificationConfiguration={
            'LambdaFunctionConfigurations': [
                {
                    'Id': notification_id,
                    'LambdaFunctionArn': function_arn,
                    'Events': [
                        's3:ObjectCreated:*'
                    ],
                    'Filter': {
                        'Key': {
                            'FilterRules': [
                                {
                                    'Name': 'prefix',
                                    'Value': 'input/'
                                },
                                {
                                    'Name': 'suffix',
                                    'Value': 'csv'
                                },
                            ]
                        }
                    }
                },
            ]
        }
    )
    return notification_response


def load_csv_data(table_name):
    csv_file = "testfile_financial_data.csv"

    batch_size = 100
    batch = []

    for row in csv.DictReader(open(csv_file)):
        if len(batch) >= batch_size:
            write_to_dynamo(batch, table_name)
            batch.clear()
        batch.append(row)

    if batch:
        write_to_dynamo(batch, table_name)

    return {
        'statusCode': 200,
        'body': json.dumps('CSV file loaded into the DYnamoDB table')
    }


@tracer.capture_method
def write_to_dynamo(rows, table_name):
    try:
        table = dynamodb.Table(table_name)
    except:
        logger.exception("Error loading DynamoDB table. Check if table was created correctly and environment variable.")

    try:
        with table.batch_writer() as batch:
            for i in range(len(rows)):
                batch.put_item(
                    Item=rows[i]
                )
    except Exception as e:
        logger.exception("Exception occurred")


def create(properties, physical_id):
    bucket_name = properties['S3Bucket']
    notification_id = properties['NotificationId']
    function_arn = properties['FunctionARN']
    table_name = properties['FinancialTableName']
    response = add_bucket_notification(bucket_name, notification_id, function_arn)
    logger.info('AddBucketNotification response: %s' % json.dumps(response))
    logger.info('Loading table: %s' % table_name)
    response = load_csv_data(table_name)
    logger.info('AddBucketNotification response: %s' % json.dumps(response))

    return cfnresponse.SUCCESS, physical_id


def update(properties, physical_id):
    return cfnresponse.SUCCESS, None


def delete(properties, physical_id):
    return cfnresponse.SUCCESS, None
