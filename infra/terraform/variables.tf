variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-north-1"
}

variable "project_name" {
  description = "Project name, used as prefix for resource names"
  type        = string
  default     = "kube-news"
}

variable "github_org" {
  description = "GitHub org/user for OIDC trust policy"
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "GitHub repo name for OIDC trust policy"
  type        = string
  default     = "kube-news"
}

# EC2 / Prefect worker
variable "prefect_api_url" {
  description = "Prefect Cloud API URL"
  type        = string
  sensitive   = true
}

variable "prefect_api_key" {
  description = "Prefect Cloud API key"
  type        = string
  sensitive   = true
}

variable "github_token" {
  description = "GitHub PAT for higher API rate limits"
  type        = string
  sensitive   = true
}

# Phase 2 — Processing
variable "hf_api_token" {
  description = "HuggingFace API token for zero-shot classification"
  type        = string
  sensitive   = true
  default     = ""
}

variable "qdrant_url" {
  description = "Qdrant Cloud cluster URL"
  type        = string
  sensitive   = true
  default     = ""
}

variable "qdrant_api_key" {
  description = "Qdrant Cloud API key"
  type        = string
  sensitive   = true
  default     = ""
}
