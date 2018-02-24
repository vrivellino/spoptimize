#!/usr/bin/env bash
set -e
cd "$(dirname $0)/.."

if [ -z "$VIRTUAL_ENV" ]; then
    # This env var cause issues with older versions of virtualenv, pip, and Python load paths
    # https://github.com/certbot/certbot/issues/1680#issuecomment-175298203
    PYTHON_INSTALL_LAYOUT=""
    if [ ! -d .venv ]; then
        virtualenv -p python2.7 .venv
    fi
    . .venv/bin/activate
fi
echo 'Installing Python pre-reqs'
pip install --upgrade pip
if [ -e requirements-dev.txt ]; then
    pip install --upgrade -r requirements-dev.txt
fi
if [ -e requirements.txt ]; then
    pip install --upgrade -r requirements.txt
    #pip install -t vendored -r requirements.txt
fi

yamllint_cmd='yamllint *.yml demo/*.yml'
echo "Checking yaml files via: $yamllint_cmd"
$yamllint_cmd
echo

echo
python scripts/validate-templates.py
echo

test_cmd='coverage run --source=. -m unittest discover -s spoptimize -v' "$@"
echo "Executing: $test_cmd" "$@"
$test_cmd "$@"
echo
coverage report
