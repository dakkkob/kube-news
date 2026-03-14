#!/bin/bash
set -euo pipefail

# Log everything to a file for debugging
exec > /var/log/kube-news-setup.log 2>&1

echo "=== kube-news worker setup ==="

# Add 2GB swap — t3.micro has only 1GB RAM, pip needs more for large wheels
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile swap swap defaults 0 0' >> /etc/fstab

# Install Python 3.11 and git
dnf install -y python3.11 python3.11-pip git

# Create app user
useradd -m -s /bin/bash kubenews

# Clone the repo and install
cd /home/kubenews
su - kubenews -c "
  git clone https://github.com/${github_org}/${github_repo}.git app || \
    mkdir -p app
"

# Create .env with secrets from Terraform
cat > /home/kubenews/app/.env << 'ENVEOF'
AWS_REGION=${aws_region}
S3_BUCKET=${s3_bucket}
DYNAMODB_TABLE=${dynamodb_table}
GITHUB_TOKEN=${github_token}
PREFECT_API_URL=${prefect_api_url}
PREFECT_API_KEY=${prefect_api_key}
HF_API_TOKEN=${hf_api_token}
QDRANT_URL=${qdrant_url}
QDRANT_API_KEY=${qdrant_api_key}
MLFLOW_TRACKING_URI=${mlflow_tracking_uri}
MLFLOW_TRACKING_USERNAME=${mlflow_tracking_username}
MLFLOW_TRACKING_PASSWORD=${mlflow_tracking_password}
ENVEOF

chown kubenews:kubenews /home/kubenews/app/.env
chmod 600 /home/kubenews/app/.env

# Install deps as kubenews user
su - kubenews -c "
  cd ~/app
  python3.11 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  pip install -e '.[ml]'
"

# Create systemd service for Prefect worker
cat > /etc/systemd/system/prefect-worker.service << 'SVCEOF'
[Unit]
Description=Prefect Worker for kube-news
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=kubenews
WorkingDirectory=/home/kubenews/app
EnvironmentFile=/home/kubenews/app/.env
ExecStart=/home/kubenews/app/.venv/bin/python /home/kubenews/app/flows/serve_all.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable prefect-worker
systemctl start prefect-worker

echo "=== kube-news worker setup complete ==="
