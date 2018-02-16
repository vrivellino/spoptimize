#!/usr/bin/env bash

if [[ -z $CODEBUILD_BUILD_ID ]]; then
    echo 'Fatal: expecting CODEBUILD_BUILD_ID in env' >&2
fi

# snagged from https://github.com/thii/aws-codebuild-extras/blob/master/install
export GIT_BRANCH=$(git symbolic-ref HEAD --short 2>/dev/null)
if [[ -z $GIT_BRANCH ]]; then
    GIT_BRANCH=$(git branch -a --contains HEAD | sed -n 2p | awk '{ printf $1 }')
    export GIT_BRANCH=${GIT_BRANCH#remotes/origin/}
fi

# only run coveralls on master
if [[ $GIT_BRANCH == master ]]; then
  coveralls
fi
