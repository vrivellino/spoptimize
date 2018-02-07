import boto3
# import json
import logging
import os
# import re

from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)

# this adds vendored directory to the Python import path
here = os.path.dirname(os.path.realpath(__file__))
mocks_dir = os.path.join(here, 'resources', 'mock_data')

ec2 = boto3.client('ec2')


def term_instance(instance_id, mock=False):
    if mock:
        return
    try:
        ec2.terminate_instances(InstanceIds=[instance_id])
    except ClientError as c:
        if c.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
            pass
        raise


def tag_instance(instance_id, resource_tags, mock=False):
    if not resource_tags:
        return
    if mock:
        return
    ec2.create_tags(Resources=[instance_id], Tags=resource_tags)
