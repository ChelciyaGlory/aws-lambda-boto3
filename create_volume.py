import boto3

client = boto3.client("ec2")

response = client.create_volume(
    AvailabilityZone='ap-south-1a',
    Encrypted=True,
    Size=20,
    VolumeType='gp3'
)
