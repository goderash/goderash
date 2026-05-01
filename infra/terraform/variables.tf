variable "name" {
  description = "Name prefix for all resources (e.g. 'goderash-prod')."
  type        = string
  default     = "goderash"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Tags applied to every taggable resource."
  type        = map(string)
  default = {
    Project   = "goderash"
    ManagedBy = "terraform"
  }
}

# ---- network ----

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.30.0.0/16"
}

variable "alb_ingress_cidrs" {
  description = "CIDR blocks allowed to reach the ALB. Tighten before production."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ---- database ----

variable "db_instance_class" {
  description = "RDS instance class for Postgres."
  type        = string
  default     = "db.t4g.small"
}

variable "db_allocated_storage_gb" {
  description = "RDS storage in GiB."
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = "Multi-AZ RDS — turn on for production."
  type        = bool
  default     = false
}

# ---- redis ----

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "redis_num_nodes" {
  description = "Number of cache nodes."
  type        = number
  default     = 1
}

# ---- ecs ----

variable "core_image" {
  description = "ECR image URI (with tag) for goderash-core."
  type        = string
  default     = ""
}

variable "dashboard_image" {
  description = "ECR image URI (with tag) for goderash-dashboard."
  type        = string
  default     = ""
}

variable "core_desired_count" {
  description = "Number of goderash-core Fargate tasks."
  type        = number
  default     = 2
}

variable "dashboard_desired_count" {
  description = "Number of goderash-dashboard Fargate tasks."
  type        = number
  default     = 2
}
