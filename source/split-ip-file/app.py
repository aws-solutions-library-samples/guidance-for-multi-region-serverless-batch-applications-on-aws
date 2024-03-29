# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import uuid

import s3fs
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics()
tracer = Tracer()
logger = Logger()
# S3 bucket info
s3 = s3fs.S3FileSystem(anon=False)


@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    input_archive_folder = event['inputArchiveFolder']
    to_process_folder = str(uuid.uuid4()) + "/" + "to_process"
    file_row_limit = event['fileChunkSize']
    file_delimiter = event['fileDelimiter']
    output_path = to_process_folder.replace("to_process", "output")

    record = event['Records']

    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']
    logger.append_keys(s3_object_key=key)
    create_start_indicator(bucket, output_path)
    input_file = os.path.join(bucket, key)
    archive_path = os.path.join(bucket, input_archive_folder, os.path.basename(key))
    folder = os.path.split(key)[0]
    s3_url = os.path.join(bucket, folder)
    output_file_template = os.path.splitext(os.path.basename(key))[0] + "__part"
    output_path = os.path.join(bucket, to_process_folder)

    # Number of files to be created
    num_files = file_count(s3.open(input_file, 'r'), file_delimiter, file_row_limit)
    # Split the input file into several files, each with the number of records mentioned in the fileChunkSize parameter.
    splitFileNames = split(input_file,
                           s3.open(input_file, 'r'),
                           file_delimiter,
                           file_row_limit,
                           output_file_template,
                           output_path, True,
                           num_files)
    # Archive the input file.
    archive(input_file, archive_path)

    response = {"bucket": bucket, "key": key, "splitFileNames": splitFileNames,
                "toProcessFolder": to_process_folder}
    metrics.add_metric(name="InputFilesSplit", unit=MetricUnit.Count, value=1)
    logger.info(response)
    return response


# Determine the number of files that this Lambda function will create.
def file_count(file_handler, delimiter, row_limit):
    import csv
    reader = csv.reader(file_handler, delimiter=delimiter)
    # Figure out the number of files this function will generate.
    row_count = sum(1 for row in reader) - 1
    # If there's a remainder, always round up.
    file_count = int(row_count // row_limit) + (row_count % row_limit > 0)
    return file_count


# Split the input into several smaller files.
def split(input_file, filehandler, delimiter, row_limit, output_name_template, output_path, keep_headers, num_files):
    import csv
    reader = csv.reader(filehandler, delimiter=delimiter)
    split_file_path = []
    data = []
    current_piece = 1
    current_out_path = os.path.join(
        output_path,
        output_name_template + str(current_piece) + "__of" + str(num_files) + ".csv"
    )
    split_file_path.append(current_out_path)
    current_out_writer = csv.writer(s3.open(current_out_path, 'w'), delimiter=delimiter, quoting=csv.QUOTE_ALL)
    current_limit = row_limit
    if keep_headers:
        headers = next(reader)
        current_out_writer.writerow(headers)
    for i, row in enumerate(reader):
        if i + 1 > current_limit:
            current_piece += 1
            current_limit = row_limit * current_piece
            current_out_path = os.path.join(
                output_path,
                output_name_template + str(current_piece) + "__of" + str(num_files) + ".csv"
            )
            split_file_path.append(current_out_path)
            current_out_writer = csv.writer(s3.open(current_out_path, 'w'), delimiter=delimiter, quoting=csv.QUOTE_ALL)
            if keep_headers:
                current_out_writer.writerow(headers)
        current_out_writer.writerow(row)
        data.append(row[0])
    logger.info("Data", input_file=input_file, data=data)
    return split_file_path


@tracer.capture_method
# Move the original input file into an archive folder.
def archive(input_file, archive_path):
    s3.copy(input_file, archive_path)
    s3.rm(input_file)


def create_start_indicator(bucket, folder_name):
    response = s3.touch(bucket + "/" + folder_name + "/_started")
