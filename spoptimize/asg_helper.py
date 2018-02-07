import boto3
import json
import logging
import os
import re

from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)

# this adds vendored directory to the Python import path
here = os.path.dirname(os.path.realpath(__file__))
mocks_dir = os.path.join(here, 'resources', 'mock_data')

autoscaling = boto3.client('autoscaling')


def describe_asg(asg_name, mock=False):
    if mock:
        resp = json.loads(os.path.join(mocks_dir, 'asg-describe_groups.json'))
        resp['AutoScalingGroups'] = [x for x in resp['AutoScalingGroups'] if x['AutoScalingGroupName'] == asg_name]
    else:
        resp = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
    if len(resp['AutoScalingGroups']):
        return resp['AutoScalingGroups'][0]
    return {}


def get_launch_config(asg_name, mock=False):
    asg = describe_asg(asg_name, mock)
    if not asg:
        return {}
    lc_name = asg.get('LaunchConfigurationName')
    if mock:
        resp = json.loads(os.path.join(mocks_dir, 'asg-describe_launch_config.json'))
        resp['LaunchConfigurations'] = [x for x in resp['LaunchConfigurations'] if x['LaunchConfigurations'] == lc_name]
    else:
        resp = autoscaling.describe_launch_configurations(LaunchConfigurationNames=[lc_name])
    if len(resp['LaunchConfigurations']):
        return resp['LaunchConfigurations'][0]
    return {}


def get_instance_status(instance_id, mock=False):
    if mock:
        resp = json.loads(os.path.join(mocks_dir, 'asg-describe_auto_scaling_instances', '{}.json'.format(instance_id)))
    else:
        resp = autoscaling.describe_auto_scaling_instances(InstanceIds=[instance_id])
    # instance is terminated or detatched if empty
    if not len(resp['AutoScalingInstances']):
        return 'Terminated'
    instance_detail = resp['AutoScalingInstances'][0]
    if re.match(r'^terminat', instance_detail.get('LifecycleState', 'unknown').lower()):
        # instance is being terminated
        return 'Terminated'
    if re.match(r'^detach', instance_detail.get('LifecycleState', 'unknown').lower()):
        # instance is being detached
        return 'Terminated'
    if instance_detail.get('ProtectedFromScaleIn', 'false').lower() == 'true':
        # instance is protected from scale-in, so let's not replace
        return 'Protected'
    if instance_detail.get('LifecycleState') == 'InService' \
            and instance_detail.get('HealthStatus') == 'HEALTHY':
        # Healthy instance!
        return 'Healthy'
    # else return Pending ...
    return 'Pending'


def terminate_instance(instance_id, decrement_cap, mock=False):
    if mock:
        return
    try:
        autoscaling.terminate_instance_in_auto_scaling_group(
            InstanceId=instance_id, ShouldDecrementDesiredCapacity=decrement_cap)
    except ClientError as c:
        if re.march(r'not found', c.response['Error']['Message']):
            pass
        raise


def attach_instance(asg_name, instance_id, mock=False):
    if mock:
        return
    try:
        autoscaling.attach_instances(InstanceIds=[instance_id], AutoScalingGroupName=asg_name)
    except ClientError as c:
        if re.match(r'please update the AutoScalingGroup sizes appropriately', c.response['Error']['Message']):
            return 'AutoScaling group not sized correctly'
        if re.match(r'AutoScalingGroup name not found', c.response['Error']['Message']):
            return 'Auto-Scaling Group Disappeared'
        if re.match(r'Instance .* is not in correct state', c.response['Error']['Message']):
            return 'Instance missing'
        if re.match(r'Invalid Instance ID', c.response['Error']['Message']):
            return 'Invalid instance'
        raise
    return 'Success'
