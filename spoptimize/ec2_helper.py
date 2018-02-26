import boto3
import copy
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
    '''
    Terminates instance_id via the EC2 API
    No return value
    '''
    logger.info('Terminating EC2 Instance {}'.format(instance_id))
    try:
        ec2.terminate_instances(InstanceIds=[instance_id])
    except ClientError as c:
        if c.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
            logger.info('{} not found'.format(instance_id))
        else:
            raise


def tag_instance(instance_id, orig_instance_id, resource_tags=[]):
    '''
    Tags instance_id using tags of orig_instance_id and resource_tags
    Returns True if successful, False if not
    '''
    my_tags = copy.copy(resource_tags)
    my_tags.append({'Key': 'spoptimize:orig_instance_id', 'Value': orig_instance_id or 'UNKNWON'})
    logger.info('Tagging EC2 instance {0} with {1}'.format(instance_id, resource_tags))
    try:
        ec2.create_tags(Resources=[instance_id], Tags=my_tags)
    except ClientError as c:
        if c.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
            logger.info('{} not found'.format(instance_id))
            return False
        else:
            raise
    return True


def is_instance_running(instance_id):
    '''
    Checks the state of instance_id
    Returns True if the instance is running; False if not
    '''
    logger.debug('Fetching EC2 instance state of {}'.format(instance_id))
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
    except ClientError as c:
        if c.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
            logger.warning('{} not found'.format(instance_id))
            return None
        else:
            raise
    # pending | running | shutting-down | terminated | stopping | stopped
    instance_state = resp['Reservations'][0]['Instances'][0]['State']['Name']
    logger.info('EC2 Instance state of {0}: {1}'.format(instance_id, instance_state))
    return resp['Reservations'][0]['Instances'][0]['State']['Name'] == 'running'


def is_spoptimize_instance(instance_id):
    '''
    Uses instance_id's tags to see if it was launched by spoptimize
    Returns True/False
    '''
    logger.debug('Determining if {} was launched by Spoptimize'.format(instance_id))
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
    except ClientError as c:
        if c.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
            logger.warning('{} not found'.format(instance_id))
            return None
        else:
            raise
    spoptimize_tags = [x for x in resp['Reservations'][0]['Instances'][0].get('Tags', [])
                       if x['Key'].split(':')[0] == 'spoptimize']
    if spoptimize_tags:
        logger.debug('{0} has spoptimize tags: {1}'.format(instance_id, spoptimize_tags))
        return True
    return False
