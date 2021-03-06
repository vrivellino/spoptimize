#!/usr/bin/env bash

basedir=$(dirname "$0")
if [[ -f $basedir/.env ]]; then
    set -o allexport
    source "$basedir/.env"
    set +o allexport
fi

stack_basename=${STACK_BASENAME:-spoptimize}
aws_account_id=$(aws sts get-caller-identity --query Account --output=text)
s3_bucket=${S3_BUCKET:-spoptimize-artifacts-$aws_account_id}
s3_prefix=${S3_PREFIX:-spoptimize}
sns_topic_name=${ASG_SNS_TOPIC_NAME:-$stack_basename-init}
sns_alarm_topic_name=$SNS_ALARM_TOPIC_NAME
lambda_debug_log=${SPOPTIMIZE_LAMBDA_DEBUG_LOG:-false}
cfn_iam_role_arn_arg=''
cfn_sam_role_arn_arg=''
cfn_notification_arns_arg=''
cfn_iam_tags_arg=''
cfn_sam_tags_arg=''
if [[ -n $CFN_IAM_SVC_ROLE_ARN ]]; then
    cfn_iam_role_arn_arg="--role-arn $CFN_IAM_SVC_ROLE_ARN"
fi
if [[ -n $CFN_SAM_SVC_ROLE_ARN ]]; then
    cfn_sam_role_arn_arg="--role-arn $CFN_SAM_SVC_ROLE_ARN"
fi
if [[ -n $CFN_NOTIFICATION_ARNS ]]; then
    cfn_notification_arns_arg="--notification-arns $CFN_NOTIFICATION_ARNS"
fi
if [[ -n $CFN_IAM_TAGS ]]; then
    cfn_iam_tags_arg="--tags $CFN_IAM_TAGS"
fi
if [[ -n $CFN_SAM_TAGS ]]; then
    cfn_sam_tags_arg="--tags $CFN_SAM_TAGS"
fi

if [[ -z "$1" ]]; then
    do_iam=True
    do_pkg=True
    do_sam=True
else
    do_iam=''
    do_pkg=''
    do_sam=''
fi

for opt in "$@"; do
    case $opt in
        iam)
            do_iam=True
            ;;
        cfn-pkg)
            do_pkg=True
            ;;
        cfn-deploy)
            do_sam=True
            ;;
        cfn)
            do_pkg=True
            do_sam=True
            ;;
        all)
            do_iam=True
            do_pkg=True
            do_sam=True
            ;;
        *)
            echo "Usage: $(basename "$0") [iam|cfn|cfn-pkg|cfn-deploy|all]" >&2
            exit 1
    esac

done

if [[ -n $do_iam ]]; then
    # TODO primary/global region?
    echo 'Deploying IAM stack ...'
    aws cloudformation deploy $cfn_iam_role_arn_arg $cfn_notification_arns_arg \
        --stack-name "$stack_basename-iam-global" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --parameter-overrides StackBasename=$stack_basename \
        --template-file "$basedir/iam-global.yml" $cfn_iam_tags_arg
    rc=$?
    if [[ $rc != 0 ]] && [[ $rc != 255 ]]; then
        exit $rc
    fi
    echo
fi

if [[ -n $do_pkg ]]; then
    echo 'Testing S3 access ...'
    s3_probe_path='.spoptimize-deploy-probe'
    s3_probe_path="$s3_prefix/.spoptimize-deploy-probe"
    set -e
    [[ -z $S3_BUCKET ]] || aws s3 cp - "s3://$s3_bucket/$s3_probe_path" < /dev/null || aws s3 mb "s3://$s3_bucket"
    echo 'Packaging ...'
    zip -r "$basedir/target/lambda-pkg.zip" LICENSE handler.py spoptimize/ -x spoptimize/test_* spoptimize/*.pyc
    aws cloudformation package \
        --template-file "$basedir/sam.yml" \
        --output-template-file "$basedir/target/sam_output.yml" \
        --s3-bucket "$s3_bucket" \
        --s3-prefix "$s3_prefix"
    echo
fi

if [[ -n $do_sam ]]; then
    echo 'SNS Topic Arn for Autoscaling Notifications ...'
    aws sns create-topic --name "$sns_topic_name" --output=text --query TopicArn
    echo
    echo 'Deploying Spoptimize ...'
    if [[ $sns_topic_name != $stack_basename-init ]]; then
        sns_params="SnsTopicNameOverride=$sns_topic_name"
    fi
    if [[ -n $sns_alarm_topic_name ]]; then
        sns_params="$sns_params AlarmTopicName=$sns_alarm_topic_name"
    fi
    aws cloudformation deploy $cfn_sam_role_arn_arg $cfn_notification_arns_arg \
        --stack-name "$stack_basename" \
        --parameter-overrides StackBasename=$stack_basename DebugLambdas=$lambda_debug_log $sns_params \
        --template-file "$basedir/target/sam_output.yml" $cfn_sam_tags_arg || exit $?
fi
