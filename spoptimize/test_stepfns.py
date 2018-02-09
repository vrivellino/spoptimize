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
    'activity_id': '{0}-{1}'.format(launch_notification['EC2InstanceId'], launch_notification['ActivityId']),
    'ondemand_instance_id': launch_notification['EC2InstanceId'],
    'launch_subnet_id': launch_notification['Details']['Subnet ID'],
    'launch_az': launch_notification['Details']['Availability Zone'],
    'autoscaling_group': {},
    'spoptimize_wait_interval_s': 0,
    'spot_failure_sleep_s': 3600
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
        expected_state['spoptimize_wait_interval_s'] = int(
            self.asg_dict['HealthCheckGracePeriod'] * (2 + self.asg_dict['MaxSize'] + random.random())
        )
        random.seed(randseed)
        (state_machine_dict, msg) = stepfns.init_machine_state(launch_notification)
        self.assertDictEqual(state_machine_dict, expected_state)
        self.assertGreater(state_machine_dict['spoptimize_wait_interval_s'],
                           self.asg_dict['HealthCheckGracePeriod'] * (2 + self.asg_dict['MaxSize']))
        self.assertIsNone(msg)

    def test_unknown_notification(self):
        logger.debug('TestInitMachineState.test_malformed_notification')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        for bad_notification in [{'hello': 'world'}, 'test', None]:
            with self.assertRaises(Exception):
                (state_machine_dict, msg) = stepfns.init_machine_state(bad_notification)

    def test_malformed_notification(self):
        logger.debug('TestInitMachineState.test_malformed_notification')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        for required_key in ['EC2InstanceId', 'AutoScalingGroupName', 'Details', 'ActivityId']:
            bad_notification = copy.deepcopy(launch_notification)
            del(bad_notification[required_key])
            with self.assertRaises(Exception):
                (state_machine_dict, msg) = stepfns.init_machine_state(bad_notification)

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

    def test_asg_with_wait_interval(self):
        logger.debug('TestInitMachineState.test_fixed_asg')
        wait_s = int(random.random() * 10)
        self.asg_dict['Tags'].append({'Key': 'spoptimize:wait_interval', 'Value': '{}'.format(wait_s)})
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        (state_machine_dict, msg) = stepfns.init_machine_state(launch_notification)
        self.assertEqual(state_machine_dict['spoptimize_wait_interval_s'], wait_s)
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
                                            launch_notification['Details']['Subnet ID'])
        stepfns.asg_helper.get_launch_config.assert_called()
        stepfns.spot_helper.request_spot_instance.assert_called()
        self.assertDictEqual(res, {'dummy': 'response'})


class TestCheckAsgAndTagSpot(unittest.TestCase):

    def setUp(self):
        self.asg_dict = copy.deepcopy(mock_attrs['autoscaling']['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0])
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()

    def test_capacity_available(self):
        logger.debug('TestCheckAsgAndTagSpot.test_capacity_available')
        expected_res = 'Capacity Available'
        expected_tags = [{'Key': x['Key'], 'Value': x['Value']} for x in self.asg_dict['Tags']
                         if x.get('PropagateAtLaunch', False) and x.get('Key', '').split(':')[0] != 'aws']
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Healthy'
        })
        stepfns.ec2_helper = Mock(**{
            'tag_instance.return_value': True
        })
        res = stepfns.check_asg_and_tag_spot(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.terminate_instance.assert_not_called()
        stepfns.ec2_helper.tag_instance.assert_called_once_with('i-9999999', 'i-abcd123', expected_tags)
        stepfns.asg_helper.get_instance_status.assert_called_once_with('i-abcd123')
        self.assertEqual(res, expected_res)

    def test_no_asg(self):
        logger.debug('TestCheckAsgAndTagSpot.test_no_asg')
        expected_res = 'AutoScaling Group Disappeared'
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': {}
        })
        res = stepfns.check_asg_and_tag_spot(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.tag_instance.assert_not_called()
        stepfns.ec2_helper.terminate_instance.assert_called_once_with('i-9999999')
        stepfns.asg_helper.get_instance_status.assert_not_called()
        self.assertEqual(res, expected_res)

    def test_spot_disappeared(self):
        logger.debug('TestCheckAsgAndTagSpot.test_spot_disappeared')
        expected_res = 'Spot Instance Disappeared'
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Healthy'
        })
        stepfns.ec2_helper = Mock(**{
            'tag_instance.return_value': False
        })
        res = stepfns.check_asg_and_tag_spot(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.terminate_instance.assert_not_called()
        stepfns.ec2_helper.tag_instance.assert_called()
        stepfns.asg_helper.get_instance_status.assert_not_called()
        self.assertEqual(res, expected_res)

    def test_od_disappeared_or_protected(self):
        logger.debug('TestCheckAsgAndTagSpot.test_od_disappeared_or_protected')
        expected_res = 'OD Instance Disappeared Or Protected'
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Protected'
        })
        stepfns.ec2_helper = Mock(**{
            'tag_instance.return_value': True
        })
        res = stepfns.check_asg_and_tag_spot(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.terminate_instance.assert_not_called()
        stepfns.ec2_helper.tag_instance.assert_called()
        stepfns.asg_helper.get_instance_status.assert_called()
        self.assertEqual(res, expected_res)

    def test_no_capacity(self):
        logger.debug('TestCheckAsgAndTagSpot.test_no_capacity')
        expected_res = 'No Capacity Available'
        self.asg_dict['DesiredCapacity'] = self.asg_dict['MaxSize']
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Healthy'
        })
        stepfns.ec2_helper = Mock(**{
            'tag_instance.return_value': True
        })
        res = stepfns.check_asg_and_tag_spot(self.asg_dict, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.ec2_helper.terminate_instance.assert_not_called()
        stepfns.ec2_helper.tag_instance.assert_called()
        stepfns.asg_helper.get_instance_status.assert_called()
        self.assertEqual(res, expected_res)


class TestAttachSpotInstance(unittest.TestCase):

    def setUp(self):
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()

    def test_term_ondemand(self):
        logger.debug('TestAttachSpotInstance.test_term_ondemand')
        stepfns.asg_helper = Mock(**{
            'attach_instance.return_value': {'dummy': 'response'}
        })
        res = stepfns.attach_spot_instance({'AutoScalingGroupName': 'group-name'}, 'i-9999999', 'i-abcd123')
        stepfns.asg_helper.terminate_instance.assert_called_once_with('i-abcd123', decrement_cap=True)
        stepfns.asg_helper.attach_instance.assert_called_once_with('group-name', 'i-9999999')
        self.assertDictEqual(res, {'dummy': 'response'})

    def test_no_ondemand(self):
        logger.debug('TestAttachSpotInstance.test_term_ondemand')
        stepfns.asg_helper = Mock(**{
            'attach_instance.return_value': {'dummy': 'response'}
        })
        res = stepfns.attach_spot_instance({'AutoScalingGroupName': 'group-name'}, 'i-9999999')
        stepfns.asg_helper.terminate_instance.assert_not_called()
        stepfns.asg_helper.attach_instance.assert_called_once_with('group-name', 'i-9999999')
        self.assertDictEqual(res, {'dummy': 'response'})


class TestTerminateAsgInstance(unittest.TestCase):

    def setUp(self):
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()

    def test_term_ondemand(self):
        logger.debug('TestTerminateAsgInstance.test_term_ondemand')
        stepfns.asg_helper = Mock(**{
            'terminate_instance.return_value': {'dummy': 'response'}
        })
        res = stepfns.terminate_asg_instance('i-abcd123')
        stepfns.asg_helper.terminate_instance.assert_called_once_with('i-abcd123', decrement_cap=True)
        self.assertDictEqual(res, {'dummy': 'response'})


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
