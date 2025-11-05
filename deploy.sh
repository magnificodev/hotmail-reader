#!/bin/bash

# Hotmail Reader - One-shot Non-Interactive Deployment Script
# Usage:
#   sudo bash deploy.sh
# Optional ENV overrides:
#   DOMAIN=mydomain.com REPO_URL=... SERVICE_USER=www-data APP_DIR=/opt/hotmail-reader sudo -E bash deploy.sh

set -euo pipefail

echo "🚀 Starting one-shot deployment..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Config (overridable by environment)
APP_NAME=${APP_NAME:-"hotmail-reader"}
APP_DIR=${APP_DIR:-"/opt/${APP_NAME}"}
SERVICE_USER=${SERVICE_USER:-"www-data"}
BACKEND_PORT=${BACKEND_PORT:-8000}
DOMAIN=${DOMAIN:-""}
REPO_URL=${REPO_URL:-"https://github.com/magnificodev/hotmail-reader.git"}
GIT_BRANCH=${GIT_BRANCH:-"main"}
AUTO_SSL=${AUTO_SSL:-"0"}
CERTBOT_EMAIL=${CERTBOT_EMAIL:-""}

# Root check
if [ "${EUID}" -ne 0 ]; then
  echo -e "${RED}Please run as root (use sudo)${NC}"; exit 1
fi

echo -e "${GREEN}✓ Running as root${NC}"

# Packages
echo -e "${YELLOW}📦 Installing system packages...${NC}"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl wget git python3 python3-pip python3-venv nginx build-essential ca-certificates

# Node.js 18+
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR=$(node -v | sed 's/v//;s/\..*$//') || true
else
  NODE_MAJOR=0
fi
if [ "${NODE_MAJOR}" -lt 18 ]; then
  echo -e "${YELLOW}Installing Node.js 18...${NC}"
  curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
  apt-get install -y -qq nodejs
fi

echo -e "${GREEN}✓ System ready${NC}"

# Create app dir
mkdir -p "${APP_DIR}"
cd "${APP_DIR}"

# Acquire source code
if [ -d .git ]; then
  echo -e "${YELLOW}📥 Repo detected, pulling latest...${NC}"
  git fetch origin "${GIT_BRANCH}" || true
  git checkout "${GIT_BRANCH}" || true
  git pull --rebase --autostash origin "${GIT_BRANCH}" || true
elif [ -n "${REPO_URL}" ]; then
  echo -e "${YELLOW}📥 Cloning from REPO_URL...${NC}"
  git clone --branch "${GIT_BRANCH}" --single-branch "${REPO_URL}" .
else
  echo -e "${YELLOW}No git repo found and REPO_URL not set. Assuming files already present.${NC}"
fi

# Backend setup
echo -e "${YELLOW}🐍 Setting up backend (FastAPI)...${NC}"
cd "${APP_DIR}/api"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
"${APP_DIR}/api/.venv/bin/pip" -q install --upgrade pip
"${APP_DIR}/api/.venv/bin/pip" -q install -r requirements.txt

# Ensure backend .env populated for production
# Interactive inputs (only ask if values not already provided)
DEF_IP=$(hostname -I | awk '{print $1}')
if [ -z "${DOMAIN}" ]; then
  read -r -p "Domain (để trống dùng IP ${DEF_IP}): " IN_DOMAIN || true
  if [ -n "${IN_DOMAIN}" ]; then DOMAIN=${IN_DOMAIN}; else DOMAIN=${DEF_IP}; fi
fi

if [ "${AUTO_SSL}" != "1" ]; then
  read -r -p "Bật HTTPS với Let's Encrypt? (y/N): " IN_SSL || true
  case "${IN_SSL}" in
    y|Y) AUTO_SSL=1 ;;
    *) AUTO_SSL=0 ;;
  esac
fi

if [ "${AUTO_SSL}" = "1" ] && [ -z "${CERTBOT_EMAIL}" ]; then
  read -r -p "Email cho certbot (khuyến nghị, Enter để bỏ qua): " IN_EMAIL || true
  CERTBOT_EMAIL=${IN_EMAIL:-""}
fi

# OAuth (optional)
USE_OAUTH=${USE_OAUTH:-""}
if [ -z "${USE_OAUTH}" ]; then
  read -r -p "Dùng OAuth CLIENT_ID/SECRET? (y/N): " IN_OAUTH || true
  case "${IN_OAUTH}" in y|Y) USE_OAUTH=1 ;; *) USE_OAUTH=0 ;; esac
fi
if [ "${USE_OAUTH}" = "1" ]; then
  if [ -z "${CLIENT_ID:-}" ]; then read -r -p "CLIENT_ID: " CLIENT_ID || true; fi
  if [ -z "${GRAPH_CLIENT_SECRET:-}" ]; then read -r -p "GRAPH_CLIENT_SECRET (Enter nếu public app): " GRAPH_CLIENT_SECRET || true; fi
  GRAPH_TENANT=${GRAPH_TENANT:-"consumers"}
fi
SCHEME=$([ "${AUTO_SSL}" = "1" ] && echo https || echo http)
UI_ORIGIN_VALUE="${SCHEME}://${DOMAIN}"
OAUTH_REDIRECT_URI_VALUE="${SCHEME}://${DOMAIN}/oauth/callback"
if [ ! -f .env ]; then
  {
    echo "UI_ORIGIN=${UI_ORIGIN_VALUE}"
    echo "NODE_ENV=production"
    echo "OAUTH_REDIRECT_URI=${OAUTH_REDIRECT_URI_VALUE}"
    if [ "${USE_OAUTH}" = "1" ] && [ -n "${CLIENT_ID:-}" ]; then echo "CLIENT_ID=${CLIENT_ID}"; fi
    if [ "${USE_OAUTH}" = "1" ] && [ -n "${GRAPH_CLIENT_SECRET:-}" ]; then echo "GRAPH_CLIENT_SECRET=${GRAPH_CLIENT_SECRET}"; fi
    if [ "${USE_OAUTH}" = "1" ] && [ -n "${GRAPH_TENANT:-}" ]; then echo "GRAPH_TENANT=${GRAPH_TENANT}"; fi
    echo "OUTLOOK_SCOPE=offline_access https://outlook.office.com/IMAP.AccessAsUser.All"
  } > .env
else
  # idempotently ensure required keys
  grep -q '^UI_ORIGIN=' .env || echo "UI_ORIGIN=${UI_ORIGIN_VALUE}" >> .env
  grep -q '^NODE_ENV=' .env || echo "NODE_ENV=production" >> .env
  grep -q '^OAUTH_REDIRECT_URI=' .env || echo "OAUTH_REDIRECT_URI=${OAUTH_REDIRECT_URI_VALUE}" >> .env
  if [ "${USE_OAUTH}" = "1" ] && [ -n "${CLIENT_ID:-}" ] && ! grep -q '^CLIENT_ID=' .env; then echo "CLIENT_ID=${CLIENT_ID}" >> .env; fi
  if [ "${USE_OAUTH}" = "1" ] && [ -n "${GRAPH_CLIENT_SECRET:-}" ] && ! grep -q '^GRAPH_CLIENT_SECRET=' .env; then echo "GRAPH_CLIENT_SECRET=${GRAPH_CLIENT_SECRET}" >> .env; fi
  if [ "${USE_OAUTH}" = "1" ] && [ -n "${GRAPH_TENANT:-}" ] && ! grep -q '^GRAPH_TENANT=' .env; then echo "GRAPH_TENANT=${GRAPH_TENANT}" >> .env; fi
fi

echo -e "${GREEN}✓ Backend ready${NC}"

# systemd service for backend
echo -e "${YELLOW}⚙️  Creating systemd service for API...${NC}"
cat > "/etc/systemd/system/${APP_NAME}-api.service" <<EOF
[Unit]
Description=${APP_NAME} API (Uvicorn)
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/api/.venv/bin"
Environment="PYTHONPATH=${APP_DIR}"
ExecStart=${APP_DIR}/api/.venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port ${BACKEND_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${APP_NAME}-api.service"
systemctl restart "${APP_NAME}-api.service"
echo -e "${GREEN}✓ API service started${NC}"

# Optional: enable swap to avoid OOM during frontend build
SWAP_ENABLE=${SWAP_ENABLE:-"0"}
if [ "${SWAP_ENABLE}" = "1" ] && ! swapon --show | grep -q swapfile; then
  echo -e "${YELLOW}🧠 Enabling 2G swap for build stability...${NC}"
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

# Frontend setup (Next.js static export)
echo -e "${YELLOW}⚛️  Setting up frontend (Next.js)...${NC}"
cd "${APP_DIR}"
export HUSKY=0
# Prefer ci if lock exists, fall back to install on failure (e.g., OOM kill)
if [ -f package-lock.json ]; then
  (npm ci --no-audit --no-fund) || (echo -e "${YELLOW}npm ci failed, falling back to npm install...${NC}" && npm install --no-audit --no-fund)
else
  npm install --no-audit --no-fund
fi
echo "NEXT_PUBLIC_API_URL=/api" > .env.local

# Ensure static export enabled (best-effort, idempotent)
if [ -f next.config.mjs ]; then
  if ! grep -q "output: 'export'" next.config.mjs; then
    sed -i "s|export default nextConfig;|nextConfig.output='export';\nif(!nextConfig.images) nextConfig.images={};\nnextConfig.images.unoptimized=true;\n\nexport default nextConfig;|" next.config.mjs || true
  fi
fi

echo -e "${YELLOW}🔨 Building frontend...${NC}"
if ! npm run -s build; then
  echo -e "${RED}Frontend build failed. Continuing to configure API and Nginx. UI may be unavailable.${NC}"
fi
echo -e "${YELLOW}📤 Exporting static site...${NC}"
if ! npx --yes next export; then
  echo -e "${YELLOW}Export failed; ensuring out/ exists so Nginx still starts.${NC}"
  mkdir -p "${APP_DIR}/out"
  echo "<html><body><h1>Build pending</h1></body></html>" > "${APP_DIR}/out/index.html"
fi
mkdir -p "${APP_DIR}/out"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}/out"
chmod -R 755 "${APP_DIR}/out"

# Nginx config
echo -e "${YELLOW}🌐 Configuring Nginx...${NC}"
cat > "/etc/nginx/sites-available/${APP_NAME}" <<EOF
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static frontend
    root ${APP_DIR}/out;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF

ln -sf "/etc/nginx/sites-available/${APP_NAME}" "/etc/nginx/sites-enabled/${APP_NAME}"
rm -f /etc/nginx/sites-enabled/default || true
nginx -t
systemctl restart nginx
echo -e "${GREEN}✓ Nginx configured${NC}"

# Optional: Automatic SSL (Let's Encrypt) if DOMAIN provided and AUTO_SSL=1
if [ "${AUTO_SSL}" = "1" ] && [ -n "${DOMAIN}" ]; then
  echo -e "${YELLOW}🔐 Enabling HTTPS with Let's Encrypt...${NC}"
  apt-get install -y -qq certbot python3-certbot-nginx || true
  if [ -n "${CERTBOT_EMAIL}" ]; then
    certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "${CERTBOT_EMAIL}" || true
  else
    certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos --register-unsafely-without-email || true
  fi
  systemctl reload nginx || true
fi

# Permissions
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
chmod -R 755 "${APP_DIR}"

echo ""
echo -e "${GREEN}✅ Deployment completed${NC}"
echo -e "${GREEN}App URL:${NC} http://${DOMAIN}"
echo -e "${GREEN}API URL (direct):${NC} http://${DOMAIN}:${BACKEND_PORT}"
echo ""
echo -e "${YELLOW}Tip:${NC} Auto SSL: set AUTO_SSL=1 CERTBOT_EMAIL=you@example.com in the deploy command"


