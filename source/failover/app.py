import os
import json
import boto3
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics()
tracer = Tracer()
logger = Logger()


@metrics.log_metrics(capture_cold_start_metric=False)
@logger.inject_lambda_context(log_event=True, clear_state=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    function = event["FUNCTION"]

    if function == "get_current_routing_control_state":
        return get_current_routing_control_state(event, context)
    elif function == "rotate_arc_controls":
        return rotate_arc_controls(event, context)
    else:
        dummy(event, context)


@tracer.capture_method
def get_current_routing_control_state(event, context):

    logger.info("get_current_routing_control_state Invoked")
    endpoints = json.loads(os.environ['ARC_CLUSTER_ENDPOINTS'])
    routing_control_arn = os.environ['ARC_ROUTING_CONTROL_ARN']

    for region, endpoint in endpoints.items():
        try:
            logger.info("route 53 recover cluster endpoint: " + endpoint)
            client = boto3.client('route53-recovery-cluster', region_name=region, endpoint_url=endpoint)
            routing_control_state = client.get_routing_control_state(RoutingControlArn=routing_control_arn)

            logger.info("routing Control State is " + routing_control_state["RoutingControlState"])

            return {'routing_control_state': routing_control_state["RoutingControlState"]}
        except Exception as e:
            logger.exception("Exception occurred while getting current routing control state")


@tracer.capture_method
def rotate_arc_controls(event, context):

    logger.info("update_arc_control Invoked")
    endpoints = json.loads(os.environ['ARC_CLUSTER_ENDPOINTS'])
    routing_control_arn = os.environ['ARC_ROUTING_CONTROL_ARN']
    updated_routing_control_state = "NotUpdated"
    done = False
    for region, endpoint in endpoints.items():
        try:
            logger.info("route 53 recovery cluster endpoint: " + endpoint)
            client = boto3.client('route53-recovery-cluster', region_name=region, endpoint_url=endpoint)

            logger.info("toggling routing control")
            routing_control_state = client.get_routing_control_state(RoutingControlArn=routing_control_arn)
            logger.info("Current Routing Control State: " + routing_control_state["RoutingControlState"])
            if routing_control_state["RoutingControlState"] == "On":
                client.update_routing_control_state(RoutingControlArn=routing_control_arn, RoutingControlState="Off")
                routing_control_state = client.get_routing_control_state(RoutingControlArn=routing_control_arn)
                updated_routing_control_state = routing_control_state["RoutingControlState"]
                logger.info("Updated routing Control State is " + updated_routing_control_state)
                done = True
                break
            else:
                client.update_routing_control_state(RoutingControlArn=routing_control_arn, RoutingControlState="On")
                routing_control_state = client.get_routing_control_state(RoutingControlArn=routing_control_arn)
                updated_routing_control_state = routing_control_state["RoutingControlState"]
                logger.info("Updated routing Control State is " + updated_routing_control_state)
                done = True
                break
        except Exception as e:
            logger.exception("Exception occurred while toggling ARC Routing Control")
        if done:
            metrics.add_metric(name="RegionalFailover", unit=MetricUnit.Count, value=1)
            break
    return {'routing_control_state': updated_routing_control_state}


def dummy(event, context):
    logger.info("dummy")


if __name__ == "__main__":
    event = dict()
    event["FUNCTION"] = "dummy"
    lambda_handler(event, None)
