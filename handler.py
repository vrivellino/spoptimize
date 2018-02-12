import boto3
import json

from os import environ

import spoptimize.stepfns as stepfns
import spoptimize.util as util
from spoptimize.logging_helper import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sfn = boto3.client('stepfunctions')


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
                    step_fn_resps.append(sfn.start_execution(
                        stateMachineArn=state_machine_arn,
                        name=init_state['ondemand_instance_id'],
                        input=json.dumps(init_state, indent=2, default=util.json_dumps_converter)
                    ))
                else:
                    logger.error('Aborting executing: {}'.format(msg))
        retval = step_fn_resps

    # Test New ASG Instance
    elif action == 'ondemand-instance-healthy':
        retval = stepfns.asg_instance_state(event['autoscaling_group'], event['ondemand_instance_id'])

    # Request Spot Instance
    elif action == 'request-spot':
        retval = stepfns.request_spot_instance(event['autoscaling_group'], event['launch_az'],
                                               event['launch_subnet_id'], event['ondemand_instance_id'])

    # Check Spot Request
    elif action == 'check-spot':
        retval = stepfns.get_spot_request_status(event['spot_request']['SpotInstanceRequestId'])

    # Check ASG and Tag Spot
    elif action == 'check-asg-and-tag-spot':
        retval = stepfns.check_asg_and_tag_spot(event['autoscaling_group'], event['spot_request_result'], event['ondemand_instance_id'])

    # AutoScaling Group Disappeared
    elif action == 'term-spot-instance':
        retval = stepfns.terminate_ec2_instance(event.get('spot_request_result'))

    # Term OnDemand Before Attach Spot
    elif action == 'term-ondemand-attach-spot':
        retval = stepfns.attach_spot_instance(event['autoscaling_group'], event['spot_request_result'], event['ondemand_instance_id'])

    # Attach Spot Before Term OnDemand
    elif action == 'attach-spot':
        retval = stepfns.attach_spot_instance(event['autoscaling_group'], event['spot_request_result'], None)

    # Test Attached Instance
    elif action == 'spot-instance-healthy':
        retval = stepfns.asg_instance_state(event['autoscaling_group'], event['spot_request_result'])

    # Terminate OD Instance
    elif action == 'term-ondemand-instance':
        retval = stepfns.terminate_asg_instance(event['ondemand_instance_id'])

    else:
        raise Exception('SPOPTIMIZE_ACTION env var specifies unknown action: {}'.format(action))
    # Replace any instance of datetime.datetime in retval with a string to avoid
    # 'An error occurred during JSON serialization of response' Exception
    util.walk_dict_for_datetime(retval)
    return retval
