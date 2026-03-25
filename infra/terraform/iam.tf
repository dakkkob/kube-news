# GitHub Actions OIDC provider
resource "aws_iam_openid_connect_provider" "github" {
  count = var.github_org != "" ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# IAM role for GitHub Actions (assumes OIDC)
resource "aws_iam_role" "github_actions" {
  count = var.github_org != "" ? 1 : 0

  name = "${var.project_name}-github-actions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github[0].arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:*"
          }
        }
      }
    ]
  })
}

# Policy: S3 + DynamoDB access for the pipeline
resource "aws_iam_policy" "pipeline_access" {
  name = "${var.project_name}-pipeline-access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.raw.arn,
          "${aws_s3_bucket.raw.arn}/*",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem",
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
          aws_dynamodb_table.drift_metrics.arn,
        ]
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "github_actions_pipeline" {
  count = var.github_org != "" ? 1 : 0

  role       = aws_iam_role.github_actions[0].name
  policy_arn = aws_iam_policy.pipeline_access.arn
}

# Read-only IAM user for Streamlit Cloud
resource "aws_iam_user" "streamlit" {
  name = "${var.project_name}-streamlit"
}

resource "aws_iam_policy" "streamlit_readonly" {
  name = "${var.project_name}-streamlit-readonly"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
        ]
        Resource = "${aws_s3_bucket.raw.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
          aws_dynamodb_table.drift_metrics.arn,
        ]
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "streamlit_readonly" {
  user       = aws_iam_user.streamlit.name
  policy_arn = aws_iam_policy.streamlit_readonly.arn
}

resource "aws_iam_access_key" "streamlit" {
  user = aws_iam_user.streamlit.name
}
