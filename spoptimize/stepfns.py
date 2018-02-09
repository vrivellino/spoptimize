# import json
import logging
from random import random

import asg_helper
import ec2_helper
import spot_helper

logger = logging.getLogger()


def init_machine_state(sns_message):
    '''
    sns_message: Dict of Launch Notification embedded in SNS message
    Returns initial machine state for Spoptimize step functions

    Raises exception if an improper message is passed
    '''
    # logger.debug('Launch notification received {}'.format(json.dumps(sns_message, indent=2)))
    if type(sns_message) != dict and sns_message.get('Event') != 'autoscaling:EC2_INSTANCE_LAUNCH':
        raise Exception('Unknown SNS message')
    if not sns_message.get('EC2InstanceId'):
        raise Exception('Unable to extract EC2InstanceId from SNS message')
    if not sns_message.get('ActivityId'):
        raise Exception('Unable to extract ActivityId from SNS message')
    if not sns_message.get('AutoScalingGroupName'):
        raise Exception('Unable to extract AutoScalingGroupName from SNS message')
    if not sns_message.get('Details'):
        raise Exception('Unable to extract Details from SNS message')
    instance_id = sns_message.get('EC2InstanceId')
    group_name = sns_message.get('AutoScalingGroupName')
    subnet_details = sns_message.get('Details', {})
    if not ('Subnet ID' in subnet_details and 'Availability Zone' in subnet_details):
        raise Exception('Unable to extract Subnet Details from SNS message')
    # use Activity ID for unique step function execution identifier
    activity_id = '{0}-{1}'.format(instance_id, sns_message.get('ActivityId'))
    logger.info('Processing launch notification for {0}: {1} {2}/{3}'.format(
        group_name, instance_id, subnet_details['Availability Zone'], subnet_details['Subnet ID']))
    msg = None
    asg = asg_helper.describe_asg(group_name)
    if not asg:
        logger.warning('Autoscaling Group {} does not exist'.format(group_name))
        return ({}, 'AutoScaling Group does not exist')
    sleep_interval_tags = [x['Value'] for x in asg['Tags'] if x['Key'] == 'spoptimize:wait_interval']
    if sleep_interval_tags:
        logger.info('Wait interval {} specified via resource tags'.format(sleep_interval_tags[0]))
        sleep_interval = int(sleep_interval_tags[0])
    else:
        sleep_interval = int(asg['HealthCheckGracePeriod'] * (2 + asg['MaxSize'] + random()))
        logger.info('Using wait interval {}s'.format(sleep_interval))
    if asg['MinSize'] == asg['MaxSize']:
        logger.warning('Autoscaling Group {} has a fixed size'.format(group_name))
        return ({}, 'AutoScaling Group has fixed size')
    return ({
        'activity_id': activity_id,
        'ondemand_instance_id': instance_id,
        'launch_subnet_id': subnet_details['Subnet ID'],
        'launch_az': subnet_details['Availability Zone'],
        'autoscaling_group': asg,
        'spoptimize_wait_interval_s': sleep_interval,
        'spot_request_wait_interval_s': 60,
        'spot_failure_sleep_s': 3600
    }, msg)


def asg_instance_state(asg_dict, instance_id):
    '''
    Evaluates ondemand instance_id's health according to autoscaling group
    '''
    asg_name = asg_dict.get('AutoScalingGroupName')
    logger.debug('Fetching instance status for {0} in {1}'.format(instance_id, asg_name))
    if not asg_helper.describe_asg(asg_name):
        logger.warning('AutoScaling group {} not longer exists'.format(asg_name))
        return 'AutoScaling Group Disappeared'
    return asg_helper.get_instance_status(instance_id)


def request_spot_instance(asg_dict, az, subnet_id, activity_id):
    '''
    Fetches LaunchConfig of ASG and requests a Spot instance
    '''
    asg_name = asg_dict.get('AutoScalingGroupName')
    logger.info('Preparing to launch spot instance in {0}/{1} for {2}'.format(az, subnet_id, asg_name))
    launch_config = asg_helper.get_launch_config(asg_name)
    return spot_helper.request_spot_instance(launch_config, az, subnet_id, activity_id)


def get_spot_request_status(spot_request_id):
    '''
    Fetches status of spot request
    '''
    return spot_helper.get_spot_request_status(spot_request_id)


def check_asg_and_tag_spot(asg_dict, spot_instance_id, ondemand_instance_id):
    '''
    Attaches spot_instance_id to AutoScaling Group
    '''
    asg_name = asg_dict.get('AutoScalingGroupName')
    logger.info('Checking AutoScaling group {0} in preparation to attach {1} and term {2}'.format(
        asg_name, spot_instance_id, ondemand_instance_id))
    asg = asg_helper.describe_asg(asg_name)
    if not asg:
        logger.info('AutoScaling group {0} no longer exists; Terminating {1}'.format(asg_name, spot_instance_id))
        ec2_helper.terminate_instance(spot_instance_id)
        return 'AutoScaling Group Disappeared'
    resource_tags = [{'Key': x['Key'], 'Value': x['Value']} for x in asg['Tags']
                     if x.get('PropagateAtLaunch', False) and x.get('Key', '').split(':')[0] != 'aws']
    if not ec2_helper.tag_instance(spot_instance_id, ondemand_instance_id, resource_tags):
        logger.warning('Spot instance {} does not appear to exist'.format(spot_instance_id))
        return 'Spot Instance Disappeared'
    if asg_helper.get_instance_status(ondemand_instance_id) != 'Healthy':
        logger.info('OnDemand instance {} is protected or unhealthy'.format(ondemand_instance_id))
        return 'OD Instance Disappeared Or Protected'
    if asg['DesiredCapacity'] == asg['MaxSize']:
        logger.info("AutoScaling group {0}'s DesiredCapacity equals MaxSize - no capacity available".format(asg_name))
        return 'No Capacity Available'
    logger.info('AutoScaling group {0} has available capacity'.format(asg_name))
    return 'Capacity Available'


def attach_spot_instance(asg_dict, spot_instance_id, ondemand_instance_id=None):
    if ondemand_instance_id:
        asg_helper.terminate_instance(ondemand_instance_id, decrement_cap=True)
    return asg_helper.attach_instance(asg_dict['AutoScalingGroupName'], spot_instance_id)


def terminate_asg_instance(instance_id):
    return asg_helper.terminate_instance(instance_id, decrement_cap=True)


def terminate_ec2_instance(instance_id):
    if instance_id:
        return ec2_helper.terminate_instance(instance_id)
