# Lambda function to start/stop EC2 worker on a schedule

# Package the Lambda code
data "archive_file" "ec2_scheduler" {
  type        = "zip"
  source_file = "${path.module}/../lambda/ec2_scheduler.py"
  output_path = "${path.module}/../lambda/ec2_scheduler.zip"
}

# IAM role for Lambda
resource "aws_iam_role" "ec2_scheduler" {
  name = "${var.project_name}-ec2-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "ec2_scheduler" {
  name = "${var.project_name}-ec2-scheduler"
  role = aws_iam_role.ec2_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:StartInstances",
          "ec2:StopInstances",
        ]
        Resource = aws_instance.worker.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      },
    ]
  })
}

# Lambda function
resource "aws_lambda_function" "ec2_scheduler" {
  filename         = data.archive_file.ec2_scheduler.output_path
  source_code_hash = data.archive_file.ec2_scheduler.output_base64sha256
  function_name    = "${var.project_name}-ec2-scheduler"
  role             = aws_iam_role.ec2_scheduler.arn
  handler          = "ec2_scheduler.handler"
  runtime          = "python3.12"
  timeout          = 30

  environment {
    variables = {
      INSTANCE_ID = aws_instance.worker.id
    }
  }
}

# EventBridge: Start EC2 at 05:50 UTC Mon/Wed/Fri
resource "aws_cloudwatch_event_rule" "start_worker" {
  name                = "${var.project_name}-start-worker"
  description         = "Start EC2 worker before pipeline runs"
  schedule_expression = "cron(50 5 ? * MON,WED,FRI *)"
}

resource "aws_cloudwatch_event_target" "start_worker" {
  rule = aws_cloudwatch_event_rule.start_worker.name
  arn  = aws_lambda_function.ec2_scheduler.arn

  input = jsonencode({ action = "start" })
}

resource "aws_lambda_permission" "start_worker" {
  statement_id  = "AllowEventBridgeStart"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ec2_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.start_worker.arn
}

# EventBridge: Stop EC2 at 07:00 UTC Mon/Wed/Fri
resource "aws_cloudwatch_event_rule" "stop_worker" {
  name                = "${var.project_name}-stop-worker"
  description         = "Stop EC2 worker after pipeline completes"
  schedule_expression = "cron(0 7 ? * MON,WED,FRI *)"
}

resource "aws_cloudwatch_event_target" "stop_worker" {
  rule = aws_cloudwatch_event_rule.stop_worker.name
  arn  = aws_lambda_function.ec2_scheduler.arn

  input = jsonencode({ action = "stop" })
}

resource "aws_lambda_permission" "stop_worker" {
  statement_id  = "AllowEventBridgeStop"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ec2_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.stop_worker.arn
}
