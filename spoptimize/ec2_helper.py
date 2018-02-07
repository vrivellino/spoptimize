import boto3
import os

from logging_helper import logging

from botocore.exceptions import ClientError

logger = logging.getLogger()
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)

# this adds vendored directory to the Python import path
here = os.path.dirname(os.path.realpath(__file__))
mocks_dir = os.path.join(here, 'resources', 'mock_data')

ec2 = boto3.client('ec2')


def terminate_instance(instance_id):
    logger.info('Terminating EC2 Instance {}'.format(instance_id))
    try:
        ec2.terminate_instances(InstanceIds=[instance_id])
    except ClientError as c:
        if c.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
            pass
        raise


def tag_instance(instance_id, resource_tags):
    logger.info('Tagging EC2 instance {0} with {1}'.format(instance_id, resource_tags))
    if not resource_tags:
        return
    ec2.create_tags(Resources=[instance_id], Tags=resource_tags)
