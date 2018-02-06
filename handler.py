import boto3
import json
import spoptimize

from os import environ

sfn = boto3.client('stepfunctions')


def start_state_machine(event, context):
    '''
    Processes an autoscaling launch event via SNS; Starts execution of step fns
    '''
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    mock_mode = environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false'
    state_machine_arn = environ['SPOPTIMIZE_SFN_ARN']
    step_fn_resps = []
    for record in event['Records']:
        if 'Sns' in record and 'Message' in record['Sns']:
            (init_state, msg) = spoptimize.init_machine_state(json.loads(record['Sns']['Message']), mock=mock_mode)
            if init_state['autoscaling_group']:
                step_fn_resps.append(sfn.start_execution(
                    stateMachineArn=state_machine_arn,
                    name=init_state['ActivityId'],
                    input=json.dumps(init_state)))
            else:
                print('Aborting executing: {}'.format(msg))
    return step_fn_resps


def ondemand_instance_healthy(event, context):
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    mock_mode = environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false'
    return spoptimize.asg_instance_state(event['ondemand_instance_id'], mock=mock_mode)


def request_spot_instance(event, context):
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    mock_mode = environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false'
    return spoptimize.request_spot_instance(
        event['activity_id'],
        event['autoscaling_group'],
        event['launch_az'],
        event['launch_subnet_id'],
        mock=mock_mode
    )


def check_spot_request(event, context):
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    mock_mode = environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false'
    return spoptimize.get_spot_request_status(event['spot_request']['SpotInstanceRequestId'], mock=mock_mode)


def check_asg_and_tag_spot(event, context):
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    mock_mode = environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false'
    return spoptimize.check_asg_and_tag_spot(event['asg'], event['spot_request_result'],
                                             event['ondemand_instance_id'], mock=mock_mode)


def term_ondemand_attach_spot(event, context):
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    mock_mode = environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false'
    return spoptimize.attach_spot_instance(event['asg'], event['spot_request_result'],
                                           event['ondemand_instance_id'], mock=mock_mode)


def attach_spot(event, context):
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    mock_mode = environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false'
    return spoptimize.attach_spot_instance(event['asg'], event['spot_request_result'], None, mock=mock_mode)


def spot_instance_healthy(event, context):
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    mock_mode = environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false'
    return spoptimize.asg_instance_state(event['spot_request_result'], mock=mock_mode)


def asg_instance_healthy(event, context):
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    if environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false':
        print('MOCK MODE: Instance Healthy')
        return 'Healthy'
    # TODO
    raise Exception('Active mode not supported')


def terminate_instance(event, context):
    print('EVENT: {}'.format(json.dumps(event, indent=2)))
    if environ.get('SPOPTIMIZE_MOCK', 'false').lower() != 'false':
        print('MOCK MODE: Instance Terminated')
        return 'SUCCESS'
    # TODO
    raise Exception('Active mode not supported')
