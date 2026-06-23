resource "aws_cloudwatch_log_group" "application_logs" {
  name              = "/aiops/${var.environment}/application"
  retention_in_days = 30
}
resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "aiops-high-cpu-dev"
  metric_name         = "CPUUtilization"
  threshold           = 80.0
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  period              = 120
}
resource "aws_ssm_parameter" "cloudwatch_agent_config" {
  name  = "/aiops/dev/cloudwatch-agent-config"
  value = jsonencode({ ... })
}