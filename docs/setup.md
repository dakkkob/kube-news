# Setup Guide

## Prerequisites

- Python 3.11+
- AWS CLI v2
- Terraform 1.5+
- Git

---

## 1. Create the GitHub repo

```bash
# From the project root
git init
git add .
git commit -m "Initial commit: Phase 1 scaffold"

# Create repo on GitHub (public is fine — .env is gitignored)
gh repo create kube-news --public --source=. --push
```

---

## 2. Get your API keys

### GitHub Personal Access Token (free)

1. Go to https://github.com/settings/tokens?type=beta
2. Click **Generate new token** (fine-grained)
3. Name: `kube-news`, Expiration: 90 days
4. Repository access: **Public repositories (read-only)** — that's all we need
5. Copy the token (`github_pat_...`)

> Without a token you get 60 requests/hour. With one: 5,000/hour.

### AWS Account (free tier)

1. Go to https://aws.amazon.com/free/ and create an account (or use existing)
2. Install AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
3. Create an IAM user for local dev:
   - IAM Console → Users → Create user
   - Name: `kube-news-dev`
   - Attach policies: `AmazonS3FullAccess`, `AmazonDynamoDBFullAccess`
   - Security credentials → Create access key → CLI use case
4. Configure locally:
   ```bash
   aws configure
   # Enter: Access Key ID, Secret Access Key, Region (eu-north-1), Output (json)
   ```

> **Note:** AWS now recommends `aws login` via IAM Identity Center (SSO) instead of
> access keys. That's the right call for teams/orgs, but requires setting up AWS
> Organizations + Identity Center — overkill for a solo free-tier project. Our access
> key is only used locally. In production, EC2 uses an IAM instance profile (no keys)
> and CI uses GitHub OIDC (no keys).

### Prefect Cloud (free tier)

1. Sign up at https://app.prefect.cloud/ (GitHub SSO works)
2. Create a workspace (free tier gives you 3)
3. Get your API key: Profile icon → API Keys → Create
4. Get your API URL from Settings → General → copy the API URL
   - Format: `https://api.prefect.cloud/api/accounts/ACCOUNT_ID/workspaces/WORKSPACE_ID`
5. Login locally:
   ```bash
   prefect cloud login -k YOUR_API_KEY
   ```

### Phase 2 keys (not needed yet)

These are for later — skip them for now:

- **HuggingFace**: https://huggingface.co/settings/tokens (free, for zero-shot classifier)
- **Qdrant Cloud**: https://cloud.qdrant.io/ (free 1GB cluster)
- **DagsHub/MLflow**: https://dagshub.com/ (sign up with GitHub, get token from Settings)
- **OpenAI** (Phase 3): https://platform.openai.com/api-keys

---

## 3. Set up your local environment

```bash
cd kube-news

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Create your .env from the template
cp .env.example .env
# Edit .env with your actual keys:
#   GITHUB_TOKEN=github_pat_...
#   PREFECT_API_URL=https://api.prefect.cloud/...
#   PREFECT_API_KEY=pnu_...
#   AWS_REGION=eu-west-1
#   S3_BUCKET=kube-news-raw
#   DYNAMODB_TABLE=kube-news
```

---

## 4. Run the tests

```bash
# Activate venv if not already
source .venv/bin/activate

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Tests (18 should pass)
pytest -v
```

---

## 5. Deploy AWS infrastructure

```bash
cd infra/terraform

# Create terraform.tfvars from the example
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your Prefect and GitHub credentials

# Initialize Terraform
terraform init

# Preview what will be created
terraform plan

# Deploy (creates S3, DynamoDB, EC2, IAM)
terraform apply
```

This creates:
- S3 bucket: `kube-news-raw` (stores raw JSON items)
- DynamoDB table: `kube-news` (metadata + dedup)
- EC2 t2.micro: Prefect worker (auto-starts via systemd)
- IAM instance profile: EC2 accesses S3/DynamoDB without access keys
- IAM role for GitHub Actions OIDC (no long-lived keys in CI)

---

## 6. Test ingestion locally

```bash
source .venv/bin/activate

# Quick smoke test — fetch RSS without saving to S3
python3 -c "
from src.ingestion.rss_client import fetch_rss
items = fetch_rss('https://kubernetes.io/feed.xml', 'kubernetes-blog')
print(f'Got {len(items)} items')
print(items[0]['title'] if items else 'No items')
"

# Test CVE feed (no auth needed)
python3 -c "
from src.ingestion.cve_client import fetch_k8s_cves
items = fetch_k8s_cves()
print(f'Got {len(items)} CVEs')
"
```

---

## 7. Deploy Prefect flows

```bash
# Create the work pool in Prefect Cloud first
prefect work-pool create kube-news-pool --type process

# Deploy all 4 flows (reads prefect.yaml)
prefect deploy --all
```

This registers the flows with Prefect Cloud on their schedules:
- `ingest-github-releases` — daily at 06:00 UTC
- `ingest-rss-feeds` — daily at 07:00 UTC
- `ingest-k8s-cves` — every 6 hours
- `ingest-endoflife` — daily at 08:00 UTC

---

## 8. Connect to EC2 (if needed)

The EC2 instance auto-starts the Prefect worker via user data script. No SSH key needed — use SSM Session Manager:

```bash
# Connect via AWS CLI (requires Session Manager plugin)
# Install: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html
aws ssm start-session --target INSTANCE_ID --region eu-north-1

# Check the worker is running
sudo systemctl status prefect-worker

# View setup logs
sudo cat /var/log/kube-news-setup.log
```

---

## Security notes

- `.env` is in `.gitignore` — never committed
- `.env.example` has only placeholder values — safe to commit
- GitHub Actions uses OIDC (temporary credentials) — no AWS keys stored in repo
- The GitHub token only needs **public repo read** access
- Making the repo public exposes zero secrets
