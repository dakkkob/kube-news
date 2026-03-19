"""Lambda function to start/stop the kube-news EC2 worker on a schedule."""

import os

import boto3


def handler(event, context):
    instance_id = os.environ["INSTANCE_ID"]
    action = event.get("action", "")

    ec2 = boto3.client("ec2", region_name=os.environ.get("AWS_REGION", "eu-north-1"))

    if action == "start":
        ec2.start_instances(InstanceIds=[instance_id])
        print(f"Started instance {instance_id}")
    elif action == "stop":
        ec2.stop_instances(InstanceIds=[instance_id])
        print(f"Stopped instance {instance_id}")
    else:
        raise ValueError(f"Unknown action: {action}. Expected 'start' or 'stop'.")

    return {"action": action, "instance_id": instance_id}
