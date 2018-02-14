# import json
import logging
import re

from datetime import datetime, timedelta
from random import random

import asg_helper
import ddb_lock_helper
import ec2_helper
import spot_helper
# import util

logger = logging.getLogger()


def get_spoptimize_tags(asg_tags):
    # logger.debug('Processing auto-scaling group tags for configuration override: {}'.format(
    #    json.dumps(asg_tags, indent=2, default=util.json_dumps_converter)))
    spoptimize_tags = {
        x['Key'].split(':')[1]: x['Value']
        for x in asg_tags
        if x['Key'].split(':')[0] == 'spoptimize'
    }
    logger.info('Autoscaling group tags for configuration override: {}'.format(spoptimize_tags))
    return spoptimize_tags


def init_machine_state(sns_message):
    '''
    sns_message: Dict of Launch Notification embedded in SNS message
    Returns initial machine state for Spoptimize step functions

    Raises exception if an improper message is passed
    '''
    # logger.debug('Launch notification received {}'.format(json.dumps(sns_message, indent=2, default=util.json_dumps_converter)))
    if type(sns_message) != dict:
        return ({}, 'Invalid SNS message')
    if sns_message.get('Event') != 'autoscaling:EC2_INSTANCE_LAUNCH':
        return ({}, 'Invalid SNS message')
    if not sns_message.get('EC2InstanceId'):
        return ({}, 'Unable to extract EC2InstanceId from SNS message')
    if not sns_message.get('AutoScalingGroupName'):
        return ({}, 'Unable to extract AutoScalingGroupName from SNS message')
    if not sns_message.get('Details'):
        return ({}, 'Unable to extract Details from SNS message')
    instance_id = sns_message.get('EC2InstanceId')
    group_name = sns_message.get('AutoScalingGroupName')
    subnet_details = sns_message.get('Details', {})
    if not ('Subnet ID' in subnet_details and 'Availability Zone' in subnet_details):
        return ({}, 'Unable to extract Subnet Details from SNS message')
    logger.info('Processing launch notification for {0}: {1} {2}/{3}'.format(
        group_name, instance_id, subnet_details['Availability Zone'], subnet_details['Subnet ID']))
    msg = None
    asg = asg_helper.describe_asg(group_name)
    if not asg:
        logger.warning('Autoscaling Group {} does not exist'.format(group_name))
        return ({}, 'AutoScaling Group does not exist')
    spoptimize_tags = get_spoptimize_tags(asg.get('Tags', []))
    init_sleep_interval = spoptimize_tags.get(
        'init_sleep_interval',
        asg['HealthCheckGracePeriod'] * (2 + asg['MaxSize'] + random())
    )
    spot_req_sleep_interval = spoptimize_tags.get('spot_req_sleep_interval', 30)
    spot_attach_sleep_interval = spoptimize_tags.get('spot_attach_sleep_interval', asg['HealthCheckGracePeriod'] * 2)
    spot_failure_sleep_interval = spoptimize_tags.get('spot_failure_sleep_interval', 3600)
    logger.info('Initial wait interval {}s'.format(init_sleep_interval))
    logger.info('Spot request wait interval {}s'.format(spot_req_sleep_interval))
    logger.info('Spot attachment wait interval {}s'.format(spot_attach_sleep_interval))
    logger.info('Spot failure wait interval {}s'.format(spot_failure_sleep_interval))
    if asg['MinSize'] == asg['MaxSize']:
        logger.warning('Autoscaling Group {} has a fixed size'.format(group_name))
        return ({}, 'AutoScaling Group has fixed size')
    return ({
        'iteration_count': 0,
        'ondemand_instance_id': instance_id,
        'launch_subnet_id': subnet_details['Subnet ID'],
        'launch_az': subnet_details['Availability Zone'],
        'autoscaling_group': asg,
        'init_sleep_interval': int(init_sleep_interval),
        'spot_req_sleep_interval': int(spot_req_sleep_interval),
        'spot_attach_sleep_interval': int(spot_attach_sleep_interval),
        'spot_failure_sleep_interval': int(spot_failure_sleep_interval)
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


def request_spot_instance(asg_dict, az, subnet_id, client_token):
    '''
    Fetches LaunchConfig of ASG and requests a Spot instance
    '''
    asg_name = asg_dict.get('AutoScalingGroupName')
    logger.info('Preparing to launch spot instance in {0}/{1} for {2}'.format(az, subnet_id, asg_name))
    launch_config = asg_helper.get_launch_config(asg_name)
    return spot_helper.request_spot_instance(launch_config, az, subnet_id, client_token)


def get_spot_request_status(spot_request_id):
    '''
    Fetches status of spot request
    '''
    spot_request_result = spot_helper.get_spot_request_status(spot_request_id)
    if re.match(r'^i-', spot_request_result):
        if ec2_helper.is_instance_running(spot_request_result):
            return spot_request_result
        else:
            return 'Pending'
    return spot_request_result


def attach_spot_instance(asg_dict, spot_instance_id, ondemand_instance_id):
    '''
    Attaches spot_instance_id to AutoScaling Group
    '''
    asg_name = asg_dict.get('AutoScalingGroupName')
    logger.info('Checking AutoScaling group {0} in preparation to attach {1} and term {2}'.format(
        asg_name, spot_instance_id, ondemand_instance_id))
    asg = asg_helper.describe_asg(asg_name)
    if not asg:
        logger.info('AutoScaling group {0} no longer exists; Terminating {1}'.format(asg_name, spot_instance_id))
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
        logger.info("AutoScaling group {0}'s DesiredCapacity equals MaxSize - terminating {1}, then attaching {2}".format(
            asg_name, ondemand_instance_id, spot_instance_id))
        asg_helper.terminate_instance(ondemand_instance_id, decrement_cap=True)
        return asg_helper.attach_instance(asg_dict['AutoScalingGroupName'], spot_instance_id)
    logger.info('AutoScaling group {0} has available capacity - attaching {1}, then terminating {2}'.format(
        asg_name, spot_instance_id, ondemand_instance_id))
    retval = asg_helper.attach_instance(asg_dict['AutoScalingGroupName'], spot_instance_id)
    asg_helper.terminate_instance(ondemand_instance_id, decrement_cap=True)
    return retval


def terminate_ec2_instance(instance_id):
    if instance_id:
        return ec2_helper.terminate_instance(instance_id)


def acquire_lock(table_name, group_name, my_execution_arn):
    logger.info('Acquiring lock for {}'.format(group_name))
    logger.debug('My execution ARN is {}'.format(my_execution_arn))
    ttl = int((timedelta(days=7) + datetime.now() - datetime.utcfromtimestamp(0)).total_seconds())
    if ddb_lock_helper.put_item(table_name, group_name, my_execution_arn, ttl):
        logger.info('Lock for {} Acquired'.format(group_name))
        return True
    current_owner = ddb_lock_helper.get_item(table_name, group_name)
    if current_owner == my_execution_arn:
        logger.info('Lock for {} Already Acquired'.format(group_name))
        return True
    if ddb_lock_helper.is_execution_running(current_owner):
        logger.info('Lock for {0} belongs to {1}'.format(group_name, current_owner))
        return False
    logger.info('Found stale lock for {0}  belonging to {1}'.format(group_name, current_owner))
    if ddb_lock_helper.put_item(table_name, group_name, my_execution_arn, ttl, current_owner):
        logger.info('Lock for {} Acquired'.format(group_name))
        return True
    logger.warning('Unable to acquire lock for {}'.format(group_name))
    return False


def release_lock(table_name, group_name, my_execution_arn):
    logger.info('Releasing lock for {}'.format(group_name))
    logger.debug('My execution ARN is {}'.format(my_execution_arn))
    ddb_lock_helper.delete_item(table_name, group_name, my_execution_arn)
