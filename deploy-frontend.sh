#!/bin/bash

# Frontend deployment script (for static export or npm start)
# Usage: sudo bash deploy-frontend.sh

set -e

APP_NAME="hotmail-reader"
APP_DIR="/opt/${APP_NAME}"
SERVICE_USER="www-data"
FRONTEND_PORT=3000

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

cd ${APP_DIR}

echo "⚛️  Deploying frontend..."

# Option 1: Static Export (recommended)
echo "Building static export..."
npm run build

# Setup Nginx for static files
read -p "Enter your domain (or press Enter to use IP): " DOMAIN
if [ -z "$DOMAIN" ]; then
    DOMAIN="$(hostname -I | awk '{print $1}')"
fi

cat > /etc/nginx/sites-available/${APP_NAME}-frontend << EOF
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};
    root ${APP_DIR}/out;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/${APP_NAME}-frontend /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx

echo "✅ Frontend deployed at http://${DOMAIN}"

