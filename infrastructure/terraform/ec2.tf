resource "aws_security_group" "aiops_sg" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 8000
    to_port     = 8000
    ...
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_instance" "aiops_backend" {
  ami                  = var.ami_id
  instance_type        = var.instance_type
  iam_instance_profile = aws_iam_instance_profile.ec2_aiops_profile.name
  vpc_security_group_ids = [aws_security_group.aiops_sg.id]
  
  user_data = base64encode(templatefile("${path.module}/userdata.sh", {
    aws_region      = var.aws_region
    s3_bucket_name  = aws_s3_bucket.aiops_data_lake.bucket
    cw_config_param = aws_ssm_parameter.cloudwatch_agent_config.name
    environment     = var.environment
  }))
}