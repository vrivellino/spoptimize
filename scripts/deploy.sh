#!/usr/bin/env bash

basedir=$(dirname "$0")/..
stack_basename=${STACK_BASENAME:-spoptimize}
s3_bucket=${S3_BUCKET:-spoptimize-artifacts-$(aws sts get-caller-identity --query Account --output=text)}

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
    aws cloudformation deploy \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --template-file "$basedir/iam-global.yml" \
        --stack-name "$stack_basename-iam-global" || exit $?
fi

if [[ -n $do_sam ]]; then
    aws cloudformation package \
        --template-file file "$basedir/sam.yml" \
        --output-template-file sam_output.yml \
        --s3-bucket "$s3_bucket"
    aws cloudformation deploy \
        --template-file "$basedir/sam_output.yml" \
        --stack-name "$stack_basename-lambda" || exit $?
fi
