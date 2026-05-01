# Goderash on AWS — Terraform skeleton

Single-region AWS deployment using ECS Fargate + RDS Postgres + ElastiCache
Redis + ECR. **Skeleton only** — review every resource before applying.

## What this provisions

| Resource | Purpose |
|----------|---------|
| VPC + public/private subnets | Network isolation across two AZs |
| ECR repositories | `goderash-core`, `goderash-dashboard` images |
| RDS Postgres 16 | Single-AZ db.t4g.small (bump for prod) |
| ElastiCache Redis 7 | cache.t4g.micro single node |
| ECS Fargate cluster + services | `core` (2 tasks) + `dashboard` (2 tasks) |
| ALB + target groups | TLS termination, /health checks |
| Secrets Manager entries | `JWT_SECRET`, `ADMIN_API_KEY` |

## Layout

```
infra/terraform/
├── README.md
├── versions.tf          # required providers + minimum Terraform
├── variables.tf         # all knobs (region, tags, instance sizes)
├── providers.tf         # AWS provider config
├── main.tf              # VPC, ECR, RDS, Redis, ECS, ALB
├── outputs.tf           # ECR URLs, ALB DNS, RDS endpoint
└── terraform.tfvars.example
```

## Apply

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars                 # set region + name + sizes
terraform init
terraform plan
terraform apply
```

## Production checklist

- [ ] Set `db_multi_az = true` and bump `db_instance_class`
- [ ] Set `redis_num_nodes >= 2` and enable automatic failover
- [ ] Move state to a remote backend (S3 + DynamoDB locking)
- [ ] Restrict `alb_ingress_cidrs` from `0.0.0.0/0` to your CIDRs / WAF
- [ ] Attach a real ACM certificate to the ALB listener
- [ ] Enable RDS deletion protection and turn on automated backups
- [ ] Add CloudWatch alarms on ECS service health, RDS CPU, Redis evictions
- [ ] Rotate seed values in Secrets Manager and remove the placeholder
