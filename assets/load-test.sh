#!/bin/bash
#set -xv

usage() { echo "Usage: $0 [-a <s3 mrap ARN>] [-r <number of batch file runs>] [-w <wait between uploads>]" 1>&2; exit 1; }

while getopts ":a:r:w:" opt; do
  case $opt in
    a)  
      S3_MRAP_ARN=$OPTARG
      ;;  
    r)
      RUNS=$OPTARG
      ;;
    w)
      INTERVAL=$OPTARG
      ;;
  esac
done
shift $((OPTIND-1))

if [ -z "$S3_MRAP_ARN" ] || [ -z "$RUNS" ] || [ -z "$INTERVAL" ]; then
  usage
fi

echo "S3 MRAP ARN: $S3_MRAP_ARN"
echo "Number of batch file runs: $RUNS"
echo "Wait between uploads: $INTERVAL"
echo "Starting Load Test..."

for i in $(seq 1 $RUNS);
do
  fileName=testfile_$i.csv
  aws s3 cp testfile.csv s3://$S3_MRAP_ARN/input/$fileName
  echo "Uploaded File: $fileName"
  sleep $INTERVAL
done