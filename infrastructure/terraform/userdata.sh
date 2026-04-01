#!/bin/bash
# EC2 first-boot setup script for AIOps project

# Update system
yum update -y

# Install Python and Git
yum install -y python3 python3-pip git

# Install CloudWatch Agent
yum install -y amazon-cloudwatch-agent

# Fetch CloudWatch agent config from SSM and start it
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c ssm:${cw_config_param} \
  -s

# Create log directories for AIOps agents
mkdir -p /var/log/aiops
touch /var/log/aiops/application.log
touch /var/log/aiops/monitoring-agent.log
touch /var/log/aiops/anomaly-agent.log

# Write environment config for Python code to read
mkdir -p /opt/aiops
cat > /opt/aiops/.env << EOF
AWS_REGION=${aws_region}
S3_BUCKET_NAME=${s3_bucket_name}
ENVIRONMENT=${environment}
EOF