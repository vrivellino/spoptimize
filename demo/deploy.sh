#!/usr/bin/env bash

set -e

stack_name=spoptimize-demo-asg
tpl_file=$(dirname $0)/demo.yml

if [[ $1 =~ delete$ ]]; then
    aws cloudformation delete-stack --stack-name $stack_name
    exit $?
elif [[ -z $1 ]]; then
    echo "Usage: $(basename $0) Ec2Key=<ec2-keyname>"
    exit 1
fi

set -x

aws cloudformation validate-template --template-body "file://$tpl_file"

default_vpc_id=$(aws ec2 describe-vpcs --output=text --query 'Vpcs[?IsDefault==`true`].VpcId')
subnet_ids=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$default_vpc_id" \
    --query=Subnets[].SubnetId --output=text | tr '[:space:]' '\n' | sort | tr '\n' ',' | sed 's/,$//')
my_ip=$(curl -s https://ucanhazip.co)/32

aws cloudformation deploy \
    --stack-name $stack_name \
    --template-file "$tpl_file" \
    --parameter-overrides VPC=$default_vpc_id SubnetIds=$subnet_ids WhitelistCidr=$my_ip "$@"
