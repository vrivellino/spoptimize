import copy
import datetime
import json
import os
import random
import unittest

# from botocore.exceptions import ClientError
from mock import Mock

import stepfns
from logging_helper import logging, setup_stream_handler

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())

here = os.path.dirname(os.path.realpath(__file__))
mocks_dir = os.path.join(here, 'resources', 'mock_data')
mock_attrs = {}
for svc in ['autoscaling', 'ec2']:
    mock_attrs[svc] = {}
    svc_mocks_dir = os.path.join(mocks_dir, svc)
    for file in os.listdir(svc_mocks_dir):
        if file.endswith('.json'):
            with open(os.path.join(svc_mocks_dir, file)) as j:
                mock_attrs[svc]['{}.return_value'.format(file.split('.')[0])] = json.loads(j.read())

with open(os.path.join(mocks_dir, 'asg-launch-notification.json')) as j:
    sns_notification = json.loads(j.read())
launch_notification = json.loads(sns_notification['Message'])
randseed = (datetime.datetime.now() - datetime.datetime.utcfromtimestamp(0)).total_seconds()
state_machine_init = {
    'ondemand_instance_id': launch_notification['EC2InstanceId'],
    'launch_subnet_id': launch_notification['Details']['Subnet ID'],
    'launch_az': launch_notification['Details']['Availability Zone'],
    'autoscaling_group': {},
    'init_sleep_interval': 0,
    'spot_req_sleep_interval': 30,
    'spot_attach_sleep_interval': 0,
    'spot_failure_sleep_interval': 3600
}


class TestInitMachineState(unittest.TestCase):

    def setUp(self):
        # self.maxDiff = None
        self.mock_attrs = copy.deepcopy(mock_attrs)
        self.asg_dict = self.mock_attrs['autoscaling']['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()

    def test_standard_asg(self):
        logger.debug('TestInitMachineState.test_standard_asg')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        random.seed(randseed)
        expected_state = state_machine_init.copy()
        expected_state['autoscaling_group'] = self.asg_dict.copy()
        expected_state['init_sleep_interval'] = int(
            self.asg_dict['HealthCheckGracePeriod'] * (2 + self.asg_dict['MaxSize'] + random.random())
        )

        expected_state['spot_attach_sleep_interval'] = int(self.asg_dict['HealthCheckGracePeriod'] * 2)
        random.seed(randseed)
        (state_machine_dict, msg) = stepfns.init_machine_state(launch_notification)
        self.assertDictEqual(state_machine_dict, expected_state)
        self.assertGreater(state_machine_dict['init_sleep_interval'],
                           self.asg_dict['HealthCheckGracePeriod'] * (2 + self.asg_dict['MaxSize']))
        self.assertIsNone(msg)

    def test_unknown_notification(self):
        logger.debug('TestInitMachineState.test_unknown_notification')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        for bad_notification in [{'hello': 'world'}, 'test', None]:

            (state_machine_dict, msg) = stepfns.init_machine_state(bad_notification)
            self.assertDictEqual(state_machine_dict, {})
            self.assertEqual(msg, 'Invalid SNS message')

    def test_malformed_notification(self):
        logger.debug('TestInitMachineState.test_malformed_notification')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        for required_key in ['EC2InstanceId', 'AutoScalingGroupName', 'Details']:
            bad_notification = copy.deepcopy(launch_notification)
            del(bad_notification[required_key])
            (state_machine_dict, msg) = stepfns.init_machine_state(bad_notification)
            self.assertDictEqual(state_machine_dict, {})
            self.assertTrue(msg)

    def test_fixed_asg(self):
        logger.debug('TestInitMachineState.test_fixed_asg')
        self.asg_dict['MinSize'] = 1
        self.asg_dict['MaxSize'] = 1
        self.asg_dict['DesiredCapacity'] = 1
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        expected_msg = 'AutoScaling Group has fixed size'
        (state_machine_dict, msg) = stepfns.init_machine_state(launch_notification)
        self.assertDictEqual(state_machine_dict, {})
        self.assertEqual(msg, expected_msg)

    def test_unknown_asg(self):
        logger.debug('TestInitMachineState.test_unknown_asg')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': {}
        })
        expected_msg = 'AutoScaling Group does not exist'
        (state_machine_dict, msg) = stepfns.init_machine_state(launch_notification)
        self.assertDictEqual(state_machine_dict, {})
        self.assertEqual(msg, expected_msg)

    def test_asg_with_tag_overrides(self):
        logger.debug('TestInitMachineState.test_asg_with_tag_overrides')
        wait_s = int(random.random() * 10)
        spot_req_wait_s = wait_s + 1
        attach_wait_s = wait_s + 2
        spot_fail_wait_s = wait_s + 3
        self.asg_dict['Tags'].append({'Key': 'spoptimize:init_sleep_interval', 'Value': '{}'.format(wait_s)})
        self.asg_dict['Tags'].append({'Key': 'spoptimize:spot_req_sleep_interval', 'Value': '{}'.format(spot_req_wait_s)})
        self.asg_dict['Tags'].append({'Key': 'spoptimize:spot_attach_sleep_interval', 'Value': '{}'.format(attach_wait_s)})
        self.asg_dict['Tags'].append({'Key': 'spoptimize:spot_failure_sleep_interval', 'Value': '{}'.format(spot_fail_wait_s)})
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        (state_machine_dict, msg) = stepfns.init_machine_state(launch_notification)
        self.assertEqual(state_machine_dict['init_sleep_interval'], wait_s)
        self.assertEqual(state_machine_dict['spot_req_sleep_interval'], spot_req_wait_s)
        self.assertEqual(state_machine_dict['spot_attach_sleep_interval'], attach_wait_s)
        self.assertEqual(state_machine_dict['spot_failure_sleep_interval'], spot_fail_wait_s)
        self.assertIsNone(msg)


class TestAsgInstanceStatus(unittest.TestCase):

    def setUp(self):
        self.asg_dict = copy.deepcopy(mock_attrs['autoscaling']['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0])
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()

    def test_valid_asg(self):
        logger.debug('TestAsgInstanceStatus.test_valid_asg')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Healthy'
        })
        res = stepfns.asg_instance_state(self.asg_dict, 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.asg_helper.get_instance_status.assert_called()
        self.assertEqual(res, 'Healthy')

    def test_unknown_asg(self):
        logger.debug('TestAsgInstanceStatus.test_unknown_asg')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': {},
            'get_instance_status.return_value': 'Terminated'
        })
        res = stepfns.asg_instance_state(self.asg_dict, 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.asg_helper.get_instance_status.assert_not_called()
        self.assertEqual(res, 'AutoScaling Group Disappeared')


class TestRequestSpotInstance(unittest.TestCase):

    def setUp(self):
        self.asg_dict = copy.deepcopy(mock_attrs['autoscaling']['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0])
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()

    def test_request_spot(self):
        logger.debug('TestRequestSpotInstance.test_request_spot')
        stepfns.spot_helper = Mock(**{
            'request_spot_instance.return_value': {'dummy': 'response'}
        })
        res = stepfns.request_spot_instance(self.asg_dict,
                                            launch_notification['Details']['Availability Zone'],
                                            launch_notification['Details']['Subnet ID'],
                                            'test-activity')
        stepfns.asg_helper.get_launch_config.assert_called()
        stepfns.spot_helper.request_spot_instance.assert_called()
        self.assertDictEqual(res, {'dummy': 'response'})


class TestGetSpotRequestStatus(unittest.TestCase):

    def setUp(self):
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()

    def test_get_spot_request_status(self):
        logger.debug('TestGetSpotRequestStatus.test_get_spot_request_status')
        stepfns.spot_helper = Mock(**{'get_spot_request_status.return_value': 'Pending'})
        res = stepfns.get_spot_request_status('sir-test')
        stepfns.spot_helper.get_spot_request_status.assert_called_with('sir-test')
        stepfns.ec2_helper.is_instance_running.assert_not_called()
        self.assertEqual(res, 'Pending')

    def test_get_spot_request_status_running_instance(self):
        logger.debug('TestGetSpotRequestStatus.test_get_spot_request_status')
        stepfns.spot_helper = Mock(**{'get_spot_request_status.return_value': 'i-abcd123'})
        stepfns.ec2_helper = Mock(**{'is_instance_running.return_value': True})
        res = stepfns.get_spot_request_status('sir-test')
        stepfns.spot_helper.get_spot_request_status.assert_called_with('sir-test')
        stepfns.ec2_helper.is_instance_running.assert_called_once_with('i-abcd123')
        self.assertEqual(res, 'i-abcd123')

    def test_get_spot_request_status_notrunning_instance(self):
        logger.debug('TestGetSpotRequestStatus.test_get_spot_request_status')
        stepfns.spot_helper = Mock(**{'get_spot_request_status.return_value': 'i-abcd123'})
        stepfns.ec2_helper = Mock(**{'is_instance_running.return_value': False})
        res = stepfns.get_spot_request_status('sir-test')
        stepfns.spot_helper.get_spot_request_status.assert_called_with('sir-test')
        stepfns.ec2_helper.is_instance_running.assert_called_once_with('i-abcd123')
        self.assertEqual(res, 'Pending')

    def test_get_spot_request_status_unknown_instance(self):
        logger.debug('TestGetSpotRequestStatus.test_get_spot_request_status')
        stepfns.spot_helper = Mock(**{'get_spot_request_status.return_value': 'i-abcd123'})
        stepfns.ec2_helper = Mock(**{'is_instance_running.return_value': None})
        res = stepfns.get_spot_request_status('sir-test')
        stepfns.spot_helper.get_spot_request_status.assert_called_with('sir-test')
        stepfns.ec2_helper.is_instance_running.assert_called_once_with('i-abcd123')
        self.assertEqual(res, 'Pending')


class TestAttachSpotInstance(unittest.TestCase):

    def setUp(self):
        self.asg_dict = copy.deepcopy(mock_attrs['autoscaling']['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0])
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()

    def test_no_capacity(self):
        logger.debug('TestAttachSpotInstance.test_no_capacity')
        expected_res = 'Success'
        self.asg_dict['DesiredCapacity'] = self.asg_dict['MaxSize']
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Healthy',
            'attach_instance.return_value': 'Success'
        })
        stepfns.ec2_helper = Mock(**{
            'tag_instance.return_value': True
        })
        res = stepfns.attach_spot_instance(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.terminate_instance.assert_not_called()
        stepfns.ec2_helper.tag_instance.assert_called()
        stepfns.asg_helper.get_instance_status.assert_called()
        stepfns.asg_helper.attach_instance.assert_called_once_with(
            self.asg_dict['AutoScalingGroupName'], 'i-9999999')
        stepfns.asg_helper.terminate_instance.assert_called_once_with('i-abcd123', decrement_cap=True)
        self.assertEqual(res, expected_res)

    def test_capacity_available(self):
        logger.debug('TestAttachSpotInstance.test_capacity_available')
        expected_res = 'Success'
        expected_tags = [{'Key': x['Key'], 'Value': x['Value']} for x in self.asg_dict['Tags']
                         if x.get('PropagateAtLaunch', False) and x.get('Key', '').split(':')[0] != 'aws']
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Healthy',
            'attach_instance.return_value': 'Success'
        })
        stepfns.ec2_helper = Mock(**{
            'tag_instance.return_value': True
        })
        res = stepfns.attach_spot_instance(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.terminate_instance.assert_not_called()
        stepfns.ec2_helper.tag_instance.assert_called_once_with('i-9999999', 'i-abcd123', expected_tags)
        stepfns.asg_helper.get_instance_status.assert_called_once_with('i-abcd123')
        stepfns.asg_helper.attach_instance.assert_called_once_with(
            self.asg_dict['AutoScalingGroupName'], 'i-9999999')
        stepfns.asg_helper.terminate_instance.assert_called_once_with('i-abcd123', decrement_cap=True)
        self.assertEqual(res, expected_res)

    def test_no_asg(self):
        logger.debug('TestAttachSpotInstance.test_no_asg')
        expected_res = 'AutoScaling Group Disappeared'
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': {}
        })
        res = stepfns.attach_spot_instance(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.tag_instance.assert_not_called()
        stepfns.asg_helper.get_instance_status.assert_not_called()
        stepfns.asg_helper.attach_instance.assert_not_called()
        stepfns.asg_helper.terminate_instance.assert_not_called()
        self.assertEqual(res, expected_res)

    def test_spot_disappeared(self):
        logger.debug('TestAttachSpotInstance.test_spot_disappeared')
        expected_res = 'Spot Instance Disappeared'
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Healthy'
        })
        stepfns.ec2_helper = Mock(**{
            'tag_instance.return_value': False
        })
        res = stepfns.attach_spot_instance(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.tag_instance.assert_called()
        stepfns.asg_helper.get_instance_status.assert_not_called()
        stepfns.asg_helper.attach_instance.assert_not_called()
        stepfns.asg_helper.terminate_instance.assert_not_called()
        self.assertEqual(res, expected_res)

    def test_od_disappeared_or_protected(self):
        logger.debug('TestAttachSpotInstance.test_od_disappeared_or_protected')
        expected_res = 'OD Instance Disappeared Or Protected'
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Protected'
        })
        stepfns.ec2_helper = Mock(**{
            'tag_instance.return_value': True
        })
        res = stepfns.attach_spot_instance(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.tag_instance.assert_called()
        stepfns.asg_helper.get_instance_status.assert_called()
        stepfns.asg_helper.terminate_instance.assert_not_called()
        self.assertEqual(res, expected_res)


class TestTerminateEc2Instance(unittest.TestCase):

    def setUp(self):
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()

    def test_terminate(self):
        logger.debug('TestTerminateEc2Instance.test_terminate')
        stepfns.ec2_helper = Mock(**{
            'terminate_instance.return_value': {'dummy': 'response'}
        })
        res = stepfns.terminate_ec2_instance('i-9999999')
        stepfns.ec2_helper.terminate_instance.assert_called_once_with('i-9999999')
        self.assertDictEqual(res, {'dummy': 'response'})

    def test_no_terminate(self):
        logger.debug('TestTerminateEc2Instance.test_no_terminate')
        stepfns.ec2_helper = Mock(**{
            'terminate_instance.return_value': {'dummy': 'response'}
        })
        stepfns.terminate_ec2_instance(None)
        stepfns.ec2_helper.terminate_instance.assert_not_called()


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
