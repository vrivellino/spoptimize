#!/usr/bin/env bash

basedir=$(dirname "$0")/..
stack_basename=${STACK_BASENAME:-spoptimize}
s3_bucket=${S3_BUCKET:-spoptimize-artifacts-$(aws sts get-caller-identity --query Account --output=text)}

if [[ -z "$1" ]]; then
    do_iam=True
    do_state_machine=True
    do_lambda=True
else
    do_iam=''
    do_state_machine=''
    do_lambda=''
fi
do_mock=''

for opt in "$@"; do
    case $opt in
        iam)
            do_iam=True
            ;;
        state-machine)
            do_state_machine=True
            ;;
        lambda)
            do_lambda=True
            ;;
        mock)
            do_mock=True
            ;;
        all)
            do_iam=True
            do_state_machine=True
            do_lambda=True
            ;;
        *)
            echo "Usage: $(basename "$0") [iam|state-machine|lambda|all]" >&2
            exit 1
    esac

done

if [[ -n $do_iam ]]; then
    # TODO primary/global region?
    aws cloudformation deploy \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --template-file "$basedir/iam-global.yml" \
        --stack-name "$stack_basename-iam-global" || exit $?
fi

if [[ -n $do_state_machine ]]; then
    aws cloudformation deploy \
        --parameter-overrides \
            StackBasename=$stack_basename \
            Mode=active \
        --template-file "$basedir/state-machine.yml" \
        --stack-name "$stack_basename-state-machine" || exit $?
fi

if [[ -n $do_mock ]]; then
    aws cloudformation deploy \
        --parameter-overrides \
            StackBasename=$stack_basename \
            Mode=mock \
        --template-file "$basedir/state-machine.yml" \
        --stack-name "$stack_basename-state-machine-mock" || exit $?
    # TODO
    exit
    aws cloudformation package \
        --template-file file "$basedir/sam.yml" \
        --output-template-file sam_output.yml \
        --s3-bucket "$s3_bucket"
    aws cloudformation deploy \
        --parameter-overrides \
            StackBasename=$stack_basename \
            Mode=mock \
        --template-file "$basedir/sam_output.yml" \
        --stack-name "$stack_basename-lambda-mock" || exit $?
fi

exit

if [[ -n $do_lambda ]]; then
    aws cloudformation package \
        --template-file file "$basedir/sam.yml" \
        --output-template-file sam_output.yml \
        --s3-bucket "$s3_bucket"
    aws cloudformation deploy \
        --template-file "$basedir/sam_output.yml" \
        --stack-name "$stack_basename-lambda" || exit $?
fi
