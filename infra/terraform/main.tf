terraform {
  required_version = ">= 1.5.0"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

output "deployment_profile" {
  value = {
    environment = var.environment
    region      = var.region
    service     = "writing-agent"
  }
}
