#!/usr/bin/env bash

basedir=$(dirname "$0")/..

s3_bucket=spoptimize-artifacts
version_str=$(git describe --tags)
s3_prefix=public/$version_str
s3_latest_prefix=public/latest

s3_url="s3://$s3_bucket/$s3_prefix"
s3_latest_url="s3://$s3_bucket/$s3_latest_prefix"

echo 'Testing S3 access ...'
s3_probe_path='.spoptimize-deploy-probe'
s3_probe_path="$s3_prefix/.spoptimize-deploy-probe"
set -e
aws s3 cp - "s3://$s3_bucket/$s3_probe_path" < /dev/null
echo 'Packaging ...'
zip -r "$basedir/target/lambda-pkg.zip" LICENSE handler.py spoptimize/ -x spoptimize/test_* spoptimize/*.pyc
aws cloudformation package \
    --template-file "$basedir/sam.yml" \
    --output-template-file "$basedir/target/sam_output.yml" \
    --s3-bucket "$s3_bucket" \
    --s3-prefix "$s3_prefix/sam"
echo

sed "s/{{VERSION_TOKEN}}/$version_str/" "$basedir/principal.yml" > target/spoptimize.yml

echo "Copying CloudFormation templates to $s3_url/"
aws s3 cp "$basedir/iam-global.yml" "$s3_url/iam-global.yml"
aws s3 cp "$basedir/target/sam_output.yml" "$s3_url/sam_output.yml"
aws s3 cp "$basedir/target/spoptimize.yml" "$s3_latest_url/spoptimize.yml"
