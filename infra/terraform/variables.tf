variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-1"
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
