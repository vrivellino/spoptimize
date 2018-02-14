import json
import logging

import asg_helper
import ec2_helper
import util

logger = logging.getLogger()


def process_warning_event(event):
    event_source = event.get('source')
    event_detail_type = event.get('detail-type')
    if event_source != 'aws.ec2' or event_detail_type != 'EC2 Spot Instance Interruption Warning':
        raise Exception('Malformed event: {}'.format(json.dumps(event, indent=2, default=util.json_dumps_converter)))
    if event['detail']['instance-action'] != 'terminate':
        raise Exception('Invalid or unknown event: {}'.format(json.dumps(event, indent=2, default=util.json_dumps_converter)))
    instance_id = event['detail']['instance-id']
    logger.info('EC2 Spot Interruption Warning received for {}'.format(instance_id))
    if ec2_helper.is_spoptimize_instance(instance_id):
        logger.info('{} was launched by spoptimize ... terminating via autoscaling API'.format(instance_id))
        asg_helper.terminate_instance(instance_id, decrement_cap=False)
    else:
        logger.info('{} was not launched by spoptimize ... ignoring'.format(instance_id))
