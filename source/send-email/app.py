# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import base64
import hashlib
import hmac
import json
import os
import smtplib
from email.message import EmailMessage

import boto3
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics()
tracer = Tracer()
logger = Logger()
s3_client = boto3.client('s3')
ddb_client = boto3.resource('dynamodb')

@tracer.capture_method
def get_mrap_alias(mrap_alias_secret):
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=os.environ['AWS_REGION'],
    )
    get_secret_value_response = client.get_secret_value(
        SecretId=mrap_alias_secret
    )
    return get_secret_value_response['SecretString']

@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    sender = event['sender']
    recipient = event['recipient']

    s3_output_file = event['s3OutputFileName']
    original_file_name = event['originalFileName']

    logger.info({"original file name": original_file_name})

    update_status(original_file_name)
    logger.info("Status updated in Batch Status Table")
    account_id = context.invoked_function_arn.split(":")[4]
    mrap_alias = get_mrap_alias(os.environ['MRAP_ALIAS_SECRET'])
    pre_signed_url = generate_s3_signed_url(account_id, mrap_alias, s3_output_file)
    logger.info("Generated Presigned URL")

    send_email(sender, recipient, pre_signed_url)
    metrics.add_metric(name="EmailSent", unit=MetricUnit.Count, value=1)

    return {"response": "success"}

@tracer.capture_method
def generate_s3_signed_url(account_id, mrap_alias, s3_target_key):
    return s3_client.generate_presigned_url(HttpMethod='GET',
                                            ClientMethod='get_object',
                                            Params={'Bucket': 'arn:aws:s3::' + account_id + ':accesspoint/' + mrap_alias,
                                                    'Key': s3_target_key},
                                            ExpiresIn=3600)

@tracer.capture_method
def update_status(file_name):
    status = 'COMPLETED'
    table_name = os.environ['BATCH_STATE_DDB']
    runtime_region = os.environ['AWS_REGION']
    logger.info({"current_region", runtime_region})
    table = ddb_client.Table(table_name)
    response = table.update_item(
        Key={'fileName': file_name},
        UpdateExpression="set #status = :s, #completedRegion = :cRegion",
        ExpressionAttributeValues={
            ':s': status,
            ':cRegion': runtime_region
        },
        ExpressionAttributeNames={
            '#status': 'status',
            '#completedRegion': 'processingCompletedRegion'
        },
        ReturnValues="UPDATED_NEW")

    return response

@tracer.capture_method
def send_email(sender, recipient, pre_signed_url):
    # The subject line for the email.
    subject = "Batch Processing complete: Output file information"

    # The HTML body of the email.
    body_html = """<html>
    <head></head>
    <body>
      <h1>The file has been processed successfully</h1>
      <p>Click the pre-signed S3 URL to access the output file:
        <a href='{url}'>Output File</a></p>
      <p>The link will expire in 60 minutes.</p>
    </body>
    </html>""".format(url=pre_signed_url)

    # construct email
    email = EmailMessage()
    email['Subject'] = subject
    email['From'] = sender
    email['To'] = recipient
    email.set_content(body_html, subtype='html')
    # Try to send the email.
    try:
        smtp_credentials = get_smtp_credentials()
        response = transmit_email(email, smtp_credentials)
    except Exception as e:
        logger.exception('Unable to send email')
    else:
        logger.info("EMail sent!")

@tracer.capture_method
def transmit_email(email, smtp_credentials):
    username = smtp_credentials['AccessKey']
    password = calculate_key(smtp_credentials['SecretAccessKey'], os.environ['AWS_REGION'])
    server = smtplib.SMTP(os.environ['SMTP_HOST'], 25)
    server.starttls()
    server.login(username, password)
    response = server.send_message(email)
    server.close()
    return response

@tracer.capture_method
def get_smtp_credentials():
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=os.environ['AWS_REGION'],
    )
    get_secret_value_response = client.get_secret_value(
        SecretId=os.environ['SMTP_CREDENTIAL_SECRET']
    )
    json_secret_value = json.loads(get_secret_value_response['SecretString'])
    return json_secret_value


# These values are required to calculate the signature. Do not change them.
DATE = "11111111"
SERVICE = "ses"
MESSAGE = "SendRawEmail"
TERMINAL = "aws4_request"
VERSION = 0x04


def sign(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()


def calculate_key(secret_access_key, region):
    signature = sign(("AWS4" + secret_access_key).encode('utf-8'), DATE)
    signature = sign(signature, region)
    signature = sign(signature, SERVICE)
    signature = sign(signature, TERMINAL)
    signature = sign(signature, MESSAGE)
    signature_and_version = bytes([VERSION]) + signature
    smtp_password = base64.b64encode(signature_and_version)
    return smtp_password.decode('utf-8')
