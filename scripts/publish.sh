#!/usr/bin/env bash

basedir=$(dirname "$0")/..

s3_bucket=spoptimize-artifacts
version_str=$(git describe --tags)
s3_prefix=public/$version_str
s3_latest_prefix=public/latest

s3_path="$s3_bucket/$s3_prefix"
s3_latest_path="$s3_bucket/$s3_latest_prefix"
iam_template_url="https://s3.amazonaws.com/$s3_path/iam-global.yml"

echo 'Testing S3 access ...'
s3_probe_path='.spoptimize-deploy-probe'
s3_probe_path="$s3_prefix/.spoptimize-deploy-probe"
set -e
aws s3 cp - "s3://$s3_bucket/$s3_probe_path" < /dev/null
echo 'Packaging ...'
zip -r "$basedir/target/lambda-pkg.zip" LICENSE handler.py spoptimize/ -x spoptimize/test_* spoptimize/*.pyc
echo -n > $basedir/sam-all.yml
OLDIFS=$IFS
IFS=''
while read line; do
    if [[ $line =~ URL_TOKEN ]]; then
        echo "    Default: '$iam_template_url'" >> $basedir/sam-all.yml
    else
        echo "$line" >> $basedir/sam-all.yml
    fi
done < $basedir/sam.yml
IFS=$OLDIFS

aws cloudformation package \
    --template-file "$basedir/sam-all.yml" \
    --output-template-file "$basedir/target/spoptimize.yml" \
    --s3-bucket "$s3_bucket" \
    --s3-prefix "$s3_prefix/sam"
echo

echo 'Validating CloudFormation templates'
aws cloudformation validate-template --template-body "file://$basedir/iam-global.yml" > /dev/null || exit $?
aws cloudformation validate-template --template-body "file://$basedir/target/spoptimize.yml" > /dev/null || exit $?
echo

echo "Copying CloudFormation templates to s3://$s3_path/"
aws s3 cp "$basedir/iam-global.yml" "s3://$s3_path/iam-global.yml"
aws s3 cp "$basedir/target/spoptimize.yml" "s3://$s3_path/spoptimize.yml"
aws s3 cp "$basedir/target/spoptimize.yml" "s3://$s3_latest_path/spoptimize.yml"
