# snagged from https://github.com/thii/aws-codebuild-extras/blob/master/install
export CI=true
export CODEBUILD=true

export GIT_BRANCH=$(git symbolic-ref HEAD --short 2>/dev/null)
if [ -z "$GIT_BRANCH" ]; then
    export GIT_BRANCH=$(git branch -a --contains HEAD | sed -n 2p | awk '{ printf $1 }' | sed 's,^remotes/origin/,,')
fi

export GIT_MESSAGE=$(git log -1 --pretty=%B)
export GIT_AUTHOR=$(git log -1 --pretty=%an)
export GIT_AUTHOR_EMAIL=$(git log -1 --pretty=%ae)
export GIT_COMMIT=$(git log -1 --pretty=%H)
export GIT_TAG=$(git describe --tags --abbrev=0 2>/dev/null)

export GITHUB_PULL_REQUEST=false
if [ "$(echo "$GIT_BRANCH" | cut -f 1 -d -)" = 'pr' ]; then
    export GITHUB_PULL_REQUEST=$(echo "$GIT_BRANCH" | sed 's/^pr-//')
fi
