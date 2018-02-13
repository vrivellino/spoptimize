import boto3
import logging
import os
import re

from botocore.exceptions import ClientError

logger = logging.getLogger()
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)

# this adds vendored directory to the Python import path
here = os.path.dirname(os.path.realpath(__file__))
mocks_dir = os.path.join(here, 'resources', 'mock_data')

autoscaling = boto3.client('autoscaling')


def describe_asg(asg_name):
    logger.debug('Querying for autoscaling group {}'.format(asg_name))
    resp = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
    if len(resp['AutoScalingGroups']):
        logger.debug('Autoscaling group {} found'.format(asg_name))
        return resp['AutoScalingGroups'][0]
    logger.debug('Autoscaling group {} not found'.format(asg_name))
    return {}


def get_launch_config(asg_name):
    logger.debug('Querying for launch config for autoscaling group {}'.format(asg_name))
    asg = describe_asg(asg_name)
    if not asg:
        return {}
    lc_name = asg.get('LaunchConfigurationName')
    logger.debug('Querying for launchh config {}'.format(lc_name))
    resp = autoscaling.describe_launch_configurations(LaunchConfigurationNames=[lc_name])
    if len(resp['LaunchConfigurations']):
        logger.debug('Launch config {} found'.format(lc_name))
        return resp['LaunchConfigurations'][0]
    logger.debug('Launch config {} not found'.format(lc_name))
    return {}


def get_instance_status(instance_id):
    logger.debug('Fetching autoscaling health status for {}'.format(instance_id))
    resp = autoscaling.describe_auto_scaling_instances(InstanceIds=[instance_id])
    # instance is terminated or detatched if empty
    if not len(resp['AutoScalingInstances']):
        logger.info('{0} terminated or not managed by autoscaling'.format(instance_id))
        return 'Terminated'
    instance_detail = resp['AutoScalingInstances'][0]
    logger.debug('{0} details: {1}'.format(instance_id, instance_detail))
    if re.match(r'^terminat', instance_detail.get('LifecycleState', 'unknown').lower()):
        logger.info('{0} is being terminated by autoscaling'.format(instance_id))
        # instance is being terminated
        return 'Terminated'
    if re.match(r'^detach', instance_detail.get('LifecycleState', 'unknown').lower()):
        logger.info('{0} is being detached by autoscaling'.format(instance_id))
        # instance is being detached
        return 'Terminated'
    if instance_detail.get('ProtectedFromScaleIn', False):
        logger.info('{0} is protected by scale-in by autoscaling'.format(instance_id))
        # instance is protected from scale-in, so let's not replace
        return 'Protected'
    if instance_detail.get('LifecycleState', 'unknown') in ['EnteringStandby', 'Standby']:
        logger.info('{0} is marked as standby in autoscaling'.format(instance_id))
        return 'Protected'
    if instance_detail.get('LifecycleState') == 'InService' \
            and instance_detail.get('HealthStatus') == 'HEALTHY':
        logger.info('{0} is healthy and in-service in autoscaling'.format(instance_id))
        # Healthy instance!
        return 'Healthy'
    # else return Pending ...
    logger.info('{0} is {1}/{2} ... defaulting to Pending'.format(
        instance_id, instance_detail.get('HealthStatus'), instance_detail.get('LifecycleState')))
    return 'Pending'


def terminate_instance(instance_id, decrement_cap):
    logger.info('Terminating autoscaling instance {0}; decrement capacity: {1}'.format(instance_id, decrement_cap))
    try:
        autoscaling.terminate_instance_in_auto_scaling_group(
            InstanceId=instance_id, ShouldDecrementDesiredCapacity=decrement_cap)
    except ClientError as c:
        if re.match(r'.*not found.*', c.response['Error']['Message']):
            logger.info('Autoscaling instance {} not found ... ignoring'.format(instance_id))
        else:
            raise


def attach_instance(asg_name, instance_id):
    logger.info('Attaching {0} to AutoScaling group {1}'.format(instance_id, asg_name))
    try:
        autoscaling.attach_instances(InstanceIds=[instance_id], AutoScalingGroupName=asg_name)
    except ClientError as c:
        if re.match(r'.*please update the AutoScalingGroup sizes appropriately', c.response['Error']['Message']):
            logger.error(c.response['Error']['Message'])
            return 'AutoScaling group not sized correctly'
        if re.match(r'AutoScalingGroup name not found', c.response['Error']['Message']):
            logger.warning(c.response['Error']['Message'])
            return 'AutoScaling Group Disappeared'
        if re.match(r'Instance .* is not in correct state', c.response['Error']['Message']):
            logger.error(c.response['Error']['Message'])
            return 'Instance missing'
        if re.match(r'Invalid Instance ID', c.response['Error']['Message']):
            logger.error(c.response['Error']['Message'])
            return 'Invalid instance'
        raise
    logger.debug('Successfully attached {0} to {1}'.format(instance_id, asg_name))
    return 'Success'
