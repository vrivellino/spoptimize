import copy
import unittest
from mock import Mock

import spot_warning
from logging_helper import logging, setup_stream_handler

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())

sample_warning_event = {
    'account': '123456789012',
    'source': 'aws.ec2',
    'detail': {
        'instance-action': 'terminate',
        'instance-id': 'i-02aaeba0211010942'
    },
    'detail-type': 'EC2 Spot Instance Interruption Warning',
    'id': 'b082f84f-569f-cc21-f89d-3beb103b5c9e',
    'region': 'us-east-1',
    'resources': ['arn:aws:ec2:us-east-1c:instance/i-08cb4315e07e136ef'],
    'time': '2018-01-29T23:25:20Z',
    'version': '0'
}


class TestProcessSpotWarningEvent(unittest.TestCase):

    def setUp(self):
        self.event = copy.deepcopy(sample_warning_event)
        spot_warning.asg_helper = Mock()
        spot_warning.ec2_helper = Mock()

    def test_malformed_event(self):
        logger.debug('TestProcessSpotWarningEvent.test_malformed_event')
        with self.assertRaises(Exception):
            spot_warning.process_warning_event({})

    def test_invalid_event(self):
        logger.debug('TestProcessSpotWarningEvent.test_invalid_event')
        self.event['detail']['instance-action'] = 'unknown'
        with self.assertRaises(Exception):
            spot_warning.process_warning_event(self.event)

    def test_not_spoptimize_instance(self):
        logger.debug('TestProcessSpotWarningEvent.test_not_spoptimize_instance')
        spot_warning.ec2_helper = Mock(**{'is_spoptimize_instance.return_value': False})
        spot_warning.process_warning_event(self.event)
        spot_warning.ec2_helper.is_spoptimize_instance.assert_called_once_with(self.event['detail']['instance-id'])
        spot_warning.asg_helper.terminate_instance.assert_not_called()

    def test_terminate_spoptimize_instance(self):
        logger.debug('TestProcessSpotWarningEvent.test_terminate_spoptimize_instance')
        spot_warning.ec2_helper = Mock(**{'is_spoptimize_instance.return_value': True})
        spot_warning.process_warning_event(self.event)
        spot_warning.ec2_helper.is_spoptimize_instance.assert_called_once_with(self.event['detail']['instance-id'])
        spot_warning.asg_helper.terminate_instance.assert_called_once_with(self.event['detail']['instance-id'], decrement_cap=False)


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
