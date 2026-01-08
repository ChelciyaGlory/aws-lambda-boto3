import boto3

client = boto3.client("ec2")

response = client.describe_volumes()

for volume in response['Volumes']:
    print(volume['VolumeId'], volume['VolumeType'])
