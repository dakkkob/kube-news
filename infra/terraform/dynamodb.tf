resource "aws_dynamodb_table" "main" {
  name         = var.project_name
  billing_mode = "PAY_PER_REQUEST" # No provisioned capacity = free tier friendly
  hash_key     = "item_id"

  attribute {
    name = "item_id"
    type = "S"
  }

  attribute {
    name = "source"
    type = "S"
  }

  attribute {
    name = "published_at"
    type = "S"
  }

  attribute {
    name = "is_deprecation"
    type = "S" # DynamoDB GSI needs string, store "true"/"false"
  }

  # GSI 1: Query by source, sorted by date
  global_secondary_index {
    name            = "source-published_at-index"
    hash_key        = "source"
    range_key       = "published_at"
    projection_type = "ALL"
  }

  # GSI 2: Query deprecations, sorted by date
  global_secondary_index {
    name            = "deprecation-published_at-index"
    hash_key        = "is_deprecation"
    range_key       = "published_at"
    projection_type = "ALL"
  }

  # TTL: auto-delete items after 2 years to stay within free tier
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# Drift metrics table (Phase 4)
resource "aws_dynamodb_table" "drift_metrics" {
  name         = "${var.project_name}-drift-metrics"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "check_type"
  range_key    = "timestamp"

  attribute {
    name = "check_type"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }
}
