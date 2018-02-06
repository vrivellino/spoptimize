import boto3
import json
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


def gen_launch_specification(launch_config, avail_zone, subnet_id):
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
            'Enabled': launch_config['InstanceMonitoring'].get('Enabled', 'false')
        }


def request_spot_instance(client_token, launch_config, avail_zone, subnet_id, mock=False):
    launch_spec = gen_launch_specification(launch_config, avail_zone, subnet_id)
    if mock:
        resp = json.loads(os.path.join(mocks_dir, 'ec2-request_spot_instances.json'))
        resp['SpotInstanceRequests'][0]['LaunchSpecification'] = launch_spec.copy()
    else:
        resp = ec2.request_spot_instances(InstanceCount=1, LaunchSpecification=launch_spec,
                                          Type='one-time', ClientToken=client_token)
    return resp['SpotInstanceRequests'][0]


def get_spot_request_status(spot_request_id, mock=False):
    if mock:
        resp = json.loads(os.path.join(mocks_dir, 'ec2-describe_spot_instance_request.json'))
        resp['SpotInstanceRequests'] = [x for x in resp['SpotInstanceRequests']
                                        if x['SpotInstanceRequestId'] == spot_request_id]
    else:
        try:
            resp = ec2.describe_spot_instance_requests(SpotInstanceRequestIds=[spot_request_id])
        except ClientError as c:
            if c.response['Error']['Code'] == 'InvalidSpotInstanceRequestID.NotFound':
                return 'Failure'
            raise
    spot_request = resp['SpotInstanceRequests'][0]
    if spot_request.get('State', '') == 'active' and spot_request.get('InstanceId'):
        return spot_request['InstanceId']
    if spot_request.get('State', 'unknown') in ['closed', 'cancelled', 'failed']:
        return 'Failure'
    return 'Pending'
