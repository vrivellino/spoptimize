#!/usr/bin/env bash

basedir=$(dirname "$0")/..
stack_basename=${STACK_BASENAME:-spoptimize}
aws_account_id=$(aws sts get-caller-identity --query Account --output=text)
s3_bucket=${S3_BUCKET:-spoptimize-artifacts-$aws_account_id}
s3_prefix=${S3_PREFIX:-spoptimize}
sns_topic_name=${ASG_SNS_TOPIC_NAME:-spoptimize-init}
lambda_debug_log=${SPOPTIMIZE_LAMBDA_DEBUG_LOG:-false}

if [[ -z "$1" ]]; then
    do_iam=True
    do_sam=True
else
    do_iam=''
    do_sam=''
fi

for opt in "$@"; do
    case $opt in
        iam)
            do_iam=True
            ;;
        sam)
            do_sam=True
            ;;
        all)
            do_iam=True
            do_sam=True
            ;;
        *)
            echo "Usage: $(basename "$0") [iam|sam|all]" >&2
            exit 1
    esac

done

if [[ -n $do_iam ]]; then
    # TODO primary/global region?
    echo 'Deploying IAM stack ...'
    aws cloudformation deploy \
        --parameter-overrides StackBasename=$stack_basename \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --template-file "$basedir/iam-global.yml" \
        --stack-name "$stack_basename-iam-global"
    rc=$?
    if [[ $rc != 0 ]] && [[ $rc != 255 ]]; then
        exit $rc
    fi
    echo
fi

if [[ -n $do_sam ]]; then
    echo 'Testing S3 access ...'
    s3_probe_path='.spoptimize-deploy-probe'
    s3_probe_path="$s3_prefix/.spoptimize-deploy-probe"
    set -e
    aws s3 cp - "s3://$s3_bucket/$s3_probe_path" < /dev/null || aws s3 mb "s3://$s3_bucket"
    echo 'SNS Topic Arn for Autoscaling Notifications ...'
    aws sns create-topic --name "$sns_topic_name" --output=text --query TopicArn
    echo
    echo 'Packaging ...'
    zip -r "$basedir/target/lambda-pkg.zip" LICENSE handler.py spoptimize/ -x spoptimize/test_* spoptimize/*.pyc
    aws cloudformation package \
        --template-file "$basedir/sam.yml" \
        --output-template-file "$basedir/target/sam_output.yml" \
        --s3-bucket "$s3_bucket" \
        --s3-prefix "$s3_prefix"
    echo
    echo 'Deploying Spoptimize ...'
    aws cloudformation deploy \
        --parameter-overrides StackBasename=$stack_basename DebugLambdas=$lambda_debug_log \
        --template-file "$basedir/target/sam_output.yml" \
        --stack-name "$stack_basename" || exit $?
fi
