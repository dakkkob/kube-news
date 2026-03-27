# Latest Amazon Linux 2023 AMI
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Security group: outbound only (SSM Session Manager for access, no SSH needed)
resource "aws_security_group" "worker" {
  name        = "${var.project_name}-worker"
  description = "Prefect worker - outbound only, SSM for access"

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-worker"
  }
}

# IAM instance profile: S3 + DynamoDB + SSM access
resource "aws_iam_role" "ec2_worker" {
  name = "${var.project_name}-ec2-worker"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_pipeline" {
  role       = aws_iam_role.ec2_worker.name
  policy_arn = aws_iam_policy.pipeline_access.arn
}

# SSM managed policy — allows `aws ssm start-session` from your terminal
resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = aws_iam_role.ec2_worker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "worker" {
  name = "${var.project_name}-worker"
  role = aws_iam_role.ec2_worker.name
}

# EC2 t2.micro — Prefect worker
resource "aws_instance" "worker" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = "t3.small"
  iam_instance_profile   = aws_iam_instance_profile.worker.name
  vpc_security_group_ids = [aws_security_group.worker.id]

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    project_name    = var.project_name
    aws_region      = var.aws_region
    prefect_api_url = var.prefect_api_url
    prefect_api_key = var.prefect_api_key
    github_token    = var.github_token
    github_org      = var.github_org
    github_repo     = var.github_repo
    s3_bucket       = aws_s3_bucket.raw.id
    dynamodb_table  = aws_dynamodb_table.main.name
    hf_api_token    = var.hf_api_token
    qdrant_url              = var.qdrant_url
    qdrant_api_key          = var.qdrant_api_key
    mlflow_tracking_uri      = var.mlflow_tracking_uri
    mlflow_tracking_username = var.mlflow_tracking_username
    mlflow_tracking_password = var.mlflow_tracking_password
  })

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  tags = {
    Name = "${var.project_name}-worker"
  }
}
