import copy
import datetime
import json
import os
import unittest

from botocore.exceptions import ClientError
from mock import Mock

import spot_helper
from logging_helper import logging, setup_stream_handler

logger = logging.getLogger()
here = os.path.dirname(os.path.realpath(__file__))
mocks_dir = os.path.join(here, 'resources', 'mock_data', 'ec2')
mock_attrs = {}
for file in os.listdir(mocks_dir):
    if file.endswith('.json'):
        with open(os.path.join(mocks_dir, file)) as j:
            mock_attrs['{}.return_value'.format(file.split('.')[0])] = json.loads(j.read())

sample_launch_config = {
    'LaunchConfigurationName': 'test-launch-config',
    'LaunchConfigurationARN': 'arn:aws:autoscaling:us-east-1:123456789012:launchConfiguration:9c6c99f0-9bfb-4ecd-bc63-e0bfe7938607:launchConfigurationName/test-launch-config',
    'CreatedTime': datetime.datetime(2018, 2, 8, 11, 3, 15, 210898),
    'InstanceType': 't2.micro',
    'ImageId': 'ami-428aa838',
    'BlockDeviceMappings': [],
    'KernelId': '',
    'RamdiskId': '',
    'EbsOptimized': False,
    'InstanceMonitoring': {'Enabled': True},
    'KeyName': 'vince',
    'SecurityGroups': ['sg-cccccccc'],
    'IamInstanceProfile': 'arn:aws:iam::123456789012:instance-profile/base-ec2',
    'ClassicLinkVPCSecurityGroups': [],
    'UserData': 'IyBoZWxsbyB3b3JsZAo'
}
expected_launch_spec = {
    'InstanceType': 't2.micro',
    'ImageId': 'ami-428aa838',
    'Monitoring': {'Enabled': True},
    'KeyName': 'vince',
    'SecurityGroupIds': ['sg-cccccccc'],
    'IamInstanceProfile': {
        'Arn': 'arn:aws:iam::123456789012:instance-profile/base-ec2'
    },
    'UserData': 'IyBoZWxsbyB3b3JsZAo',
    'SubnetId': 'subnet-11111111',
    'Placement': {
        'AvailabilityZone': 'us-east-1d',
        'Tenancy': 'default'
    }
}


class TestGenLaunchSpecification(unittest.TestCase):

    def setUp(self):
        self.maxDiff = 1024
        self.launch_config = copy.deepcopy(sample_launch_config)
        self.subnet_id = 'subnet-11111111'
        self.az = 'us-east-1d'
        self.expected_launch_spec = copy.deepcopy(expected_launch_spec)

    def test_get_launch_specification(self):
        logger.debug('TestSpotHelper.get_launch_specification')
        launch_spec = spot_helper.gen_launch_specification(self.launch_config, self.az, self.subnet_id)
        # logger.debug('Generated launch spec: {}'.format(json.dumps(launch_spec, indent=2)))
        # logger.debug('Expected launch spec: {}'.format(json.dumps(self.expected_launch_spec, indent=2)))
        self.assertDictEqual(launch_spec, self.expected_launch_spec)

    def test_get_launch_specification_xformed_overrides(self):
        logger.debug('TestSpotHelper.test_get_launch_specification_xformed_overrides')
        del(self.launch_config['InstanceMonitoring'])
        del(self.launch_config['IamInstanceProfile'])
        self.launch_config['PlacementTenancy'] = 'dedicated'

        del(self.expected_launch_spec['Monitoring'])
        del(self.expected_launch_spec['IamInstanceProfile'])
        self.expected_launch_spec['Placement']['Tenancy'] = 'dedicated'
        launch_spec = spot_helper.gen_launch_specification(self.launch_config, self.az, self.subnet_id)
        # logger.debug('Generated launch spec: {}'.format(json.dumps(launch_spec, indent=2)))
        # logger.debug('Expected launch spec: {}'.format(json.dumps(self.expected_launch_spec, indent=2)))
        self.assertDictEqual(launch_spec, self.expected_launch_spec)

    def test_get_launch_specification_common_overrides(self):
        logger.debug('TestSpotHelper.test_get_launch_specification_common_overrides')
        del(self.launch_config['KeyName'])
        self.launch_config['EbsOptimized'] = True
        self.launch_config['RamdiskId'] = 'rd-test'
        self.launch_config['KernelId'] = 'kernel-test'
        self.launch_config['BlockDeviceMappings'] = {
            'DeviceName': '/dev/xvda',
            'Ebs': {
                'VolumeSize': '25',
                'VolumeType': 'gp2',
                'DeleteOnTermination': 'true'
            }
        }
        del(self.expected_launch_spec['KeyName'])
        self.expected_launch_spec['EbsOptimized'] = True
        self.expected_launch_spec['RamdiskId'] = 'rd-test'
        self.expected_launch_spec['KernelId'] = 'kernel-test'
        self.expected_launch_spec['BlockDeviceMappings'] = {
            'DeviceName': '/dev/xvda',
            'Ebs': {
                'VolumeSize': '25',
                'VolumeType': 'gp2',
                'DeleteOnTermination': 'true'
            }
        }
        launch_spec = spot_helper.gen_launch_specification(self.launch_config, self.az, self.subnet_id)
        # logger.debug('Generated launch spec: {}'.format(json.dumps(launch_spec, indent=2)))
        # logger.debug('Expected launch spec: {}'.format(json.dumps(self.expected_launch_spec, indent=2)))
        self.assertDictEqual(launch_spec, self.expected_launch_spec)


class TestRequestSpotInstance(unittest.TestCase):

    def setUp(self):
        self.launch_config = copy.deepcopy(sample_launch_config)
        self.expected_launch_spec = copy.deepcopy(expected_launch_spec)
        self.az = 'us-east-1d'
        self.subnet_id = 'subnet-11111111'
        self.client_token = 'testing1234'
        self.mock_attrs = copy.deepcopy(mock_attrs)

    def test_request_spot_instance(self):
        logger.debug('TestRequestSpotInstance.test_request_spot_instance')
        spot_helper.ec2 = Mock(**self.mock_attrs)
        expected_dict = mock_attrs['request_spot_instances.return_value']['SpotInstanceRequests'][0]
        spot_req_dict = spot_helper.request_spot_instance(self.launch_config, self.az, self.subnet_id, self.client_token)
        spot_helper.ec2.request_spot_instances.assert_called_once_with(
            InstanceCount=1,
            LaunchSpecification=self.expected_launch_spec,
            Type='one-time', ClientToken=self.client_token
        )
        self.assertDictEqual(spot_req_dict, expected_dict)


class TestGetSpotRequestStatus(unittest.TestCase):

    def setUp(self):
        self.mock_attrs = copy.deepcopy(mock_attrs)
        self.spot_req_id = mock_attrs['describe_spot_instance_requests.return_value']['SpotInstanceRequests'][0]['SpotInstanceRequestId']
        self.spot_instance_id = mock_attrs['describe_spot_instance_requests.return_value']['SpotInstanceRequests'][0]['InstanceId']

    def test_get_spot_request_status_active(self):
        logger.debug('TestGetSpotRequest_status.test_get_spot_request_status_active')
        expected_res = self.spot_instance_id
        spot_helper.ec2 = Mock(**self.mock_attrs)
        res = spot_helper.get_spot_request_status(self.spot_req_id)
        spot_helper.ec2.describe_spot_instance_requests.assert_called()
        self.assertEqual(res, expected_res)

    def test_get_spot_request_status_not_found(self):
        logger.debug('TestGetSpotRequest_status.test_get_spot_request_status_not_found')
        expected_res = 'Failure'
        self.mock_attrs['describe_spot_instance_requests.side_effect'] = ClientError({
            'Error': {
                'Code': 'InvalidSpotInstanceRequestID.NotFound',
                'Message': "The spot instance request ID 'sir-abcd1234' does not exist"
            }
        }, 'InvalidSpotInstanceRequestID.NotFound')
        spot_helper.ec2 = Mock(**self.mock_attrs)
        res = spot_helper.get_spot_request_status('sir-abcd1234')
        self.assertEqual(res, expected_res)

    def test_get_spot_request_status_failure(self):
        logger.debug('TestGetSpotRequest_status.test_get_spot_request_status_failure')
        expected_res = 'Failure'
        self.mock_attrs['describe_spot_instance_requests.return_value']['SpotInstanceRequests'][0]['Status']['Message'] = 'Dummy message'
        self.mock_attrs['describe_spot_instance_requests.return_value']['SpotInstanceRequests'][0]['Status']['Code'] = 'dummy-code'
        for state in ['closed', 'cancelled', 'failed']:
            self.mock_attrs['describe_spot_instance_requests.return_value']['SpotInstanceRequests'][0]['State'] = state
            spot_helper.ec2 = Mock(**self.mock_attrs)
            res = spot_helper.get_spot_request_status(self.spot_req_id)
            self.assertEqual(res, expected_res)

    def test_get_spot_request_status_pending(self):
        logger.debug('TestGetSpotRequest_status.test_get_spot_request_status_failure')
        expected_res = 'Pending'
        self.mock_attrs['describe_spot_instance_requests.return_value']['SpotInstanceRequests'][0]['Status']['Message'] = 'Your Spot request has been submitted for review, and is pending evaluation.'
        self.mock_attrs['describe_spot_instance_requests.return_value']['SpotInstanceRequests'][0]['Status']['Code'] = 'pending-evaluation'
        self.mock_attrs['describe_spot_instance_requests.return_value']['SpotInstanceRequests'][0]['State'] = 'open'
        spot_helper.ec2 = Mock(**self.mock_attrs)
        res = spot_helper.get_spot_request_status(self.spot_req_id)
        self.assertEqual(res, expected_res)


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
