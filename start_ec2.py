import boto3

client = boto3.client("ec2")

response = client.start_instances(
    InstanceIds=[
        'i-01ac16b5251c12e2e',
    ]
)
