#!/usr/bin/env python

import os
import json
import re
import subprocess
import sys

from urllib2 import Request, urlopen

here = os.path.dirname(os.path.realpath(__file__))

git_log_command = 'git log --oneline --no-decorate --first-parent master {version}..HEAD'
pr_url = 'https://github.com/vrivellino/spoptimize/pull/{pr}'
pr_api_url = 'https://api.github.com/repos/vrivellino/spoptimize/pulls/{pr}'


def git_log_since_last_release(version_str):
    git_log_output = subprocess.check_output(git_log_command.format(version=version_str).split())
    return git_log_output.strip().split('\n')


def gh_pull_request(pr_num):
    # curl --header 'Accept: application/vnd.github.v3+json' https://api.github.com/repos/vrivellino/spoptimize/pulls/28
    req = Request(pr_api_url.format(pr=pr_num))
    req.add_header('Accept', 'application/vnd.github.v3+json')
    pull_req = json.loads(urlopen(req).read())
    pr_title = pull_req.get('title').strip()
    change_log_entry = '* #[{pr}]({pr_html_url}): {title}\n'.format(
        title=pr_title, pr=pr_num, pr_html_url=pull_req.get('html_url').strip()
    )
    pr_body = pull_req.get('body').replace('\r', '').strip()
    if pr_body:
        change_log_entry += '  ' + pr_body.replace('\n', '\n  ') + '\n'
    return change_log_entry


def produce_iam_diff(cur_version_str):
    return subprocess.check_output(['git', 'diff', '{}...HEAD'.format(cur_version_str.split('-')[0]), 'iam-global.yml'])


def update_changelog(lines, cur_version_str, new_version_str):
    with open(os.path.join(here, '..', 'CHANGELOG.md')) as f:
        with open(os.path.join(here, '..', 'CHANGELOG-new.md'), 'w') as w:
            for (cnt, line) in enumerate(f):
                token = '## {}'.format(cur_version_str)
                if line[:len(token)] == token:
                    w.write('## {}\n'.format(new_version_str))
                    for line_new in lines:
                        w.write(line_new)
                    w.write('\n* New IAM privs:\n```diff\n')
                    w.write(produce_iam_diff(cur_version_str))
                    w.write('```\n\n')
                w.write(line)


def process_git_log(git_log):
    lines = []
    for log_entry in git_log:
        m = re.match('^[a-f0-9]+ Merge pull request #([0-9]+) from ', log_entry)
        if m:
            lines.append(gh_pull_request(m.groups()[0]))
        else:
            lines.append('* {} '.format(log_entry))
    return lines


def main(new_version_str):
    version_str = subprocess.check_output(['git', 'describe', '--tags']).split('-')[0]
    if not re.match(r'^v\d+[.]\d+[.]\d+', version_str):
        print('Warning: "git describe --tags" might have a wonky output: {}'.format(version_str))
    git_log = git_log_since_last_release(version_str)
    changes = process_git_log(git_log)
    update_changelog(changes, version_str, new_version_str)


if __name__ == '__main__':
    # match v1.2.3 or v1.2.3-beta1
    if len(sys.argv) != 2 or not re.match(r'^v\d+[.]\d+[.]\d+(-\w+)?$', sys.argv[1]):
        print('Usage: {script} NEW_VERSION'.format(script=os.path.basename(sys.argv[0])))
        sys.exit(2)
    main(sys.argv[1])
