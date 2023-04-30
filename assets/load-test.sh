#!/bin/sh

AWS_ACCOUNT=$1
S3_MRAP_ALIAS=$2

echo "AWS_ACCOUNT: $AWS_ACCOUNT"
echo "S3_MRAP_ALIAS: $S3_MRAP_ALIAS"

for i in {1..100};
do
  fileName=testfile_$i.csv
  aws s3 cp testfile.csv s3://arn:aws:s3::$AWS_ACCOUNT:accesspoint/$S3_MRAP_ALIAS/input/$fileName
  echo "Uploaded File: $fileName"
  sleep 1
done

