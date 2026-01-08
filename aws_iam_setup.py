import boto3

# Create IAM client
client = boto3.client('iam')

# Create IAM User
user_name = 'glory'
client.create_user(UserName=user_name)
print(f"IAM User created: {user_name}")

# Attach Policies
policies = [
    'arn:aws:iam::aws:policy/AmazonEC2FullAccess',
    'arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess',
    'arn:aws:iam::aws:policy/IAMFullAccess'
]

for policy_arn in policies:
    client.attach_user_policy(UserName=user_name, PolicyArn=policy_arn)
    print(f"Attached policy: {policy_arn}")

print("IAM user created and policies attached successfully")

