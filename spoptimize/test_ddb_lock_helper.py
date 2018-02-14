import unittest
from botocore.exceptions import ClientError
from mock import Mock

import ddb_lock_helper
from logging_helper import logging, setup_stream_handler

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())


class TestPutItem(unittest.TestCase):

    def setUp(self):
        self.table_name = 'ddbtable'
        self.group_name = 'asg-group'
        self.exec_arn = 'my:execution:arn'
        self.ttl = 1234
        ddb_lock_helper.ddb = Mock()
        ddb_lock_helper.sfn = Mock()

    def test_put_item_none_existing(self):
        logger.debug('TestPutItem.test_put_item_none_existing')
        ddb_lock_helper.ddb = Mock(**{
            'put_item.return_value': {}
        })
        expected_item = {
            'group_name': {'S': self.group_name},
            'execution_arn': {'S': self.exec_arn},
            'ttl': {'N': str(self.ttl)}
        }
        res = ddb_lock_helper.put_item(self.table_name, self.group_name, self.exec_arn, self.ttl)
        ddb_lock_helper.ddb.put_item.assert_called_once_with(TableName=self.table_name, Item=expected_item,
                                                             ConditionExpression='attribute_not_exists(execution_arn)')

        self.assertDictEqual(res, {})

    def test_put_item_none_existing_cond_fail(self):
        logger.debug('TestPutItem.test_put_item_none_existing_cond_fail')
        ddb_lock_helper.ddb = Mock(**{'put_item.side_effect': ClientError({
            'Error': {
                'Code': 'ConditionalCheckFailedException',
                'Message': 'The conditional request failed'
            }
        }, 'PutItem')})
        res = ddb_lock_helper.put_item(self.table_name, self.group_name, self.exec_arn, self.ttl)
        # should not raise an exception
        self.assertIsNone(res)

    def test_put_item_existing_record_expected(self):
        logger.debug('TestPutItem.test_put_item_existing_record')
        ddb_lock_helper.ddb = Mock(**{
            'put_item.return_value': {}
        })
        expected_item = {
            'group_name': {'S': self.group_name},
            'execution_arn': {'S': self.exec_arn},
            'ttl': {'N': str(self.ttl)}
        }
        prev_exec_arn = 'prev:execution:arn'
        res = ddb_lock_helper.put_item(self.table_name, self.group_name, self.exec_arn, self.ttl, prev_exec_arn)
        ddb_lock_helper.ddb.put_item.assert_called_once_with(TableName=self.table_name, Item=expected_item,
                                                             ConditionExpression='execution_arn = :p_val',
                                                             ExpressionAttributeValues={':p_val': {'S': prev_exec_arn}})
        self.assertDictEqual(res, {})

    def test_put_item_existing_record_unexpected(self):
        logger.debug('TestPutItem.test_put_item_existing_record_unexpected')
        ddb_lock_helper.ddb = Mock(**{'put_item.side_effect': ClientError({
            'Error': {
                'Code': 'ConditionalCheckFailedException',
                'Message': 'The conditional request failed'
            }
        }, 'PutItem')})
        prev_exec_arn = 'prev:execution:arn'
        res = ddb_lock_helper.put_item(self.table_name, self.group_name, self.exec_arn, self.ttl, prev_exec_arn)
        # should not raise an exception
        self.assertIsNone(res)


class TestGetItem(unittest.TestCase):

    def setUp(self):
        self.table_name = 'ddbtable'
        self.group_name = 'asg-group'
        ddb_lock_helper.ddb = Mock()
        ddb_lock_helper.sfn = Mock()

    def test_get_item_found(self):
        logger.debug('TestPutItem.test_get_item_found')
        ddb_lock_helper.ddb = Mock(**{
            'get_item.return_value': {
                'Item': {
                    'execution_arn': {'S': 'my:execution:arn'},
                    'group_name': {'S': self.group_name},
                    'ttl': {'N': '1518620700'}
                }
            }
        })
        res = ddb_lock_helper.get_item(self.table_name, self.group_name)
        ddb_lock_helper.ddb.get_item.assert_called_once_with(TableName=self.table_name,
                                                             Key={'group_name': {'S': self.group_name}},
                                                             ConsistentRead=True)
        self.assertEqual(res, 'my:execution:arn')

    def test_get_item_not_found(self):
        logger.debug('TestPutItem.test_get_item_not_found')
        ddb_lock_helper.ddb = Mock(**{
            'get_item.return_value': {}
        })
        res = ddb_lock_helper.get_item(self.table_name, self.group_name)
        self.assertIsNone(res)


class TestDeleteItem(unittest.TestCase):

    def setUp(self):
        self.table_name = 'ddbtable'
        self.group_name = 'asg-group'
        self.exec_arn = 'my:execution:arn'
        ddb_lock_helper.ddb = Mock()
        ddb_lock_helper.sfn = Mock()

    def test_delete_item(self):
        logger.debug('TestDeleteItem.test_delete_item')
        ddb_lock_helper.delete_item(self.table_name, self.group_name, self.exec_arn)
        ddb_lock_helper.ddb.delete_item.assert_called_once_with(TableName=self.table_name,
                                                                Key={'group_name': {'S': self.group_name}},
                                                                ConditionExpression='execution_arn = :p_val',
                                                                ExpressionAttributeValues={':p_val': {'S': self.exec_arn}})


class TestIsExecutionRunning(unittest.TestCase):

    def setUp(self):
        self.exec_arn = 'my:execution:arn'
        self.resp = {
            'name': 'arn',
            'stateMachineArn': 'my:state:arn',
            'executionArn': self.exec_arn,
            'input': 'hello world',
            'startDate': '2018-02-13T14:19:31.000Z',
            'stopDate': '2018-02-13T14:20:00.000Z',
            'status': 'FAILED'
        }
        ddb_lock_helper.ddb = Mock()
        ddb_lock_helper.sfn = Mock()

    def test_execution_is_running(self):
        logger.debug('TestIsExecutionRunning.test_execution_is_running')
        self.resp['status'] = 'RUNNING'
        ddb_lock_helper.sfn = Mock(**{
            'describe_execution.return_value': self.resp
        })
        res = ddb_lock_helper.is_execution_running(self.exec_arn)
        ddb_lock_helper.sfn.describe_execution.assert_called_once_with(executionArn=self.exec_arn)
        self.assertTrue(res)

    def test_execution_is_not_running(self):
        logger.debug('TestIsExecutionRunning.test_execution_is_not_running')
        for state in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
            self.resp['status'] = state
            ddb_lock_helper.sfn = Mock(**{
                'describe_execution.return_value': self.resp
            })
            res = ddb_lock_helper.is_execution_running(self.exec_arn)
            self.assertFalse(res)

    def test_execution_does_not_exist(self):
        logger.debug('TestIsExecutionRunning.test_execution_does_not_exist')
        ddb_lock_helper.ddb = Mock(**{'describe_execution.side_effect': ClientError({
            'Error': {
                'Code': 'ExecutionDoesNotExist',
                'Message': "Execution Does Not Exist: '{}'".format(self.exec_arn)
            }
        }, 'DescribeExecution')})
        res = ddb_lock_helper.is_execution_running(self.exec_arn)
        self.assertFalse(res)


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    setup_stream_handler()
    unittest.main()
