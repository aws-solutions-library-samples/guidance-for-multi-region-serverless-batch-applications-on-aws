# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import boto3
from aws_lambda_powertools import Logger, Tracer, Metrics
metrics = Metrics()
tracer = Tracer()
logger = Logger()
s3_client = boto3.client('s3')

@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    bucket = event['bucket']
    key = event['key']
    to_process_folder = event['toProcessFolder']
    data = []
    output_path = to_process_folder.replace("to_process", "output")

    output = []

    header_text = [
        'uuid',
        'Country',
        'Item Type',
        'Sales Channel',
        'Order Priority',
        'Order Date',
        'Region',
        'Ship Date',
        'Units Sold',
        'Unit Price',
        'Unit Cost',
        'Total Revenue',
        'Total Cost',
        'Total Profit'

    ]

    output.append(",".join(header_text) + "\n")

    try:
        for item in s3_client.list_objects_v2(Bucket=bucket, Prefix=output_path)['Contents']:
            if item['Key'].endswith('.csv'):
                resp = s3_client.select_object_content(
                    Bucket=bucket,
                    Key=item['Key'],
                    ExpressionType='SQL',
                    Expression="select * from s3object",
                    InputSerialization={'CSV': {"FileHeaderInfo": "NONE"}, 'CompressionType': 'NONE'},
                    OutputSerialization={'CSV': {}},
                )

                for event in resp['Payload']:
                    if 'Records' in event:
                        records = event['Records']['Payload'].decode('utf-8')
                        payloads = (''.join(response for response in records))
                        output.append(payloads)

        output_body = "".join(output)
        s3_target_key = output_path + "/" + get_output_filename(key)
        response = s3_client.put_object(Bucket=bucket,
                                        Key=s3_target_key,
                                        Body=output_body)

        line_num = 0
        lines = output_body.splitlines();
        for line in lines:
            words = line.split(",")
            if line_num > 0:
                data.append(words[0])
            line_num += 1

        logger.info("Data", input_file=key, data=data)
        return {"response": response, "S3OutputFileName": s3_target_key, "originalFileName": key}

    except Exception as e:
        logger.exception("Exception occurred while merging files")
        raise Exception(str(e))


def get_output_filename(key):
    last_part_pos = key.rfind("/")
    if last_part_pos == -1:
        return ""
    last_part_pos += 1
    input_file_name = key[last_part_pos:]

    return "completed/" + input_file_name
