import boto3
import json
import logging

from botocore.exceptions import ClientError

import util

logger = logging.getLogger()
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)

ddb = boto3.client('dynamodb')
sfn = boto3.client('stepfunctions')


def put_item(table_name, group_name, my_execution_arn, ttl, prev_execution_arn=None):
    item = {
        'group_name': {'S': group_name},
        'execution_arn': {'S': my_execution_arn},
        'ttl': {'N': str(ttl)}
    }
    logger.debug('Putting DDB item into {0}: {1}'.format(table_name, json.dumps(item, default=util.json_dumps_converter)))
    try:
        if prev_execution_arn:
            logger.debug('Expecting previous value {}'.format(prev_execution_arn))
            return ddb.put_item(TableName=table_name, Item=item, ConditionExpression='execution_arn = :p_val',
                                ExpressionAttributeValues={':p_val': {'S': prev_execution_arn}})
        else:
            return ddb.put_item(TableName=table_name, Item=item, ConditionExpression='attribute_not_exists(execution_arn)')
    except ClientError as c:
        if c.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.debug(c.response['Error']['Message'])
            return None
        raise


def get_item(table_name, group_name):
    logger.debug('Fetching {0} from DDB table {1}'.format(group_name, table_name))
    resp = ddb.get_item(TableName=table_name, Key={'group_name': {'S': group_name}}, ConsistentRead=True)
    item = resp.get('Item', {})
    if item and 'execution_arn' in item:
        logger.debug('Item Found')
        return item['execution_arn']['S']
    logger.debug('Item Not Found')
    return None


def delete_item(table_name, group_name, my_execution_arn):
    key = {'group_name': {'S': group_name}}
    logger.debug('Deleting DDB item from table {0} [{1}]: {2}'.format(
        json.dumps(key, default=util.json_dumps_converter), my_execution_arn, table_name))
    return ddb.delete_item(TableName=table_name, Key=key, ConditionExpression='execution_arn = :p_val',
                           ExpressionAttributeValues={':p_val': {'S': my_execution_arn}})


def is_execution_running(execution_arn):
    logger.debug('Fetching state machine execution status of {}'.format(execution_arn))
    try:
        resp = sfn.describe_execution(executionArn=execution_arn)
    except ClientError as c:
        if c.response['Error']['Code'] == 'ExecutionDoesNotExist':
            logger.info(c.response['Error']['Message'])
            return False
        raise
    return resp.get('status') == 'RUNNING'
