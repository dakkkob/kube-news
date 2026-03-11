output "s3_bucket_name" {
  value = aws_s3_bucket.raw.id
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.main.name
}

output "dynamodb_drift_table_name" {
  value = aws_dynamodb_table.drift_metrics.name
}

output "github_actions_role_arn" {
  value = var.github_org != "" ? aws_iam_role.github_actions[0].arn : "N/A - set github_org variable"
}

output "ec2_instance_id" {
  value = aws_instance.worker.id
}

output "ec2_instance_public_ip" {
  value = aws_instance.worker.public_ip
}
