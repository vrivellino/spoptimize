#!/usr/bin/env bash

set -ex

basedir=$(dirname "$0")/..

for f in iam-global sam ; do
    aws cloudformation validate-template --template-body file://$basedir/$f.yml
done
