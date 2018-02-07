import unittest
from mock import Mock

import ec2_helper
from logging_helper import logging, setup_stream_handler

logger = logging.getLogger()


class TestEc2Helper(unittest.TestCase):

    def setUp(self):
        ec2_helper.ec2 = Mock()

    def test_term_instance(self):
        logger.debug('TestEc2Helper.test_term_instance')
        ec2_helper.terminate_instance('i-abcd123')
        ec2_helper.ec2.terminate_instances.assert_called()

    def test_tag_instance(self):
        logger.debug('TestEc2Helper.test_tag_instance')
        ec2_helper.tag_instance('i-abcd123', [{'Key': 'testkey', 'Value': 'testval'}])
        ec2_helper.ec2.create_tags.assert_called()

    def test_tag_instance_no_tags(self):
        logger.debug('TestEc2Helper.test_tag_instance_no_tags')
        ec2_helper.tag_instance('i-abcd123', [])
        ec2_helper.ec2.create_tags.assert_not_called()


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
