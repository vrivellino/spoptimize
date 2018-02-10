import boto3
import datetime
import json
import logging
import os

from botocore.exceptions import ClientError

import util

logger = logging.getLogger()
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)

# this adds vendored directory to the Python import path
here = os.path.dirname(os.path.realpath(__file__))
mocks_dir = os.path.join(here, 'resources', 'mock_data')

ec2 = boto3.client('ec2')


def gen_launch_specification(launch_config, avail_zone, subnet_id):
    logger.debug('Converting asg launch config to ec2 launch spec')
    # logger.debug('Launch Config: {}'.format(json.dumps(launch_config, indent=2, default=util.json_dumps_converter)))
    spot_launch_specification = {
        'SubnetId': subnet_id,
        'Placement': {
            'AvailabilityZone': avail_zone,
            'Tenancy': launch_config.get('PlacementTenancy', 'default')
        }
    }
    # common keys
    for k in ['AssociatePublicIpAddress', 'BlockDeviceMappings', 'EbsOptimized', 'ImageId',
              'InstanceType', 'KernelId', 'KeyName', 'RamdiskId', 'UserData']:
        if launch_config.get(k):
            spot_launch_specification[k] = launch_config[k]
    # some translation needed ...
    if launch_config.get('IamInstanceProfile'):
        spot_launch_specification['IamInstanceProfile'] = {
            'Arn': launch_config['IamInstanceProfile']
        }
    if launch_config.get('SecurityGroups'):
        # Assume VPC security group ids
        spot_launch_specification['SecurityGroupIds'] = launch_config['SecurityGroups']
    if launch_config.get('InstanceMonitoring'):
        spot_launch_specification['Monitoring'] = {
            'Enabled': launch_config['InstanceMonitoring'].get('Enabled', False)
        }
    # logger.debug('Launch Specification: {}'.format(json.dumps(spot_launch_specification, indent=2, default=util.json_dumps_converter)))
    return spot_launch_specification


def request_spot_instance(launch_config, avail_zone, subnet_id, client_token):
    logger.info('Requesting spot instance in {0}/{1}'.format(avail_zone, subnet_id))
    launch_spec = gen_launch_specification(launch_config, avail_zone, subnet_id)
    resp = ec2.request_spot_instances(InstanceCount=1, LaunchSpecification=launch_spec,
                                      Type='one-time', ClientToken=client_token)
    logger.debug('Spot request response: {}'.format(json.dumps(resp, indent=2, default=util.json_dumps_converter)))
    return resp['SpotInstanceRequests'][0]


def get_spot_request_status(spot_request_id):
    logger.debug('Checking status of spot request {}'.format(spot_request_id))
    try:
        resp = ec2.describe_spot_instance_requests(SpotInstanceRequestIds=[spot_request_id])
    except ClientError as c:
        if c.response['Error']['Code'] == 'InvalidSpotInstanceRequestID.NotFound':
            logger.info('Spot instance request {} does not exist'.format(spot_request_id))
            return 'Failure'
        raise
    # logger.debug('Spot request status response: {}'.format(resp))
    spot_request = resp['SpotInstanceRequests'][0]
    if spot_request.get('State', '') == 'active' and spot_request.get('InstanceId'):
        logger.info('Spot instance request {0} is active: {1}'.format(spot_request_id, spot_request['InstanceId']))
        return spot_request['InstanceId']
    if spot_request.get('State', 'unknown') in ['closed', 'cancelled', 'failed']:
        logger.info('Spot instance request {0} is {1}'.format(spot_request_id, spot_request['State']))
        return 'Failure'
    logger.info('Spot instance request {0} is pending with state {1}'.format(spot_request_id, spot_request['State']))
    return 'Pending'
