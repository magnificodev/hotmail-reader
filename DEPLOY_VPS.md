# Hướng dẫn Deploy lên VPS

## Yêu cầu

- VPS với Ubuntu/Debian
- SSH access
- Root hoặc sudo privileges
- Domain name (optional, có thể dùng IP)

## Cách deploy

### Bước 1: Upload code lên VPS

**Option 1: Clone từ GitHub**
```bash
# SSH vào VPS
ssh user@your-vps-ip

# Clone repository
cd /opt
sudo git clone https://github.com/magnificodev/hotmail-reader.git
cd hotmail-reader
```

**Option 2: Upload file deploy.sh**
```bash
# Upload deploy.sh lên VPS
scp deploy.sh user@your-vps-ip:/tmp/
```

### Bước 2: Chạy script deploy

```bash
# SSH vào VPS
ssh user@your-vps-ip

# Copy script vào thư mục project (nếu chưa có)
cd /opt/hotmail-reader  # hoặc thư mục bạn đã clone

# Cho phép execute
chmod +x deploy.sh

# Chạy script (cần sudo)
sudo bash deploy.sh
```

### Bước 3: Cấu hình Environment Variables

Script sẽ tạo file `.env` template nếu chưa có. Chỉnh sửa:

```bash
sudo nano /opt/hotmail-reader/api/.env
```

Cập nhật các giá trị:
```env
# CLIENT_ID chỉ cần nếu bạn muốn dùng OAuth flow (/oauth/authorize)
# Nếu người dùng chỉ nhập credString vào input, không cần CLIENT_ID
CLIENT_ID=9e5f94bc-e8a4-4e73-b8be-63364c29d753  # Optional nếu không dùng OAuth flow

GRAPH_TENANT=consumers
OUTLOOK_SCOPE=offline_access https://outlook.office.com/IMAP.AccessAsUser.All
UI_ORIGIN=https://yourdomain.com  # hoặc http://your-ip
NODE_ENV=production
OAUTH_REDIRECT_URI=https://api.yourdomain.com/oauth/callback  # Chỉ cần nếu dùng OAuth flow
```

**Lưu ý:**
- `CLIENT_ID` và `OAUTH_REDIRECT_URI` chỉ cần thiết nếu bạn muốn dùng OAuth flow (endpoint `/oauth/authorize`)
- Nếu người dùng đã có `refresh_token` và `client_id`, họ có thể nhập vào input mà không cần OAuth flow
- Trong trường hợp đó, chỉ cần `UI_ORIGIN` và `NODE_ENV=production`

### Bước 4: Restart services

```bash
# Restart backend
sudo systemctl restart hotmail-reader-api

# Restart Nginx
sudo systemctl restart nginx

# Check status
sudo systemctl status hotmail-reader-api
```

### Bước 5: Setup SSL (Let's Encrypt)

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d api.yourdomain.com
```

## Cấu trúc sau khi deploy

```
/opt/hotmail-reader/
├── api/
│   ├── .venv/          # Python virtual environment
│   ├── .env            # Environment variables
│   └── ...
├── out/                # Frontend build (static export)
└── ...
```

## Quản lý services

### Backend API
```bash
# Start
sudo systemctl start hotmail-reader-api

# Stop
sudo systemctl stop hotmail-reader-api

# Restart
sudo systemctl restart hotmail-reader-api

# Status
sudo systemctl status hotmail-reader-api

# Logs
sudo journalctl -u hotmail-reader-api -f
```

### Nginx
```bash
# Restart
sudo systemctl restart nginx

# Test config
sudo nginx -t

# Logs
sudo tail -f /var/log/nginx/error.log
```

## Update code

```bash
cd /opt/hotmail-reader
sudo git pull origin main
cd api
source .venv/bin/activate
pip install -r requirements.txt
cd ..
npm install
npm run build
sudo systemctl restart hotmail-reader-api
sudo systemctl restart nginx
```

## Troubleshooting

### Backend không chạy
```bash
# Check logs
sudo journalctl -u hotmail-reader-api -n 50

# Check port
sudo netstat -tlnp | grep 8000
```

### Frontend không load
```bash
# Check Nginx config
sudo nginx -t

# Check static files
ls -la /opt/hotmail-reader/out
```

### Permission errors
```bash
sudo chown -R www-data:www-data /opt/hotmail-reader
sudo chmod -R 755 /opt/hotmail-reader
```

## Frontend Options

### Option 1: Static Export (Recommended)
- Build: `npm run build` → tạo folder `out/`
- Serve với Nginx (đã config trong script)
- Fast, không cần Node.js runtime

### Option 2: npm start
- Chạy Next.js server
- Cần systemd service cho frontend
- Dynamic rendering

Script mặc định dùng Option 1 (static export).

