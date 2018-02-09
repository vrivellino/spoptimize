import unittest
from botocore.exceptions import ClientError
from mock import Mock

import ec2_helper
from logging_helper import logging, setup_stream_handler

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())


class TestTerminateInstance(unittest.TestCase):

    def test_terminate_instance(self):
        logger.debug('TestTerminateInstance.terminate_instance')
        ec2_helper.ec2 = Mock()
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


class TestTagInstance(unittest.TestCase):

    def test_tag_instance(self):
        logger.debug('TestEc2Helper.test_tag_instance')
        ec2_helper.ec2 = Mock()
        res = ec2_helper.tag_instance('i-9999999', 'i-abcd123', [{'Key': 'testkey', 'Value': 'testval'}])
        ec2_helper.ec2.create_tags.assert_called_once_with(
            Resources=['i-9999999'],
            Tags=[{'Key': 'testkey', 'Value': 'testval'}, {'Key': 'spoptimize:orig_instance_id', 'Value': 'i-abcd123'}]
        )
        self.assertTrue(res)

    def test_tag_instance_no_tags(self):
        logger.debug('TestTagInstance.test_tag_instance_no_tags')
        ec2_helper.ec2 = Mock()
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


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
