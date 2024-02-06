#!/bin/sh
#set -xv
BUCKET=$1
# test if an s3 bucket exists and delete all objects and delete markers from it
# if it does not exist, just print a message
bucketExists=`aws s3api list-buckets --query "Buckets[].Name" | grep -w "$BUCKET" | wc -l`

if [ "$bucketExists" -eq 1 ]
then
  objects=$(aws s3api list-object-versions --bucket "$BUCKET" --no-paginate --output=json --query='{Objects: Versions[].{Key:Key,VersionId:VersionId}}')
  count=$(awk '/"Objects": null/ {print}' <<< "$objects" | wc -l)
  while [ "$count" -ne 1 ];
  do
    echo 'Deleting Object Versions...'
    aws s3api delete-objects --bucket "$BUCKET" --delete "$objects" --no-cli-pager
    objects=$(aws s3api list-object-versions --bucket "$BUCKET" --no-paginate --output=json --query='{Objects: Versions[].{Key:Key,VersionId:VersionId}}')
    count=$(awk '/"Objects": null/ {print}' <<< "$objects" | wc -l)
  done

  deleteMarkers=$(aws s3api list-object-versions --bucket "$BUCKET" --no-paginate --output=json --query='{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}')
  deleteMarkersCount=$(awk '/"Objects": null/ {print}' <<< "$deleteMarkers" | wc -l)
  while [ "$deleteMarkersCount" -ne 1 ];
  do
    echo 'Deleting DeleteMarkers...'
    aws s3api delete-objects --bucket "$BUCKET" --delete "$deleteMarkers" --no-cli-pager
    deleteMarkers=$(aws s3api list-object-versions --bucket "$BUCKET" --no-paginate --output=json --query='{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}')
    deleteMarkersCount=$(awk '/"Objects": null/ {print}' <<< "$deleteMarkers" | wc -l)
  done
else
  echo "Bucket $BUCKET does not exist..."
fi