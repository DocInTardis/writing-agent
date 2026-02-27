# Container + IaC

## Local container run

```bash
docker compose up --build
```

## Terraform skeleton

```bash
cd infra/terraform
terraform init
terraform plan -var="environment=staging" -var="region=us-east-1"
```

This folder is intentionally minimal and acts as the canonical IaC entrypoint for environment-standard deployment.
