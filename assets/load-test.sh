#!/bin/bash
#set -xv

usage() {
  echo "Usage: $0 [-a <S3 MRAP full ARN>] [-r <number of batch file runs>] [-w <wait in seconds between uploads>]"
  echo ""
  echo "  -a  S3 Multi-Region Access Point full ARN (not the alias)"
  echo "      Example: arn:aws:s3::123456789012:accesspoint/mfprmw49gbimn.mrap"
  echo "  -r  Number of test file uploads"
  echo "  -w  Wait time in seconds between uploads"
  echo ""
  echo "Example:"
  echo "  $0 -a arn:aws:s3::123456789012:accesspoint/mfprmw49gbimn.mrap -r 1 -w 0"
  exit 1
}

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

# Validate that the MRAP value looks like a full ARN, not just an alias
if [[ ! "$S3_MRAP_ARN" =~ ^arn:aws:s3:: ]]; then
  echo "Error: -a must be the full MRAP ARN, not the alias."
  echo "       Got: $S3_MRAP_ARN"
  echo "       Expected format: arn:aws:s3::<account-id>:accesspoint/<alias>"
  exit 1
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