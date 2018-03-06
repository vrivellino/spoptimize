import copy
import json
import os
import unittest
from botocore.exceptions import ClientError
from mock import Mock

import ec2_helper
from logging_helper import logging, setup_stream_handler

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())

here = os.path.dirname(os.path.realpath(__file__))
mocks_dir = os.path.join(here, 'resources', 'mock_data', 'ec2')
mock_attrs = {}
for file in os.listdir(mocks_dir):
    if file.endswith('.json'):
        with open(os.path.join(mocks_dir, file)) as j:
            mock_attrs['{}.return_value'.format(file.split('.')[0])] = json.loads(j.read())


class TestTerminateInstance(unittest.TestCase):

    def setUp(self):
        ec2_helper.ec2 = Mock()

    def test_terminate_instance(self):
        logger.debug('TestTerminateInstance.terminate_instance')
        ec2_helper.terminate_instance('i-abcd123')
        ec2_helper.ec2.terminate_instances.assert_called()

    def test_terminate_unknown_instance(self):
        logger.debug('TestTerminateInstance.terminate_unknown_instance')
        ec2_helper.ec2 = Mock(**{'terminate_instances.side_effect': ClientError({
            'Error': {
                'Code': 'InvalidInstanceID.NotFound',
                'Message': "The instance ID 'i-abcd123' does not exist"
            }
        }, 'TerminateInstances')})
        # should not raise an exception
        ec2_helper.terminate_instance('i-abcd123')
        self.assertTrue(True)

    def test_other_clienterror_raises(self):
        logger.debug('TestTerminateInstance.test_other_clienterror_raises')
        ec2_helper.ec2 = Mock(**{'terminate_instances.side_effect': ClientError({
            'Error': {
                'Code': 'UnknownError',
                'Message': 'Some other error'
            }
        }, 'TerminateInstances')})
        with self.assertRaises(ClientError):
            ec2_helper.terminate_instance('i-abcd123')

    def test_other_exception_raises(self):
        logger.debug('TestTerminateInstance.test_other_exception_raises')
        ec2_helper.ec2 = Mock(**{'terminate_instances.side_effect': Exception('test')})
        with self.assertRaises(Exception):
            ec2_helper.terminate_instance('i-abcd123')


class TestTagInstance(unittest.TestCase):

    def setUp(self):
        ec2_helper.ec2 = Mock()

    def test_tag_instance(self):
        logger.debug('TestEc2Helper.test_tag_instance')
        res = ec2_helper.tag_instance('i-9999999', 'i-abcd123', [{'Key': 'testkey', 'Value': 'testval'}])
        ec2_helper.ec2.create_tags.assert_called_once_with(
            Resources=['i-9999999'],
            Tags=[{'Key': 'testkey', 'Value': 'testval'}, {'Key': 'spoptimize:orig_instance_id', 'Value': 'i-abcd123'}]
        )
        self.assertTrue(res)

    def test_tag_instance_no_tags(self):
        logger.debug('TestTagInstance.test_tag_instance_no_tags')
        res = ec2_helper.tag_instance('i-9999999', 'i-abcd123', [])
        ec2_helper.ec2.create_tags.assert_called_once_with(
            Resources=['i-9999999'],
            Tags=[{'Key': 'spoptimize:orig_instance_id', 'Value': 'i-abcd123'}]
        )
        self.assertTrue(res)

    def test_tag_unknown_instance(self):
        logger.debug('TestTagInstance.test_tag_unknown_instance')
        ec2_helper.ec2 = Mock(**{'create_tags.side_effect': ClientError({
            'Error': {
                'Code': 'InvalidInstanceID.NotFound',
                'Message': "The instance ID 'i-abcd123' does not exist"
            }
        }, 'CreateTags')})
        res = ec2_helper.tag_instance('i-9999999', 'i-abcd123', [])
        ec2_helper.ec2.create_tags.assert_called()
        self.assertFalse(res)

    def test_other_clienterror_raises(self):
        logger.debug('TestTagInstance.test_other_clienterror_raises')
        ec2_helper.ec2 = Mock(**{'create_tags.side_effect': ClientError({
            'Error': {
                'Code': 'UnknownError',
                'Message': 'Some other error'
            }
        }, 'CreateTags')})
        with self.assertRaises(ClientError):
            ec2_helper.tag_instance('i-9999999', 'i-abcd123', [])

    def test_other_exception_raises(self):
        logger.debug('TestTagInstance.test_other_exception_raises')
        ec2_helper.ec2 = Mock(**{'create_tags.side_effect': Exception('test')})
        with self.assertRaises(Exception):
            ec2_helper.tag_instance('i-9999999', 'i-abcd123', [])


class TestIsInstanceRunning(unittest.TestCase):

    def setUp(self):
        ec2_helper.ec2 = Mock()
        self.mock_attrs = copy.deepcopy(mock_attrs)

    def test_running_instance(self):
        logger.debug('TestIsInstanceRunning.test_running_instancetest_running_instance')
        self.mock_attrs['describe_instances.return_value']['Reservations'][0]['Instances'][0]['State']['Name'] = 'running'
        ec2_helper.ec2 = Mock(**self.mock_attrs)
        res = ec2_helper.is_instance_running('i-abcd123')
        ec2_helper.ec2.describe_instances.assert_called_once_with(InstanceIds=['i-abcd123'])
        self.assertTrue(res)

    def test_not_running_instance(self):
        logger.debug('TestIsInstanceRunning.test_not_running_instance')
        for state in ['pending', 'shutting-down', 'terminated', 'stopping', 'stopped']:
            self.mock_attrs['describe_instances.return_value']['Reservations'][0]['Instances'][0]['State']['Name'] = state
            ec2_helper.ec2 = Mock(**self.mock_attrs)
            res = ec2_helper.is_instance_running('i-abcd123')
            self.assertFalse(res)

    def test_unknown_instance(self):
        logger.debug('TestIsInstanceRunning.test_unknown_instance')
        ec2_helper.ec2 = Mock(**{'describe_instances.side_effect': ClientError({
            'Error': {
                'Code': 'InvalidInstanceID.NotFound',
                'Message': "The instance ID 'i-abcd123' does not exist"
            }
        }, 'DescribeInstances')})
        res = ec2_helper.is_instance_running('i-abcd123')
        self.assertIsNone(res)

    def test_other_clienterror_raises(self):
        logger.debug('TestIsInstanceRunning.test_other_clienterror_raises')
        ec2_helper.ec2 = Mock(**{'describe_instances.side_effect': ClientError({
            'Error': {
                'Code': 'UnknownError',
                'Message': 'Some other error'
            }
        }, 'DescribeInstances')})
        with self.assertRaises(Exception):
            ec2_helper.is_instance_running('i-abcd123')

    def test_other_exception_raises(self):
        logger.debug('TestIsInstanceRunning.test_other_exception_raises')
        ec2_helper.ec2 = Mock(**{'describe_instances.side_effect': Exception('test')})
        with self.assertRaises(Exception):
            ec2_helper.is_instance_running('i-abcd123')


class TestIsSpoptimizeInstance(unittest.TestCase):

    def setUp(self):
        ec2_helper.ec2 = Mock()
        self.mock_attrs = copy.deepcopy(mock_attrs)

    def test_not_spoptimize_instance(self):
        logger.debug('TestIsSpoptimizeInstance.test_not_spoptimize_instance')
        ec2_helper.ec2 = Mock(**self.mock_attrs)
        res = ec2_helper.is_spoptimize_instance('i-abcd123')
        ec2_helper.ec2.describe_instances.assert_called_once_with(InstanceIds=['i-abcd123'])
        self.assertFalse(res)

    def test_spoptimize_instance(self):
        logger.debug('TestIsSpoptimizeInstance.test_spoptimize_instance')
        self.mock_attrs['describe_instances.return_value']['Reservations'][0]['Instances'][0]['State']['Name'] = 'running'
        self.mock_attrs['describe_instances.return_value']['Reservations'][0]['Instances'][0]['Tags'].append(
            {'Key': 'spoptimize:test_tag', 'Value': 'test-value'}
        )
        ec2_helper.ec2 = Mock(**self.mock_attrs)
        res = ec2_helper.is_spoptimize_instance('i-abcd123')
        ec2_helper.ec2.describe_instances.assert_called_once_with(InstanceIds=['i-abcd123'])
        self.assertTrue(res)

    def test_unknown_instance(self):
        logger.debug('TestIsSpoptimizeInstance.test_unknown_instance')
        ec2_helper.ec2 = Mock(**{'describe_instances.side_effect': ClientError({
            'Error': {
                'Code': 'InvalidInstanceID.NotFound',
                'Message': "The instance ID 'i-abcd123' does not exist"
            }
        }, 'DescribeInstances')})
        res = ec2_helper.is_spoptimize_instance('i-abcd123')
        self.assertIsNone(res)

    def test_other_clienterror_raises(self):
        logger.debug('TestIsSpoptimizeInstance.test_other_clienterror_raises')
        ec2_helper.ec2 = Mock(**{'describe_instances.side_effect': ClientError({
            'Error': {
                'Code': 'UnknownError',
                'Message': 'Some other error'
            }
        }, 'DescribeInstances')})
        with self.assertRaises(ClientError):
            ec2_helper.is_spoptimize_instance('i-abcd123')

    def test_other_exception_raises(self):
        logger.debug('TestIsSpoptimizeInstance.test_other_exception_raises')
        ec2_helper.ec2 = Mock(**{'describe_instances.side_effect': Exception('test')})
        with self.assertRaises(Exception):
            ec2_helper.is_spoptimize_instance('i-abcd123')


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
