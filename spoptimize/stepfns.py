import uuid
from random import random

import asg_helper
import ec2_helper
import spot_helper


def init_machine_state(sns_message, mock=False):
    '''
    sns_message: Dict of Launch Notification embedded in SNS message
    Returns initial machine state for Spoptimize step functions

    Raises exception if an improper message is passed
    '''
    if sns_message.get('Event') != 'autoscaling:EC2_INSTANCE_LAUNCH':
        raise Exception('Unknown SNS message')
    instance_id = sns_message.get('EC2InstanceId')
    group_name = sns_message.get('AutoScalingGroupName')
    subnet_details = sns_message.get('Details')
    # use Activity ID for unique step function execution identifier
    if mock:
        activity_id = '{0}-{1}'.format(instance_id, str(uuid.uuid4()))
    else:
        activity_id = '{0}-{1}'.format(instance_id, sns_message.get('ActivityId'))
    if not (instance_id and group_name and activity_id
            and 'Subnet ID' in subnet_details
            and 'Availability Zone' in subnet_details):
        raise Exception('Unable to extract EC2InstanceId, AutoScalingGroupName, '
                        'subnet Details and/or ActivityId from SNS message')
    msg = None
    asg = asg_helper.describe_asg(group_name, mock=mock)
    if asg:
        sleep_interval_tags = [x['Value'] for x in asg['Tags'] if x['Key'] == 'spoptimize:wait_interval']
        if sleep_interval_tags:
            sleep_interval = sleep_interval_tags[0]
        else:
            sleep_interval = int(asg['HealthCheckGracePeriod'] * (2 + asg['MaxSize'] + random()))
        if asg['MinSize'] == asg['MaxSize']:
            asg = {}
            msg = 'AutoScaling Group has fixed size'
    else:
        msg = 'AutoScaling Group does not exist'
    return ({
        'activity_id': activity_id,
        'ondemand_instance_id': instance_id,
        'launch_subnet_id': subnet_details['Subnet ID'],
        'launch_az': subnet_details['Availability Zone'],
        'autoscaling_group': asg,
        'spoptimize_wait_interval_s': sleep_interval,
        'spot_failure_sleep_s': 10 if mock else 3600
    }, msg)


def asg_instance_state(asg_dict, instance_id, mock=False):
    '''
    Evaluates ondemand instance_id's health according to autoscaling group
    '''
    if not asg_helper.describe_asg(asg_dict['AutoScalingGroupName'], mock):
        return 'AutoScaling Group Disappeared'
    return asg_helper.get_instance_status(instance_id, mock=mock)


def request_spot_instance(asg_dict, az, subnet_id, mock=False):
    '''
    Fetches LaunchConfig of ASG and requests a Spot instance
    '''
    launch_config = asg_helper.get_launch_config(asg_dict['AutoScalingGroupName'], mock=mock)
    return spot_helper.request_spot_instance(launch_config, az, subnet_id, mock=mock)


def check_asg_and_tag_spot(asg_dict, spot_instance_id, ondemand_instance_id, mock=False):
    '''
    Attaches spot_instance_id to AutoScaling Group
    '''
    asg = asg_helper.describe_asg(asg_dict['AutoScalingGroupName'], mock)
    if not asg:
        ec2_helper.term_instance(spot_instance_id)
        return 'AutoScaling Group Disappeared'
    resource_tags = [{'Key': x['Key'], 'Value': x['Value']} for x in asg['Tags']
                     if x.get('PropagateAtLaunch', False) and x.get('Key', '').split(':')[0] != 'aws']
    if not ec2_helper.tag_instance(spot_instance_id, resource_tags):
        return 'Spot Instance Disappeared'
    if asg_helper.get_instance_status(ondemand_instance_id, mock=mock) != 'Health':
        return 'OD Instance Disappeared Or Protected'
    if asg['DesiredCapacity'] == asg['MaxSize']:
        return 'No Capacity Available'
    return 'Capacity Available'


def attach_spot_instance(asg_dict, spot_instance_id, ondemand_instance_id=None, mock=False):
    if ondemand_instance_id:
        asg_helper.terminate_instance(ondemand_instance_id, decrement_cap=True)
    # TODO
    return asg_helper.attach_instance(asg_dict['AutoScalingGroupName'], spot_instance_id, mock=mock)


def terminate_asg_instance(instance_id, mock=False):
    return asg_helper.terminate_instance(instance_id, decrement_cap=True)


def terminate_ec2_instance(instance_id, mock=False):
    if instance_id:
        return ec2_helper.term_instance(instance_id)
