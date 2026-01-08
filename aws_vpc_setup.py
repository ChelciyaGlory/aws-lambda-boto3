# Filename: create_vpc_with_public_private_subnets_idempotent.py

import boto3
from botocore.exceptions import ClientError

# ---------------------------
# Specify region
# ---------------------------
region = "us-west-1"
ec2_client = boto3.client("ec2", region_name=region)

def get_or_create_vpc():
    response = ec2_client.describe_vpcs(
        Filters=[{'Name': 'tag:Name', 'Values': ['vpc-with-igw-nat']}]
    )
    if response['Vpcs']:
        vpc_id = response['Vpcs'][0]['VpcId']
        print(f"Reusing existing VPC: {vpc_id}")
        return vpc_id
    
    response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
    vpc_id = response['Vpc']['VpcId']
    print(f"Created new VPC: {vpc_id}")
    
    ec2_client.create_tags(Resources=[vpc_id], Tags=[{'Key': 'Name', 'Value': 'vpc-with-igw-nat'}])
    ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
    ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
    
    return vpc_id

def get_or_create_internet_gateway(vpc_id):
    response = ec2_client.describe_internet_gateways(
        Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
    )
    if response['InternetGateways']:
        igw_id = response['InternetGateways'][0]['InternetGatewayId']
        print(f"Reusing existing Internet Gateway: {igw_id}")
        return igw_id
    
    igw = ec2_client.create_internet_gateway()
    igw_id = igw['InternetGateway']['InternetGatewayId']
    ec2_client.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    print(f"Created and attached new Internet Gateway: {igw_id}")
    return igw_id

def get_or_create_subnet(vpc_id, cidr_block, tag_name):
    response = ec2_client.describe_subnets(
        Filters=[
            {'Name': 'vpc-id', 'Values': [vpc_id]},
            {'Name': 'cidr-block', 'Values': [cidr_block]}
        ]
    )
    if response['Subnets']:
        subnet_id = response['Subnets'][0]['SubnetId']
        print(f"Reusing existing {tag_name} Subnet: {subnet_id}")
        return subnet_id
    
    subnet = ec2_client.create_subnet(VpcId=vpc_id, CidrBlock=cidr_block)
    subnet_id = subnet['Subnet']['SubnetId']
    ec2_client.create_tags(Resources=[subnet_id], Tags=[{'Key': 'Name', 'Value': tag_name}])
    print(f"Created new {tag_name} Subnet: {subnet_id}")
    return subnet_id

def get_or_create_route_table(vpc_id, tag_name):
    response = ec2_client.describe_route_tables(
        Filters=[
            {'Name': 'vpc-id', 'Values': [vpc_id]},
            {'Name': 'tag:Name', 'Values': [tag_name]}
        ]
    )
    if response['RouteTables']:
        rt_id = response['RouteTables'][0]['RouteTableId']
        print(f"Reusing existing Route Table '{tag_name}': {rt_id}")
        return rt_id
    
    rt = ec2_client.create_route_table(VpcId=vpc_id)
    rt_id = rt['RouteTable']['RouteTableId']
    ec2_client.create_tags(Resources=[rt_id], Tags=[{'Key': 'Name', 'Value': tag_name}])
    print(f"Created new Route Table '{tag_name}': {rt_id}")
    return rt_id

def ensure_route(rt_id, destination, target_id, target_type):
    try:
        if target_type == 'gateway':
            ec2_client.create_route(RouteTableId=rt_id, DestinationCidrBlock=destination, GatewayId=target_id)
        elif target_type == 'nat':
            ec2_client.create_route(RouteTableId=rt_id, DestinationCidrBlock=destination, NatGatewayId=target_id)
        print(f"Route {destination} -> {target_id} added")
    except ClientError as e:
        if e.response['Error']['Code'] == 'RouteAlreadyExists':
            print(f"Route {destination} already exists")
        else:
            raise

def associate_route_table(rt_id, subnet_id):
    try:
        response = ec2_client.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id)
        print(f"Subnet {subnet_id} associated with route table {rt_id}")
        return response['AssociationId']
    except ClientError as e:
        if e.response['Error']['Code'] == 'Resource.AlreadyAssociated':
            print(f"Subnet {subnet_id} is already associated with route table {rt_id}")
        else:
            raise

def enable_public_ip_auto_assign(subnet_id):
    try:
        ec2_client.modify_subnet_attribute(
            SubnetId=subnet_id,
            MapPublicIpOnLaunch={'Value': True}
        )
        print("Auto-assign public IP enabled on public subnet")
    except ClientError as e:
        # This error occurs if it's already enabled — AWS doesn't return a specific code
        print("Auto-assign public IP already enabled or minor error (safe to ignore)")

def get_or_create_nat_gateway(public_subnet_id):
    # Better: look for any NAT in this subnet (including pending/failed, but prefer available)
    response = ec2_client.describe_nat_gateways(
        Filters=[
            {'Name': 'subnet-id', 'Values': [public_subnet_id]},
            {'Name': 'state', 'Values': ['pending', 'available']}
        ]
    )
    
    available = [ng for ng in response['NatGateways'] if ng['State'] == 'available']
    if available:
        nat_id = available[0]['NatGatewayId']
        print(f"Reusing existing available NAT Gateway: {nat_id}")
        return nat_id
    
    pending = [ng for ng in response['NatGateways'] if ng['State'] == 'pending']
    if pending:
        nat_id = pending[0]['NatGatewayId']
        print(f"NAT Gateway already being created: {nat_id}, waiting for it...")
        waiter = ec2_client.get_waiter('nat_gateway_available')
        waiter.wait(NatGatewayIds=[nat_id])
        print("Existing NAT Gateway is now available")
        return nat_id

    # Create new one
    eip = ec2_client.allocate_address(Domain='vpc')
    allocation_id = eip['AllocationId']
    print(f"Allocated new Elastic IP: {allocation_id}")
    
    nat = ec2_client.create_nat_gateway(SubnetId=public_subnet_id, AllocationId=allocation_id)
    nat_id = nat['NatGateway']['NatGatewayId']
    print(f"Creating new NAT Gateway: {nat_id}")
    
    print("Waiting for NAT Gateway to become available (this takes 3-10 minutes)...")
    waiter = ec2_client.get_waiter('nat_gateway_available')
    waiter.wait(NatGatewayIds=[nat_id])
    print("NAT Gateway is now available!")
    
    return nat_id

# ---------------------------
# Main execution
# ---------------------------
print("Starting idempotent VPC setup...\n")

vpc_id = get_or_create_vpc()
igw_id = get_or_create_internet_gateway(vpc_id)

public_subnet_id = get_or_create_subnet(vpc_id, '10.0.1.0/24', 'public-subnet')
private_subnet_id = get_or_create_subnet(vpc_id, '10.0.2.0/24', 'private-subnet')

# Enable auto-assign public IPs for public subnet
enable_public_ip_auto_assign(public_subnet_id)

# Public Route Table
public_rt_id = get_or_create_route_table(vpc_id, 'public-rt')
ensure_route(public_rt_id, '0.0.0.0/0', igw_id, 'gateway')
associate_route_table(public_rt_id, public_subnet_id)

# NAT Gateway
nat_gateway_id = get_or_create_nat_gateway(public_subnet_id)

# Private Route Table
private_rt_id = get_or_create_route_table(vpc_id, 'private-rt')
ensure_route(private_rt_id, '0.0.0.0/0', nat_gateway_id, 'nat')
associate_route_table(private_rt_id, private_subnet_id)

print("\n=== VPC Setup Completed Successfully ===")
print(f"VPC ID: {vpc_id}")
print(f"Public Subnet: {public_subnet_id}")
print(f"Private Subnet: {private_subnet_id}")
print(f"Internet Gateway: {igw_id}")
print(f"NAT Gateway: {nat_gateway_id}")