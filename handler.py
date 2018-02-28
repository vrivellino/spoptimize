import boto3
import json

from os import environ

import spoptimize.spot_warning as spot_warning
import spoptimize.stepfns as stepfns
import spoptimize.util as util
from spoptimize.logging_helper import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sfn = boto3.client('stepfunctions')


class InstancePending(Exception):
    pass


class GroupLocked(Exception):
    pass


def handler(event, context):
    logger.debug('EVENT: {}'.format(json.dumps(event, indent=2, default=util.json_dumps_converter)))
    action = environ.get('SPOPTIMIZE_ACTION').lower()
    if not action:
        raise Exception('SPOPTIMIZE_ACTION env var is not set')
    if environ.get('SPOPTIMIZE_DEBUG', 'false').lower() not in ['0', 'no', 'false']:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    retval = None

    # Process an autoscaling launch event via SNS; Start execution of step fns
    if action == 'start-state-machine':
        state_machine_arn = environ['SPOPTIMIZE_SFN_ARN']
        step_fn_resps = []
        for record in event['Records']:
            if 'Sns' in record and 'Message' in record['Sns']:
                (init_state, msg) = stepfns.init_machine_state(json.loads(record['Sns']['Message']))
                if init_state['autoscaling_group']:
                    logger.debug('Starting execution of {0} with name {1}'.format(state_machine_arn, init_state['ondemand_instance_id']))
                    logger.debug('Input: {}'.format(json.dumps(init_state, indent=2, default=util.json_dumps_converter)))
                    # NOTE: execution ARN is used for locks. if name changes, update lock acquisition & release
                    step_fn_resps.append(sfn.start_execution(
                        stateMachineArn=state_machine_arn,
                        name=init_state['ondemand_instance_id'],
                        input=json.dumps(init_state, indent=2, default=util.json_dumps_converter)
                    ))
                else:
                    logger.error('Aborting executing: {}'.format(msg))
        retval = step_fn_resps

    # Increment Count
    elif action == 'increment-count':
        retval = int(event['iteration_count']) + 1

    # Test New ASG Instance
    elif action == 'ondemand-instance-healthy':
        retval = stepfns.asg_instance_state(event['autoscaling_group'], event['ondemand_instance_id'])
        if retval == 'Pending':
            raise InstancePending('{} is not online and/or healthy'.format(event['ondemand_instance_id']))

    # Request Spot Instance
    elif action == 'request-spot':
        client_token = '{0}-{1}'.format(event['ondemand_instance_id'], event['iteration_count'])
        retval = stepfns.request_spot_instance(event['autoscaling_group'], event['launch_az'],
                                               event['launch_subnet_id'], client_token)

    # Check Spot Request
    elif action == 'check-spot':
        if event['spot_request'].get('SpoptimizeError'):
            logger.info('Spot request error'.format(event['spot_request']['SpoptimizeError']))
            retval = 'Failure'
        else:
            retval = stepfns.get_spot_request_status(event['spot_request']['SpotInstanceRequestId'])

    # AutoScaling Group Disappeared
    elif action == 'term-spot-instance':
        retval = stepfns.terminate_ec2_instance(event.get('spot_request_result'))

    # Acquire AutoScaling Group Lock
    elif action == 'acquire-lock':
        # Generate execution ARN from state machine ARN
        my_arn = environ['SPOPTIMIZE_SFN_ARN'].split(':')
        my_arn[5] = 'execution'
        my_arn.append(event['ondemand_instance_id'])
        if stepfns.acquire_lock(environ['SPOPTIMIZE_LOCK_TABLE'],
                                event['autoscaling_group']['AutoScalingGroupName'],
                                ':'.join(my_arn)):
            retval = True
        else:
            raise GroupLocked('Unable to acquire lock')

    # Release AutoScaling Group Lock
    elif action == 'release-lock':
        # Generate execution ARN from state machine ARN
        my_arn = environ['SPOPTIMIZE_SFN_ARN'].split(':')
        my_arn[5] = 'execution'
        my_arn.append(event['ondemand_instance_id'])
        retval = stepfns.release_lock(environ['SPOPTIMIZE_LOCK_TABLE'],
                                      event['autoscaling_group']['AutoScalingGroupName'],
                                      ':'.join(my_arn))

    # Attach Spot Instance
    elif action == 'attach-spot':
        retval = stepfns.attach_spot_instance(event['autoscaling_group'], event['spot_request_result'], event['ondemand_instance_id'])

    # Test Attached Instance
    elif action == 'spot-instance-healthy':
        retval = stepfns.asg_instance_state(event['autoscaling_group'], event['spot_request_result'])
        if retval == 'Pending':
            raise InstancePending('{} is not online and/or healthy'.format(event['spot_request_result']))

    else:
        raise Exception('SPOPTIMIZE_ACTION env var specifies unknown action: {}'.format(action))
    # Replace any instance of datetime.datetime in retval with a string to avoid
    # 'An error occurred during JSON serialization of response' Exception
    util.walk_dict_for_datetime(retval)
    return retval


def spot_warning_handler(event, context):
    logger.debug('EVENT: {}'.format(json.dumps(event, indent=2, default=util.json_dumps_converter)))
    if environ.get('SPOPTIMIZE_DEBUG', 'false').lower() not in ['0', 'no', 'false']:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    spot_warning.process_warning_event(event)
