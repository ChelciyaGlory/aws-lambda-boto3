import boto3

client = boto3.client("s3")

response = client.create_bucket(
    Bucket='boto3-bucket-jan-8th-2026',
    CreateBucketConfiguration={
        'LocationConstraint': 'ap-south-1'
    }
)
