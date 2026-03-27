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
   - Attach policies for **day-to-day use**: `AmazonS3FullAccess`, `AmazonDynamoDBFullAccess`, `AmazonSSMFullAccess`
   - Security credentials → Create access key → CLI use case

   **Before running `terraform apply`**, temporarily add these policies (via the console or an admin user) and remove them after:
   - `AmazonEC2FullAccess` (creates EC2 instances)
   - `IAMFullAccess` (creates Lambda/EC2 IAM roles)
   - `AWSLambda_FullAccess` (creates Lambda functions)
   - `AmazonEventBridgeFullAccess` (creates scheduled rules)
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

### Phase 2 keys (processing + ML)

- **HuggingFace**: https://huggingface.co/settings/tokens (free, for zero-shot classifier)
  - Enable "Make calls to the serverless Inference API" permission
- **Qdrant Cloud**: https://cloud.qdrant.io/ (free 1GB cluster)
  - Create a cluster, get the URL and API key from the dashboard
- **DagsHub/MLflow**: https://dagshub.com/ (sign up with GitHub)
  - Create/connect a repo, get token from Settings → Tokens
  - Tracking URI: `https://dagshub.com/<username>/kube-news.mlflow`

### Phase 3 keys (RAG chat + Streamlit app)

- **OpenAI**: https://platform.openai.com/api-keys (for RAG chat via `gpt-4o-mini`)

---

## 3. Set up your local environment

```bash
cd kube-news

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (pick what you need)
pip install -e ".[dev]"          # linting, testing, type checking
pip install -e ".[ml]"           # Phase 2: classifier, embedder, Qdrant, MLflow
pip install -e ".[app]"          # Phase 3: Streamlit, OpenAI, RAG chat

# Create your .env from the template
cp .env.example .env
# Edit .env with your actual keys:
#   GITHUB_TOKEN=github_pat_...
#   PREFECT_API_URL=https://api.prefect.cloud/...
#   PREFECT_API_KEY=pnu_...
#   AWS_REGION=eu-north-1
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

# Deploy (creates S3, DynamoDB, EC2, Lambda, EventBridge, IAM)
terraform apply
```

This creates:
- S3 bucket: `kube-news-raw` (stores raw JSON items)
- DynamoDB tables: `kube-news` (metadata + dedup), `kube-news-drift-metrics` (Phase 4)
- EC2 t3.small: Prefect worker (auto-starts via systemd, 2GB swap for ML inference)
- Lambda: `kube-news-ec2-scheduler` (starts/stops EC2 on schedule)
- EventBridge rules: start EC2 at 05:50 UTC, stop at 08:00 UTC (Mon/Wed/Fri)
- IAM instance profile: EC2 accesses S3/DynamoDB without access keys
- IAM role for GitHub Actions OIDC (no long-lived keys in CI)
- IAM user: `kube-news-streamlit` with read-only S3/DynamoDB access (for Streamlit Cloud)

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

## 7. Prefect flows

Flows run via `serve()` on EC2 (no work pools needed — Prefect free tier). The systemd
service starts `flows/serve_all.py` on boot automatically.

Schedule (Mon/Wed/Fri UTC, EC2 is started/stopped by Lambda):
- `06:00` — `ingest-github-releases`
- `06:15` — `ingest-rss-feeds`
- `06:30` — `ingest-k8s-cves`
- `06:45` — `ingest-endoflife`
- `07:15` — `process-and-embed` (classify, extract entities, embed to Qdrant, log to MLflow)
- `07:45` — `drift-check` (confidence + embedding drift, triggers retraining if drifted)

To run flows manually on EC2 (requires `AmazonSSMFullAccess` on your `kube-news-dev` user):
```bash
aws ssm start-session --target INSTANCE_ID --region eu-north-1
sudo su - kubenews
cd ~/app && source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
python flows/process_and_embed.py
```

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

## 9. Deploy to Streamlit Community Cloud

1. Push your code to GitHub (the `app/` directory must be in the repo)
2. Go to https://share.streamlit.io and connect your `dakkkob/kube-news` repo
3. Set **Main file path** to `app/streamlit_app.py`
4. In app **Settings → Secrets**, paste the credentials in TOML format:
   ```toml
   OPENAI_API_KEY = "sk-..."
   QDRANT_URL = "https://your-cluster.qdrant.io"
   QDRANT_API_KEY = "..."
   AWS_ACCESS_KEY_ID = "..."       # Use kube-news-streamlit keys (read-only)
   AWS_SECRET_ACCESS_KEY = "..."   # NOT your kube-news-dev keys
   AWS_DEFAULT_REGION = "eu-north-1"
   S3_BUCKET = "kube-news-raw"
   DYNAMODB_TABLE = "kube-news"
   QDRANT_COLLECTION = "kube-news"
   HF_API_TOKEN = "hf_..."         # Zero-shot classifier fallback
   HF_TOKEN = "hf_..."             # Same value — used by transformers library for model downloads
   DRIFT_METRICS_TABLE = "kube-news-drift-metrics"
   ```

   Get the Streamlit IAM credentials after `terraform apply` (outputs are hidden by default):
   ```bash
   terraform output -raw streamlit_aws_access_key_id
   terraform output -raw streamlit_aws_secret_access_key
   ```

5. Click **Deploy**

> The `kube-news-streamlit` IAM user can only read from S3 and query DynamoDB — no
> writes, no deletes, no access to other AWS services. Even if Streamlit Cloud were
> compromised, the blast radius is minimal.

---

## 10. GitHub Actions (automated retraining)

The retraining workflow triggers automatically when drift is detected, or manually.

1. **Enable PR creation:** Settings → Actions → General → check **"Allow GitHub Actions to create and approve pull requests"**
2. **Add repository secrets** (Settings → Secrets and variables → Actions):
   - `AWS_ROLE_ARN` — from `terraform output -raw github_actions_role_arn`
   - `MLFLOW_TRACKING_URI` — `https://dagshub.com/<username>/kube-news.mlflow`
   - `MLFLOW_TRACKING_USERNAME` — your DagsHub username
   - `MLFLOW_TRACKING_PASSWORD` — your DagsHub token
3. **Manual trigger:** `gh workflow run retrain-classifier.yml`
4. **Automated trigger:** The drift-check flow sends a `repository_dispatch` event when drift is detected

The workflow trains a DistilBERT classifier on silver labels, uploads to S3, and opens a PR with metrics. Merge the PR to promote the model.

---

## Security notes

- `.env` is in `.gitignore` — never committed
- `.env.example` has only placeholder values — safe to commit
- GitHub Actions uses OIDC (temporary credentials) — no AWS keys stored in repo
- The GitHub token only needs **public repo read** access
- Streamlit Cloud uses a dedicated read-only IAM user (`kube-news-streamlit`) — not your dev keys
- Streamlit secrets are encrypted at rest and only visible to the app owner
- EC2 uses an IAM instance profile — no access keys on the instance
- Making the repo public exposes zero secrets
