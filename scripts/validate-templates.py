#!/usr/bin/env python

import boto3
import os

here = os.path.dirname(os.path.realpath(__file__))
template_list = ['iam-global.yml', 'sam.yml']
cfn = boto3.client('cloudformation')


def validate_templates():
    print('Validating Cloudformation templates')
    for tpl in template_list:
        tpl_file = os.path.join(here, '..', tpl)
        print('Cloudformation validate-template {}'.format(tpl_file))
        with open(tpl_file, 'r') as f:
            cfn.validate_template(TemplateBody=f.read())


if __name__ == '__main__':
    validate_templates()
