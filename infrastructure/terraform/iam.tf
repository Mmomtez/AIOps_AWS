resource "aws_iam_role" "ec2_aiops_role" {
  name = "${var.project_name}-ec2-role-${var.environment}"
  
  assume_role_policy = jsonencode({
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}
resource "aws_iam_policy" "cloudwatch_policy" {
  policy = jsonencode({
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:PutLogEvents",
        "cloudwatch:PutMetricData",
        ...
      ]
      Resource = "*"
    }]
  })
}
resource "aws_iam_policy" "s3_policy" {
  policy = jsonencode({
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", ...]
      Resource = [
        aws_s3_bucket.aiops_data_lake.arn,
        "${aws_s3_bucket.aiops_data_lake.arn}/*"
      ]
    }]
  })
}
resource "aws_iam_instance_profile" "ec2_aiops_profile" {
  name = "${var.project_name}-ec2-profile-${var.environment}"
  role = aws_iam_role.ec2_aiops_role.name
}