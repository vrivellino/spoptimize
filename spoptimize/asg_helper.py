import boto3
import logging
import re

from botocore.exceptions import ClientError

import stepfn_strings as strs

logger = logging.getLogger()
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)

autoscaling = boto3.client('autoscaling')


def describe_asg(asg_name):
    '''
    Calls autoscaling.describe_auto_scaling_groups()
    Returns a dict containing autoscaling group description; Empty dict for group not found
    '''
    logger.debug('Querying for autoscaling group {}'.format(asg_name))
    resp = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
    if len(resp['AutoScalingGroups']):
        logger.debug('Autoscaling group {} found'.format(asg_name))
        return resp['AutoScalingGroups'][0]
    logger.debug('Autoscaling group {} not found'.format(asg_name))
    return {}


def get_launch_config(asg_name):
    '''
    Fetches the launch configuration of the specified autoscaling group
    Returns a dict containing the launch configuration; Empty dict for group or luanch-config not found
    '''
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
    '''
    Fetches the autoscaling health status of instance_id
    Returns a string
    '''
    logger.debug('Fetching autoscaling health status for {}'.format(instance_id))
    resp = autoscaling.describe_auto_scaling_instances(InstanceIds=[instance_id])
    # instance is terminated or detatched if empty
    if not len(resp['AutoScalingInstances']):
        logger.info('{0} terminated or not managed by autoscaling'.format(instance_id))
        return strs.asg_instance_terminated
    instance_detail = resp['AutoScalingInstances'][0]
    logger.debug('{0} details: {1}'.format(instance_id, instance_detail))
    if re.match(r'^terminat', instance_detail.get('LifecycleState', 'unknown').lower()):
        logger.info('{0} is being terminated by autoscaling'.format(instance_id))
        # instance is being terminated
        return strs.asg_instance_terminated
    if re.match(r'^detach', instance_detail.get('LifecycleState', 'unknown').lower()):
        logger.info('{0} is being detached by autoscaling'.format(instance_id))
        # instance is being detached
        return strs.asg_instance_terminated
    if instance_detail.get('ProtectedFromScaleIn', False):
        logger.info('{0} is protected by scale-in by autoscaling'.format(instance_id))
        # instance is protected from scale-in, so let's not replace
        return strs.asg_instance_protected
    if instance_detail.get('LifecycleState', 'unknown') in ['EnteringStandby', 'Standby']:
        logger.info('{0} is marked as standby in autoscaling'.format(instance_id))
        return strs.asg_instance_protected
    if instance_detail.get('LifecycleState') == 'InService' \
            and instance_detail.get('HealthStatus') == 'HEALTHY':
        logger.info('{0} is healthy and in-service in autoscaling'.format(instance_id))
        # Healthy instance!
        return strs.asg_instance_healthy
    # else return Pending ...
    logger.info('{0} is {1}/{2} ... defaulting to Pending'.format(
        instance_id, instance_detail.get('HealthStatus'), instance_detail.get('LifecycleState')))
    return strs.asg_instance_pending


def terminate_instance(instance_id, decrement_cap):
    '''
    Terminates instance_id via the autoscaling api
    No return value
    '''
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
    '''
    Attaches instance_id to the specified autoscaling group
    Returns a string describing the status of the attachment
    '''
    logger.info('Attaching {0} to AutoScaling group {1}'.format(instance_id, asg_name))
    try:
        autoscaling.attach_instances(InstanceIds=[instance_id], AutoScalingGroupName=asg_name)
    except ClientError as c:
        if re.match(r'.*please update the AutoScalingGroup sizes appropriately', c.response['Error']['Message']):
            logger.error(c.response['Error']['Message'])
            return strs.asg_not_sized_correctly
        if re.match(r'AutoScalingGroup name not found', c.response['Error']['Message']):
            logger.warning(c.response['Error']['Message'])
            return strs.asg_disappeared
        if re.match(r'Instance .* is not in correct state', c.response['Error']['Message']):
            logger.error(c.response['Error']['Message'])
            return strs.asg_instance_missing
        if re.match(r'Invalid Instance ID', c.response['Error']['Message']):
            logger.error(c.response['Error']['Message'])
            return strs.asg_instance_invalid
        raise
    logger.debug('Successfully attached {0} to {1}'.format(instance_id, asg_name))
    return strs.success
