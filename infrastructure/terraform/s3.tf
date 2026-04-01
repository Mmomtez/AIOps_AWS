resource "aws_s3_bucket" "aiops_data_lake" {
  bucket        = local.bucket_name
  force_destroy = true
}
resource "aws_s3_bucket_versioning" "aiops_versioning" {
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_public_access_block" "aiops_public_block" {
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_object" "folder_logs" {
  bucket  = aws_s3_bucket.aiops_data_lake.id
  key     = "logs/.keep"
  content = "logs folder"
}
