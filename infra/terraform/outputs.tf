output "alb_dns_name" {
  description = "Public DNS name of the ALB."
  value       = aws_lb.this.dns_name
}

output "ecr_core_repository_url" {
  description = "Push goderash-core images here."
  value       = aws_ecr_repository.core.repository_url
}

output "ecr_dashboard_repository_url" {
  description = "Push goderash-dashboard images here."
  value       = aws_ecr_repository.dashboard.repository_url
}

output "rds_endpoint" {
  description = "Postgres endpoint (private)."
  value       = aws_db_instance.this.address
}

output "redis_endpoint" {
  description = "Redis endpoint (private)."
  value       = aws_elasticache_cluster.this.cache_nodes[0].address
}

output "secret_arn" {
  description = "Secrets Manager ARN holding JWT_SECRET, ADMIN_API_KEY, DATABASE_URL, REDIS_URL."
  value       = aws_secretsmanager_secret.app.arn
}
