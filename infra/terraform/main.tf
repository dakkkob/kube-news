terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # After first apply, uncomment to use S3 backend:
  # backend "s3" {
  #   bucket = "kube-news-tfstate"
  #   key    = "terraform.tfstate"
  #   region = var.aws_region
  # }
}

provider "aws" {
  region = var.aws_region
}
