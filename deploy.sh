#!/bin/bash

# Hotmail Reader - Auto Deployment Script for VPS
# Usage: sudo bash deploy.sh

set -e  # Exit on error

echo "🚀 Starting Hotmail Reader deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="hotmail-reader"
APP_DIR="/opt/${APP_NAME}"
SERVICE_USER="www-data"
DOMAIN=""  # Set your domain here, e.g., "yourdomain.com"
BACKEND_PORT=8000
FRONTEND_PORT=3000

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Running as root${NC}"

# Update system
echo -e "${YELLOW}📦 Updating system packages...${NC}"
apt-get update -qq
apt-get install -y -qq curl wget git python3 python3-pip python3-venv nodejs npm nginx build-essential

# Check Node.js version
NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt "18" ]; then
    echo -e "${YELLOW}⚠ Node.js version < 18, installing Node.js 18...${NC}"
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt-get install -y -qq nodejs
fi

echo -e "${GREEN}✓ System packages installed${NC}"

# Create app directory
echo -e "${YELLOW}📁 Creating application directory...${NC}"
mkdir -p ${APP_DIR}
cd ${APP_DIR}

# Clone repository (for initial deployment only)
if [ -d ".git" ]; then
    echo -e "${RED}⚠ Repository already exists in ${APP_DIR}${NC}"
    echo -e "${YELLOW}This script is for initial deployment only.${NC}"
    echo -e "${YELLOW}To update, use: cd ${APP_DIR} && git pull origin main${NC}"
    exit 1
fi

echo -e "${YELLOW}📥 Cloning repository...${NC}"
echo -e "${YELLOW}For private repo, use SSH URL: git@github.com:username/hotmail-reader.git${NC}"
echo -e "${YELLOW}Or use HTTPS with token: https://token@github.com/username/hotmail-reader.git${NC}"
read -p "Enter your GitHub repository URL: " REPO_URL

if [ -z "$REPO_URL" ]; then
    echo -e "${RED}Repository URL is required${NC}"
    exit 1
fi

git clone ${REPO_URL} .

echo -e "${GREEN}✓ Repository cloned${NC}"

# Setup Backend
echo -e "${YELLOW}🐍 Setting up Python backend...${NC}"
cd ${APP_DIR}/api

# Create virtual environment
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Activate and install dependencies
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo -e "${GREEN}✓ Backend dependencies installed${NC}"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠ Backend .env file not found. Creating template...${NC}"
    cat > .env << EOF
# Required for production
UI_ORIGIN=http://your-domain-or-ip
NODE_ENV=production

# Optional - Only needed if using OAuth flow (/oauth/authorize)
# CLIENT_ID=your_client_id_here
# OAUTH_REDIRECT_URI=http://your-domain-or-ip:8000/oauth/callback

# Optional - Defaults are usually fine
# GRAPH_TENANT=consumers
# OUTLOOK_SCOPE=offline_access https://outlook.office.com/IMAP.AccessAsUser.All
EOF
    echo -e "${RED}⚠ Please edit ${APP_DIR}/api/.env with your actual values!${NC}"
    echo -e "${YELLOW}Minimum required: UI_ORIGIN and NODE_ENV=production${NC}"
fi

# Setup Frontend
echo -e "${YELLOW}⚛️  Setting up Next.js frontend...${NC}"
cd ${APP_DIR}

# Install dependencies
echo -e "${YELLOW}📦 Installing frontend dependencies...${NC}"
npm install --production=false

# Build frontend
echo -e "${YELLOW}🔨 Building frontend...${NC}"
npm run build

echo -e "${GREEN}✓ Frontend built successfully${NC}"

# Create systemd service for backend
echo -e "${YELLOW}⚙️  Creating systemd service...${NC}"
cat > /etc/systemd/system/${APP_NAME}-api.service << EOF
[Unit]
Description=Hotmail Reader API Service
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}/api
Environment="PATH=${APP_DIR}/api/.venv/bin"
ExecStart=${APP_DIR}/api/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port ${BACKEND_PORT}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl daemon-reload
systemctl enable ${APP_NAME}-api.service
systemctl restart ${APP_NAME}-api.service

echo -e "${GREEN}✓ Backend service started${NC}"

# Setup Nginx
echo -e "${YELLOW}🌐 Configuring Nginx...${NC}"

# Ask for domain
if [ -z "$DOMAIN" ]; then
    read -p "Enter your domain (or press Enter to use IP): " DOMAIN
fi

if [ -z "$DOMAIN" ]; then
    DOMAIN="$(hostname -I | awk '{print $1}')"
    echo -e "${YELLOW}Using IP: ${DOMAIN}${NC}"
fi

# Create Nginx config
cat > /etc/nginx/sites-available/${APP_NAME} << EOF
# Backend API
server {
    listen 80;
    server_name api.${DOMAIN} ${DOMAIN};

    # API endpoints
    location / {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }
}

# Frontend (if using npm start)
# server {
#     listen 80;
#     server_name ${DOMAIN} www.${DOMAIN};
#     root ${APP_DIR}/out;
#     index index.html;
#
#     location / {
#         try_files \$uri \$uri/ /index.html;
#     }
#
#     location /api {
#         proxy_pass http://127.0.0.1:${BACKEND_PORT};
#         proxy_http_version 1.1;
#         proxy_set_header Host \$host;
#         proxy_set_header X-Real-IP \$remote_addr;
#         proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
#     }
# }
EOF

# Enable site
ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test Nginx config
nginx -t

# Restart Nginx
systemctl restart nginx

echo -e "${GREEN}✓ Nginx configured${NC}"

# Set permissions
echo -e "${YELLOW}🔐 Setting permissions...${NC}"
chown -R ${SERVICE_USER}:${SERVICE_USER} ${APP_DIR}
chmod -R 755 ${APP_DIR}

echo -e "${GREEN}✓ Permissions set${NC}"

# Summary
echo -e "\n${GREEN}✅ Deployment completed successfully!${NC}\n"
echo -e "${GREEN}Backend API:${NC} http://${DOMAIN}:${BACKEND_PORT}"
echo -e "${GREEN}Nginx Proxy:${NC} http://api.${DOMAIN}"
echo -e "${GREEN}Frontend:${NC} Static files in ${APP_DIR}/out"
echo -e "\n${YELLOW}⚠ IMPORTANT - Next steps:${NC}"
echo -e "1. Edit ${APP_DIR}/api/.env:"
echo -e "   - Set UI_ORIGIN to your actual domain/IP"
echo -e "   - Set NODE_ENV=production"
echo -e "   - (Optional) Add CLIENT_ID if using OAuth flow"
echo -e ""
echo -e "2. Restart backend after editing .env:"
echo -e "   sudo systemctl restart ${APP_NAME}-api"
echo -e ""
echo -e "3. Check service status:"
echo -e "   sudo systemctl status ${APP_NAME}-api"
echo -e "   sudo journalctl -u ${APP_NAME}-api -f"
echo -e ""
echo -e "${YELLOW}To setup frontend with Nginx:${NC}"
echo -e "Create Nginx config for ${APP_DIR}/out directory"
echo -e ""
echo -e "${YELLOW}For SSL (Let's Encrypt):${NC}"
echo -e "sudo apt-get install certbot python3-certbot-nginx"
echo -e "sudo certbot --nginx -d ${DOMAIN} -d api.${DOMAIN}"

