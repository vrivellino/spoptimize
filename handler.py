import boto3
import datetime
import json

from os import environ

import spoptimize.stepfns as stepfns
from spoptimize.logging_helper import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sfn = boto3.client('stepfunctions')


def json_dumps_converter(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    raise TypeError("Unknown type")


def handler(event, context):
    logger.debug('EVENT: {}'.format(json.dumps(event, indent=2, default=json_dumps_converter)))
    action = environ.get('SPOPTIMIZE_ACTION').lower()
    if not action:
        raise Exception('SPOPTIMIZE_ACTION env var is not set')
    if environ.get('SPOPTIMIZE_DEBUG', 'false').lower() not in ['0', 'no', 'false']:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Process an autoscaling launch event via SNS; Start execution of step fns
    if action == 'start-state-machine':
        state_machine_arn = environ['SPOPTIMIZE_SFN_ARN']
        step_fn_resps = []
        for record in event['Records']:
            if 'Sns' in record and 'Message' in record['Sns']:
                (init_state, msg) = stepfns.init_machine_state(json.loads(record['Sns']['Message']))
                if init_state['autoscaling_group']:
                    logger.debug('Starting execution of {0} with name {1}'.format(state_machine_arn, init_state['activity_id']))
                    logger.debug('Input: {}'.format(json.dumps(init_state, indent=2, default=json_dumps_converter)))
                    step_fn_resps.append(sfn.start_execution(
                        stateMachineArn=state_machine_arn,
                        name=init_state['activity_id'],
                        input=json.dumps(init_state, indent=2, default=json_dumps_converter)
                    ))
                else:
                    logger.error('Aborting executing: {}'.format(msg))
        return step_fn_resps

    # Test New ASG Instance
    elif action == 'ondemand-instance-healthy':
        return stepfns.asg_instance_state(event['autoscaling_group'], event['ondemand_instance_id'])

    # Request Spot Instance
    elif action == 'request-spot':
        return stepfns.request_spot_instance(event['autoscaling_group'], event['launch_az'],
                                             event['launch_subnet_id'], event['activity_id'])

    # Check Spot Request
    elif action == 'check-spot':
        return stepfns.get_spot_request_status(event['spot_request']['SpotInstanceRequestId'])

    # Check ASG and Tag Spot
    elif action == 'check-asg-and-tag-spot':
        return stepfns.check_asg_and_tag_spot(event['asg'], event['spot_request_result'], event['ondemand_instance_id'])

    # AutoScaling Group Disappeared
    elif action == 'term-spot-instance':
        return stepfns.terminate_ec2_instance(event.get('spot_request_result'))

    # Term OnDemand Before Attach Spot
    elif action == 'term-ondemand-attach-spot':
        return stepfns.attach_spot_instance(event['asg'], event['spot_request_result'], event['ondemand_instance_id'])

    # Attach Spot Before Term OnDemand
    elif action == 'attach-spot':
        return stepfns.attach_spot_instance(event['asg'], event['spot_request_result'], None)

    # Test Attached Instance
    elif action == 'spot-instance-healthy':
        return stepfns.asg_instance_state(event['autoscaling_group'], event['spot_request_result'])

    # Terminate OD Instance
    elif action == 'term-ondemand-instance':
        return stepfns.terminate_asg_instance(event['ondemand_instance_id'])

    else:
        raise Exception('SPOPTIMIZE_ACTION env var specifies unknown action: {}'.format(action))
