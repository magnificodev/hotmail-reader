#!/bin/bash

# Quick update script for VPS
# Usage: sudo bash update-vps.sh

set -e

APP_NAME="hotmail-reader"
APP_DIR="/opt/${APP_NAME}"

if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

echo "🔄 Updating Hotmail Reader on VPS..."

cd ${APP_DIR}

# Pull latest code
echo "📥 Pulling latest code..."
git pull origin main

# Update backend dependencies (if needed)
echo "📦 Updating backend dependencies..."
cd ${APP_DIR}/api
source .venv/bin/activate
pip install -r requirements.txt -q

# Update frontend dependencies and build
echo "📦 Updating frontend dependencies..."
cd ${APP_DIR}
npm install --production=false

echo "🔨 Building frontend..."
npm run build

# Restart services
echo "🔄 Restarting services..."
systemctl restart ${APP_NAME}-api.service
systemctl restart nginx

echo "✅ Update completed!"
echo ""
echo "Check status:"
echo "  sudo systemctl status ${APP_NAME}-api"
echo "  sudo journalctl -u ${APP_NAME}-api -f"

