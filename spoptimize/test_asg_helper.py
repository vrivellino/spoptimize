import copy
import json
import os
import unittest

from botocore.exceptions import ClientError
from mock import Mock

import asg_helper
import stepfn_strings as strs
from logging_helper import logging, setup_stream_handler

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())

here = os.path.dirname(os.path.realpath(__file__))
mocks_dir = os.path.join(here, 'resources', 'mock_data', 'autoscaling')
mock_attrs = {}
for file in os.listdir(mocks_dir):
    if file.endswith('.json'):
        with open(os.path.join(mocks_dir, file)) as j:
            mock_attrs['{}.return_value'.format(file.split('.')[0])] = json.loads(j.read())


class TestDescribeAsg(unittest.TestCase):

    def setUp(self):
        self.asg_name = mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['AutoScalingGroupName']
        self.mock_attrs = copy.deepcopy(mock_attrs)

    def test_valid_asg(self):
        logger.debug('TestDescribeAsg.test_valid_asg')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        mock_response = mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]
        expected_dict = {k: mock_response[k] for k in mock_response if k in asg_helper.asg_copy_keys}
        asg_dict = asg_helper.describe_asg(self.asg_name)
        self.assertDictEqual(asg_dict, expected_dict)

    def test_unknown_asg(self):
        logger.debug('TestDescribeAsg.test_unknown_asg')
        self.mock_attrs['describe_auto_scaling_groups.return_value'] = {'AutoScalingGroups': []}
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        asg_dict = asg_helper.describe_asg(self.asg_name)
        self.assertDictEqual(asg_dict, {})


class TestGetLaunchConfig(unittest.TestCase):

    def setUp(self):
        self.asg_name = mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['AutoScalingGroupName']
        self.lc_name = mock_attrs['describe_launch_configurations.return_value']['LaunchConfigurations'][0]['LaunchConfigurationName']
        self.mock_attrs = copy.deepcopy(mock_attrs)

    def test_valid_lc(self):
        logger.debug('TestGetLaunchConfig.test_valid_lc')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        expected_dict = mock_attrs['describe_launch_configurations.return_value']['LaunchConfigurations'][0]
        lc_dict = asg_helper.get_launch_config(self.asg_name)
        self.assertDictEqual(lc_dict, expected_dict)

    def test_unknown_lc(self):
        logger.debug('TestGetLaunchConfig.test_unknown_lc')
        self.mock_attrs['describe_launch_configurations.return_value'] = {'LaunchConfigurations': []}
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        lc_dict = asg_helper.get_launch_config(self.asg_name)
        self.assertDictEqual(lc_dict, {})

    def test_unknown_asg(self):
        logger.debug('TestGetLaunchConfig.test_unknown_asg')
        self.mock_attrs['describe_auto_scaling_groups.return_value'] = {'AutoScalingGroups': []}
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        lc_dict = asg_helper.get_launch_config(self.asg_name)
        self.assertDictEqual(lc_dict, {})


class TestGetInstanceStatus(unittest.TestCase):

    def setUp(self):
        self.instance_id = mock_attrs['describe_auto_scaling_instances.return_value']['AutoScalingInstances'][0]['InstanceId']
        self.mock_attrs = copy.deepcopy(mock_attrs)
        self.mock_resp = self.mock_attrs['describe_auto_scaling_instances.return_value']['AutoScalingInstances'][0]

    def test_healthy_inservice(self):
        logger.debug('TestGetInstanceStatus.test_healthy_inservice')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.get_instance_status(self.instance_id)
        self.assertEqual(res, strs.asg_instance_healthy)

    def test_healthy_pending(self):
        logger.debug('TestGetInstanceStatus.test_healthy_pending')
        self.mock_resp['LifecycleState'] = 'Pending'
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.get_instance_status(self.instance_id)
        self.assertEqual(res, strs.asg_instance_pending)

    def test_unhealthy_inservice(self):
        logger.debug('TestGetInstanceStatus.test_unhealthy_inservice')
        self.mock_resp['HealthStatus'] = 'UNHEALTHY'
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.get_instance_status(self.instance_id)
        self.assertEqual(res, strs.asg_instance_pending)

    def test_unhealthy_terminating(self):
        logger.debug('TestGetInstanceStatus.test_unhealthy_terminating')
        self.mock_resp['HealthStatus'] = 'UNHEALTHY'
        self.mock_resp['LifecycleState'] = 'Terminating'
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.get_instance_status(self.instance_id)
        self.assertEqual(res, strs.asg_instance_terminated)

    def test_healthy_entering_standby(self):
        logger.debug('TestGetInstanceStatus.test_healthy_entering_standby')
        self.mock_resp['LifecycleState'] = 'EnteringStandby'
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.get_instance_status(self.instance_id)
        self.assertEqual(res, strs.asg_instance_protected)

    def test_healthy_standby(self):
        logger.debug('TestGetInstanceStatus.test_healthy_standby')
        self.mock_resp['LifecycleState'] = 'Standby'
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.get_instance_status(self.instance_id)
        self.assertEqual(res, strs.asg_instance_protected)

    def test_healthy_detaching(self):
        logger.debug('TestGetInstanceStatus.test_healthy_detaching')
        self.mock_resp['LifecycleState'] = 'Detaching'
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.get_instance_status(self.instance_id)
        self.assertEqual(res, strs.asg_instance_terminated)

    def test_protected_from_scalein(self):
        logger.debug('TestGetInstanceStatus.test_protected_from_scalein')
        self.mock_resp['ProtectedFromScaleIn'] = True
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.get_instance_status(self.instance_id)
        self.assertEqual(res, strs.asg_instance_protected)

    def test_unknown_instance(self):
        logger.debug('TestGetInstanceStatus.test_unknown_instance')
        self.mock_attrs['describe_auto_scaling_instances.return_value'] = {'AutoScalingInstances': []}
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.get_instance_status(self.instance_id)
        self.assertEqual(res, strs.asg_instance_terminated)


class TestTerminateInstance(unittest.TestCase):

    def setUp(self):
        self.mock_attrs = copy.deepcopy(mock_attrs)

    def test_term_instance(self):
        logger.debug('TestTerminateInstance.test_term_instance')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        asg_helper.terminate_instance('i-abcd123', True)
        asg_helper.autoscaling.terminate_instance_in_auto_scaling_group.assert_called()

    def test_term_instance_not_found(self):
        logger.debug('TestTerminateInstance.test_term_instance_not_found')
        self.mock_attrs['terminate_instance_in_auto_scaling_group.side_effect'] = ClientError({
            'Error': {
                'Code': 'ValidationError',
                'Message': 'Instance Id not found - No managed instance found for instance ID i-abcd123',
                'Type': 'Sender'
            }
        }, 'TerminateInstanceInAutoScalingGroup')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        asg_helper.terminate_instance('i-abcd123', True)
        asg_helper.autoscaling.terminate_instance_in_auto_scaling_group.assert_called()

    def test_term_instance_raise_clienterror(self):
        logger.debug('TestTerminateInstance.test_term_instance_raise_clienterror')
        self.mock_attrs['terminate_instance_in_auto_scaling_group.side_effect'] = ClientError({
            'Error': {
                'Code': 'UnknownError',
                'Message': 'Some other error',
                'Type': 'Unknown'
            }
        }, 'TerminateInstanceInAutoScalingGroup')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        with self.assertRaises(ClientError):
            asg_helper.terminate_instance('i-abcd123', True)

    def test_term_instance_raise_exception(self):
        logger.debug('TestTerminateInstance.test_term_instance_raise_exception')
        self.mock_attrs['terminate_instance_in_auto_scaling_group.side_effect'] = Exception('Testing')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        with self.assertRaises(Exception):
            asg_helper.terminate_instance('i-abcd123', True)


class TestAttachInstance(unittest.TestCase):

    def setUp(self):
        self.mock_attrs = copy.deepcopy(mock_attrs)

    def test_attach_instance(self):
        logger.debug('TestAttachInstance.test_attach_instance')
        expected_res = strs.success
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        self.assertEqual(asg_helper.attach_instance('group-name', 'i-abcd123'), expected_res)
        asg_helper.autoscaling.attach_instances.assert_called()

    def test_attach_instance_incorrect_sizing(self):
        logger.debug('TestAttachInstance.test_attach_instance_incorrect_sizing')
        expected_res = strs.asg_not_sized_correctly
        self.mock_attrs['attach_instances.side_effect'] = ClientError({
            'Error': {
                'Code': 'ValidationError',
                'Message': 'AutoScalingGroup group-name has min-size=1, max-size=1, and desired-size=1. To attach 1 instance, please '
                           'update the AutoScalingGroup sizes appropriately.',
                'Type': 'Sender'
            }
        }, 'AttachInstances')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        self.assertEqual(asg_helper.attach_instance('group-name', 'i-abcd123'), expected_res)

    def test_attach_instance_group_not_found(self):
        logger.debug('TestAttachInstance.test_attach_instance_group_not_found')
        expected_res = strs.asg_instance_missing
        self.mock_attrs['attach_instances.side_effect'] = ClientError({
            'Error': {
                'Code': 'ValidationError',
                'Message': "Instance i-abcd123 [shutting-down] is not in correct state. Instance(s) must be in 'running' state.",
                'Type': 'Sender'
            }
        }, 'AttachInstances')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        self.assertEqual(asg_helper.attach_instance('group-name', 'i-abcd123'), expected_res)

    def test_attach_instance_invalid_state(self):
        logger.debug('TestAttachInstance.test_attach_instance_invalid_state')
        expected_res = strs.asg_disappeared
        self.mock_attrs['attach_instances.side_effect'] = ClientError({
            'Error': {
                'Code': 'ValidationError',
                'Message': 'AutoScalingGroup name not found - AutoScalingGroup: group-name not found',
                'Type': 'Sender'
            }
        }, 'AttachInstances')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        self.assertEqual(asg_helper.attach_instance('group-name', 'i-abcd123'), expected_res)

    def test_attach_instance_invalid_id(self):
        logger.debug('TestAttachInstance.test_attach_instance_invalid_id')
        self.mock_attrs['attach_instances.side_effect'] = ClientError({
            'Error': {
                'Code': 'ValidationError',
                'Message': 'Invalid Instance ID(s): [i-abcd123XXX] specified',
                'Type': 'Sender'
            }
        }, 'AttachInstances')
        expected_res = strs.asg_instance_invalid
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        self.assertEqual(asg_helper.attach_instance('group-name', 'i-abcd123XXX'), expected_res)

    def test_other_clienterror_raises(self):
        logger.debug('TestAttachInstance.test_other_clienterror_raises')
        self.mock_attrs['attach_instances.side_effect'] = ClientError({
            'Error': {
                'Code': 'UnknownError',
                'Message': 'Some other error',
                'Type': 'Unknown'
            }
        }, 'AttachInstances')

        asg_helper.autoscaling = Mock(**self.mock_attrs)
        with self.assertRaises(ClientError):
            asg_helper.attach_instance('group-name', 'i-abcd123XXX')

    def test_other_exception_raises(self):
        logger.debug('TestAttachInstance.test_other_exception_raises')
        self.mock_attrs['attach_instances.side_effect'] = Exception('test')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        with self.assertRaises(Exception):
            asg_helper.attach_instance('group-name', 'i-abcd123XXX')


class TestNotEnoughProtectedInstances(unittest.TestCase):

    def setUp(self):
        self.asg_name = mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['AutoScalingGroupName']
        self.min_protected = 1
        self.mock_attrs = copy.deepcopy(mock_attrs)

    def test_instance_needs_protection(self):
        logger.debug('TestNotEnoughProtectedInstances.test_instance_needs_protection')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.not_enough_protected_instances(self.asg_name, self.min_protected)
        self.assertTrue(res)

    def test_unknown_asg(self):
        logger.debug('TestNotEnoughProtectedInstances.test_unknown_asg')
        self.mock_attrs['describe_auto_scaling_groups.return_value'] = {'AutoScalingGroups': []}
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.not_enough_protected_instances(self.asg_name, self.min_protected)
        self.assertFalse(res)

    def test_no_instances(self):
        logger.debug('TestNotEnoughProtectedInstances.test_no_instances')
        self.mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['Instances'] = []
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.not_enough_protected_instances(self.asg_name, self.min_protected)
        self.assertFalse(res)

    def test_protected_instances(self):
        logger.debug('TestNotEnoughProtectedInstances.test_no_instances')
        self.mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['Instances'][0]['ProtectedFromScaleIn'] = True
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.not_enough_protected_instances(self.asg_name, self.min_protected)
        self.assertFalse(res)

    def test_protected_instance_is_terminating(self):
        logger.debug('TestNotEnoughProtectedInstances.test_no_instances')
        self.mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['Instances'][0]['ProtectedFromScaleIn'] = True
        self.mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['Instances'][0]['LifecycleState'] = 'Terminating'
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.not_enough_protected_instances(self.asg_name, self.min_protected)
        self.assertTrue(res)

    def test_protected_instance_is_detaching(self):
        logger.debug('TestNotEnoughProtectedInstances.test_no_instances')
        self.mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['Instances'][0]['ProtectedFromScaleIn'] = True
        self.mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['Instances'][0]['LifecycleState'] = 'Detaching'
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.not_enough_protected_instances(self.asg_name, self.min_protected)
        self.assertTrue(res)

    def test_min_protected_is_zero(self):
        logger.debug('TestNotEnoughProtectedInstances.test_no_instances')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        res = asg_helper.not_enough_protected_instances(self.asg_name, 0)
        self.assertFalse(res)


class TestProtectInstance(unittest.TestCase):

    def setUp(self):
        self.asg_name = mock_attrs['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]['AutoScalingGroupName']
        self.instance_id = 'i-abcd123'
        self.mock_attrs = copy.deepcopy(mock_attrs)

    def test_set_instance_protection_is_called(self):
        logger.debug('ProtectInstance.test_set_instance_protection_')
        asg_helper.autoscaling = Mock(**self.mock_attrs)
        asg_helper.protect_instance(self.asg_name, self.instance_id)
        asg_helper.autoscaling.set_instance_protection.is_called_once_with(
            InstanceIds=[self.instance_id], AutoScalingGroupName=self.asg_name, ProtectedFromScaleIn=True)


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
