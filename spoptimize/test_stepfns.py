import copy
import datetime
import json
import os
import random
import unittest

# from botocore.exceptions import ClientError
from mock import Mock

import stepfns
import stepfn_strings as strs
from asg_helper import asg_copy_keys
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
    'iteration_count': 0,
    'ondemand_instance_id': launch_notification['EC2InstanceId'],
    'launch_subnet_id': launch_notification['Details']['Subnet ID'],
    'launch_az': launch_notification['Details']['Availability Zone'],
    'autoscaling_group': {},
    'min_protected_instances': 0,
    'init_sleep_interval': 0,
    'spot_req_sleep_interval': 30,
    'spot_attach_sleep_interval': 0,
    'spot_failure_sleep_interval': 3600
}


class TestInitMachineState(unittest.TestCase):

    def setUp(self):
        # self.maxDiff = None
        self.mock_attrs = copy.deepcopy(mock_attrs)
        mock_response = self.mock_attrs['autoscaling']['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0]
        self.asg_dict = {k: mock_response[k] for k in mock_response if k in asg_copy_keys}
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()
        stepfns.ddb_lock_helper = Mock()

    def test_standard_asg(self):
        logger.debug('TestInitMachineState.test_standard_asg')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        random.seed(randseed)
        expected_state = state_machine_init.copy()
        expected_state['autoscaling_group'] = self.asg_dict.copy()
        expected_state['init_sleep_interval'] = int(
            (self.asg_dict['HealthCheckGracePeriod'] * self.asg_dict['DesiredCapacity']) + (60 * random.random()) + 30
        )

        expected_state['spot_attach_sleep_interval'] = int(self.asg_dict['HealthCheckGracePeriod'] + 30)
        random.seed(randseed)
        (state_machine_dict, msg) = stepfns.init_machine_state(launch_notification)
        self.assertDictEqual(state_machine_dict, expected_state)
        self.assertGreater(state_machine_dict['init_sleep_interval'],
                           self.asg_dict['HealthCheckGracePeriod'] * self.asg_dict['DesiredCapacity'])
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
        for required_key in ['EC2InstanceId', 'AutoScalingGroupName', 'Details', 'Description']:
            bad_notification = copy.deepcopy(launch_notification)
            del(bad_notification[required_key])
            (state_machine_dict, msg) = stepfns.init_machine_state(bad_notification)
            self.assertDictEqual(state_machine_dict, {})
            self.assertTrue(msg)

    def test_attachment_notification(self):
        logger.debug('TestInitMachineState.test_attachment_notification')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        attach_notification = copy.deepcopy(launch_notification)
        attach_notification['Description'] = 'Attaching an existing EC2 instance: {}'.format(attach_notification['EC2InstanceId'])
        attach_notification['Cause'] = 'At 2018-03-05T22:04:49Z an instance was added in response to user request. Keeping the capacity at the new 1.'
        # launch notifications of attached instances do not include the Subnet ID
        del(attach_notification['Details']['Subnet ID'])
        (state_machine_dict, msg) = stepfns.init_machine_state(attach_notification)
        self.assertDictEqual(state_machine_dict, {})
        self.assertTrue(msg)

    def test_missing_az(self):
        logger.debug('TestInitMachineState.test_malformed_notification')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        bad_notification = copy.deepcopy(launch_notification)
        del(bad_notification['Details']['Availability Zone'])
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
        min_protected = 2
        self.asg_dict['Tags'].append({'Key': 'spoptimize:init_sleep_interval', 'Value': '{}'.format(wait_s)})
        self.asg_dict['Tags'].append({'Key': 'spoptimize:spot_req_sleep_interval', 'Value': '{}'.format(spot_req_wait_s)})
        self.asg_dict['Tags'].append({'Key': 'spoptimize:spot_attach_sleep_interval', 'Value': '{}'.format(attach_wait_s)})
        self.asg_dict['Tags'].append({'Key': 'spoptimize:spot_failure_sleep_interval', 'Value': '{}'.format(spot_fail_wait_s)})
        self.asg_dict['Tags'].append({'Key': 'spoptimize:min_protected_instances', 'Value': '{}'.format(min_protected)})
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict
        })
        (state_machine_dict, msg) = stepfns.init_machine_state(launch_notification)
        self.assertEqual(state_machine_dict['init_sleep_interval'], wait_s)
        self.assertEqual(state_machine_dict['spot_req_sleep_interval'], spot_req_wait_s)
        self.assertEqual(state_machine_dict['spot_attach_sleep_interval'], attach_wait_s)
        self.assertEqual(state_machine_dict['spot_failure_sleep_interval'], spot_fail_wait_s)
        self.assertEqual(state_machine_dict['min_protected_instances'], min_protected)
        self.assertIsNone(msg)


class TestAsgInstanceStatus(unittest.TestCase):

    def setUp(self):
        mock_response = copy.deepcopy(mock_attrs['autoscaling']['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0])
        self.asg_dict = {k: mock_response[k] for k in mock_response if k in asg_copy_keys}
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()
        stepfns.ddb_lock_helper = Mock()

    def test_valid_asg(self):
        logger.debug('TestAsgInstanceStatus.test_valid_asg')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': self.asg_dict,
            'get_instance_status.return_value': 'Healthy'
        })
        res = stepfns.asg_instance_state(self.asg_dict, 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.asg_helper.get_instance_status.assert_called()
        self.assertEqual(res, strs.asg_instance_healthy)

    def test_unknown_asg(self):
        logger.debug('TestAsgInstanceStatus.test_unknown_asg')
        stepfns.asg_helper = Mock(**{
            'describe_asg.return_value': {},
            'get_instance_status.return_value': 'Terminated'
        })
        res = stepfns.asg_instance_state(self.asg_dict, 'i-abcd123')
        stepfns.asg_helper.describe_asg.assert_called()
        stepfns.asg_helper.get_instance_status.assert_not_called()
        self.assertEqual(res, strs.asg_disappeared)


class TestRequestSpotInstance(unittest.TestCase):

    def setUp(self):
        mock_response = copy.deepcopy(mock_attrs['autoscaling']['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0])
        self.asg_dict = {k: mock_response[k] for k in mock_response if k in asg_copy_keys}
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()
        stepfns.ddb_lock_helper = Mock()

    def test_request_spot(self):
        logger.debug('TestRequestSpotInstance.test_request_spot')
        stepfns.spot_helper = Mock(**{
            'request_spot_instance.return_value': {'SpotInstanceRequestId': 'sir-xyz123'}
        })
        res = stepfns.request_spot_instance(self.asg_dict,
                                            launch_notification['Details']['Availability Zone'],
                                            launch_notification['Details']['Subnet ID'],
                                            'test-activity')
        stepfns.asg_helper.get_launch_config.assert_called()
        stepfns.spot_helper.request_spot_instance.assert_called()
        self.assertDictEqual(res, {'SpotInstanceRequestId': 'sir-xyz123'})


class TestGetSpotRequestStatus(unittest.TestCase):

    def setUp(self):
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()
        stepfns.ddb_lock_helper = Mock()

    def test_get_spot_request_status(self):
        logger.debug('TestGetSpotRequestStatus.test_get_spot_request_status')
        stepfns.spot_helper = Mock(**{'get_spot_request_status.return_value': 'Pending'})
        res = stepfns.get_spot_request_status('sir-test')
        stepfns.spot_helper.get_spot_request_status.assert_called_with('sir-test')
        stepfns.ec2_helper.is_instance_running.assert_not_called()
        self.assertEqual(res, strs.spot_request_pending)

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
        self.assertEqual(res, strs.spot_request_pending)

    def test_get_spot_request_status_unknown_instance(self):
        logger.debug('TestGetSpotRequestStatus.test_get_spot_request_status')
        stepfns.spot_helper = Mock(**{'get_spot_request_status.return_value': 'i-abcd123'})
        stepfns.ec2_helper = Mock(**{'is_instance_running.return_value': None})
        res = stepfns.get_spot_request_status('sir-test')
        stepfns.spot_helper.get_spot_request_status.assert_called_with('sir-test')
        stepfns.ec2_helper.is_instance_running.assert_called_once_with('i-abcd123')
        self.assertEqual(res, strs.spot_request_pending)


class TestAttachSpotInstance(unittest.TestCase):

    def setUp(self):
        mock_response = copy.deepcopy(mock_attrs['autoscaling']['describe_auto_scaling_groups.return_value']['AutoScalingGroups'][0])
        self.asg_dict = {k: mock_response[k] for k in mock_response if k in asg_copy_keys}
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()
        stepfns.ddb_lock_helper = Mock()

    def test_no_capacity(self):
        logger.debug('TestAttachSpotInstance.test_no_capacity')
        expected_res = strs.success
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
        expected_res = strs.success
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
        expected_res = strs.asg_disappeared
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
        expected_res = strs.spot_instance_disappeared
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
        expected_res = strs.od_instance_disappeared
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


class TestAcquireLock(unittest.TestCase):

    def setUp(self):
        self.table_name = 'ddbtable'
        self.group_name = 'group-name'
        self.exec_arn = 'my:execution:arn'
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()
        stepfns.ddb_lock_helper = Mock()

    def test_lock_acquired_no_existing(self):
        logger.debug('TestAcquireLock.test_lock_acquired_no_existing')
        stepfns.ddb_lock_helper = Mock(**{
            'put_item.return_value': True
        })
        res = stepfns.acquire_lock(self.table_name, self.group_name, self.exec_arn)
        stepfns.ddb_lock_helper.put_item.assert_called_once()
        stepfns.ddb_lock_helper.get_item.assert_not_called()
        stepfns.ddb_lock_helper.is_execution_running.assert_not_called()
        self.assertTrue(res)

    def test_lock_already_acquired(self):
        logger.debug('TestAcquireLock.test_lock_already_acquired')
        stepfns.ddb_lock_helper = Mock(**{
            'put_item.return_value': False,
            'get_item.return_value': self.exec_arn
        })
        res = stepfns.acquire_lock(self.table_name, self.group_name, self.exec_arn)
        stepfns.ddb_lock_helper.put_item.assert_called_once()
        stepfns.ddb_lock_helper.get_item.assert_called_once()
        stepfns.ddb_lock_helper.is_execution_running.assert_not_called()
        self.assertTrue(res)

    def test_lock_not_acquired_existing_owner(self):
        logger.debug('TestAcquireLock.test_lock_not_acquired_existing_owner')
        stepfns.ddb_lock_helper = Mock(**{
            'put_item.return_value': False,
            'get_item.return_value': 'other:execution:arn',
            'is_execution_running.return_value': True
        })
        res = stepfns.acquire_lock(self.table_name, self.group_name, self.exec_arn)
        stepfns.ddb_lock_helper.put_item.assert_called_once()
        stepfns.ddb_lock_helper.get_item.assert_called_once()
        stepfns.ddb_lock_helper.is_execution_running.assert_called_once()
        self.assertFalse(res)

    def test_lock_acquired_old_owner(self):
        logger.debug('TestAcquireLock.test_lock_acquired_old_owner')
        stepfns.ddb_lock_helper = Mock(**{
            'put_item.side_effect': [False, True],
            'get_item.return_value': 'other:execution:arn',
            'is_execution_running.return_value': False
        })
        res = stepfns.acquire_lock(self.table_name, self.group_name, self.exec_arn)
        stepfns.ddb_lock_helper.put_item.assert_called()
        stepfns.ddb_lock_helper.get_item.assert_called_once()
        stepfns.ddb_lock_helper.is_execution_running.assert_called_once()
        self.assertTrue(res)

    def test_lock_not_acquired_old_owner(self):
        logger.debug('TestAcquireLock.test_lock_not_acquired_old_owner')
        stepfns.ddb_lock_helper = Mock(**{
            'put_item.return_value': False,
            'get_item.return_value': 'other:execution:arn',
            'is_execution_running.return_value': False
        })
        res = stepfns.acquire_lock(self.table_name, self.group_name, self.exec_arn)
        stepfns.ddb_lock_helper.put_item.assert_called()
        stepfns.ddb_lock_helper.get_item.assert_called_once()
        stepfns.ddb_lock_helper.is_execution_running.assert_called_once()
        self.assertFalse(res)


class TestReleaseLock(unittest.TestCase):

    def setUp(self):
        self.table_name = 'ddbtable'
        self.group_name = 'group-name'
        self.exec_arn = 'my:execution:arn'
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()
        stepfns.ddb_lock_helper = Mock()

    def test_delete_item_is_called(self):
        logger.debug('TestReleaseLock.test_delete_item_is_called')
        stepfns.release_lock(self.table_name, self.group_name, self.exec_arn)
        stepfns.ddb_lock_helper.delete_item.assert_called_once_with(self.table_name, self.group_name, self.exec_arn)


class TestProtectedInstance(unittest.TestCase):

    def setUp(self):
        self.instance_id = 'i-abcd123'
        self.table_name = 'ddbtable'
        self.group_name = 'group-name'
        self.exec_arn = 'my:execution:arn'
        stepfns.asg_helper = Mock()
        stepfns.ec2_helper = Mock()
        stepfns.spot_helper = Mock()
        stepfns.ddb_lock_helper = Mock()

    def test_no_protected_instances(self):
        logger.debug('TestProtectedInstance.test_no_protected_instances')
        res = stepfns.protected_instance(self.group_name, self.instance_id, 0, self.table_name, self.exec_arn)
        stepfns.ddb_lock_helper.put_item.assert_not_called()
        stepfns.asg_helper.not_enough_protected_instances.assert_not_called()
        stepfns.asg_helper.protect_instance.assert_not_called()
        stepfns.ddb_lock_helper.delete_item.assert_not_called()
        self.assertIsNone(res)

    def test_instance_should_be_protected(self):
        logger.debug('TestProtectedInstance.test_instance_should_be_protected')
        stepfns.asg_helper = Mock(**{
            'not_enough_protected_instances.return_value': True
        })
        stepfns.ddb_lock_helper = Mock(**{
            'put_item.return_value': True
        })
        res = stepfns.protected_instance(self.group_name, self.instance_id, 1, self.table_name, self.exec_arn)
        stepfns.ddb_lock_helper.put_item.assert_called_once()
        stepfns.asg_helper.not_enough_protected_instances.assert_called_once_with(self.group_name, 1)
        stepfns.asg_helper.protect_instance.assert_called_once_with(self.group_name, self.instance_id)
        stepfns.ddb_lock_helper.delete_item.assert_called_once()
        self.assertIsNone(res)

    def test_instance_should_not_be_protected(self):
        logger.debug('TestProtectedInstance.test_instance_should_not_be_protected')
        stepfns.asg_helper = Mock(**{
            'not_enough_protected_instances.return_value': False
        })
        stepfns.ddb_lock_helper = Mock(**{
            'put_item.return_value': True
        })
        res = stepfns.protected_instance(self.group_name, self.instance_id, 1, self.table_name, self.exec_arn)
        stepfns.ddb_lock_helper.put_item.assert_called_once()
        stepfns.asg_helper.not_enough_protected_instances.assert_called_once_with(self.group_name, 1)
        stepfns.asg_helper.protect_instance.assert_not_called()
        stepfns.ddb_lock_helper.delete_item.assert_called_once()
        self.assertIsNone(res)

    def test_could_not_acquire_lock(self):
        logger.debug('TestProtectedInstance.test_could_not_acquire_lock')
        stepfns.ddb_lock_helper = Mock(**{
            'put_item.return_value': None,
            'get_item.return_value': 'other:execution:arn',
            'get_item.is_execution_running': True
        })
        res = stepfns.protected_instance(self.group_name, self.instance_id, 1, self.table_name, self.exec_arn)
        stepfns.ddb_lock_helper.put_item.assert_called_once()
        stepfns.asg_helper.not_enough_protected_instances.assert_not_called()
        stepfns.asg_helper.protect_instance.assert_not_called()
        stepfns.ddb_lock_helper.delete_item.assert_not_called()
        self.assertEqual(res, strs.unable_to_acquire_lock)


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
