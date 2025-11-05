# Hotmail Reader (Next.js UI + FastAPI API)

## Chạy nhanh (DEV)

### 1) Backend (Python FastAPI)
```bash
cd api
python -m venv .venv
# Windows PowerShell:
. .venv/Scripts/Activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt

# Tạo file .env và cấu hình (xem Environment Variables section bên dưới)
# Tạo file api/.env với các biến môi trường cần thiết

uvicorn api.main:app --reload --port 8000
```

Endpoints:
- POST http://localhost:8000/messages
- POST http://localhost:8000/otp
- POST http://localhost:8000/message
- GET  http://localhost:8000/dev/cred (chỉ khi NODE_ENV=development)
- GET  http://localhost:8000/oauth/authorize
- GET  http://localhost:8000/oauth/callback
- GET  http://localhost:8000/health

### 2) Frontend (Next.js)
```bash
npm install
npm run dev
```

**Lưu ý:** Nếu backend chạy ở port khác 8000, tạo file `.env` ở root với:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```
UI gọi API theo `NEXT_PUBLIC_API_URL` (mặc định: http://localhost:8000)

## Định dạng chuỗi đầu vào
`email|password|refresh_token|client_id`
- Dùng OAuth (khuyến nghị): `email||<refresh_token>|<client_id>`
- Dùng IMAP: `email|<password>||`

## Environment Variables

### Backend (`api/.env`)
- `CLIENT_ID` hoặc `GRAPH_CLIENT_ID`: OAuth client ID
- `GRAPH_CLIENT_SECRET`: OAuth client secret (optional)
- `GRAPH_TENANT`: Tenant ID (default: "consumers")
- `UI_ORIGIN`: CORS allowed origins (comma-separated)
- `NODE_ENV`: Set to "development" to enable dev endpoints
- `TEST_CRED_STRING`: Test credentials (development only)
 - `OAUTH_REDIRECT_URI`: URL callback cho OAuth (vd: `http://your-domain.com/oauth/callback`)
 - `OUTLOOK_SCOPE`: Scope cho Outlook IMAP (mặc định `offline_access https://outlook.office.com/IMAP.AccessAsUser.All`)

**Ví dụ file `api/.env`:**
```env
CLIENT_ID=your_client_id
GRAPH_CLIENT_SECRET=your_client_secret
UI_ORIGIN=http://localhost:3000
NODE_ENV=development
OAUTH_REDIRECT_URI=http://localhost:8000/oauth/callback
OUTLOOK_SCOPE=offline_access https://outlook.office.com/IMAP.AccessAsUser.All
```

### Frontend (`.env` - optional)
- `NEXT_PUBLIC_API_URL`: Backend API URL (default: http://localhost:8000)

Chỉ cần tạo file này nếu backend không chạy ở port 8000 mặc định.

## Deploy lên VPS (Production)

Script `deploy.sh` hỗ trợ deploy one-shot: cài đặt hệ thống, build frontend thành static, tạo service backend (systemd), và cấu hình Nginx reverse proxy `/api`.

### Các bước
1. SSH vào VPS: `ssh user@your-vps-ip`
2. Đảm bảo có `git` và quyền `sudo`.
3. Tải repo hoặc chỉ cần tải `deploy.sh` vào VPS.
4. Chỉnh các biến đầu file trong `deploy.sh` (tối thiểu `DOMAIN`), hoặc export ENV trước khi chạy.
5. Chạy: `sudo bash deploy.sh`
6. Kiểm tra service: `sudo systemctl status hotmail-reader-api`

### Cấu hình ENV Production
- File: `/opt/hotmail-reader/api/.env`
- Giá trị gợi ý:
```env
UI_ORIGIN=http://your-domain.com
NODE_ENV=production
OAUTH_REDIRECT_URI=http://your-domain.com/oauth/callback
# Nếu dùng OAuth
CLIENT_ID=your_client_id
GRAPH_CLIENT_SECRET=your_client_secret
# Tùy chọn
GRAPH_TENANT=consumers
OUTLOOK_SCOPE=offline_access https://outlook.office.com/IMAP.AccessAsUser.All
```

### Nginx và SSL
- Nginx serve static từ `out/` (Next.js export) và proxy `/api` → FastAPI (port 8000).
- Cấp SSL (Let's Encrypt):
```bash
sudo apt-get install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

### Logs & quản trị
- Backend: `sudo journalctl -u hotmail-reader-api -f`
- Restart backend: `sudo systemctl restart hotmail-reader-api`
- Kiểm tra Nginx: `sudo nginx -t && sudo systemctl restart nginx`

## Ghi chú
- Không log secrets. Không commit `.env`.
- OTP regex mặc định: 6 chữ số độc lập.
- Token cache được cleanup tự động.
- CORS hỗ trợ multiple origins (comma-separated).

## Ví dụ gọi API (cURL)

### Lấy danh sách email
```bash
curl -X POST http://localhost:8000/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "credString": "email||<refresh_token>|<client_id>",
    "from_": "no-reply@service.com",
    "page_size": 20,
    "include_body": false
  }'
```

### Trích xuất OTP gần nhất
```bash
curl -X POST http://localhost:8000/otp \
  -H 'Content-Type: application/json' \
  -d '{
    "credString": "email||<refresh_token>|<client_id>",
    "from_": "no-reply@service.com",
    "regex": "(?<!\\d)\\d{6}(?!\\d)",
    "time_window_minutes": 10
  }'
```

### Lấy nội dung email theo UID
```bash
curl -X POST http://localhost:8000/message \
  -H 'Content-Type: application/json' \
  -d '{
    "credString": "email||<refresh_token>|<client_id>",
    "id": "12345"
  }'
```

## Troubleshooting
- 502/404 trên UI: kiểm tra Nginx config và thư mục `out/` đã sinh sau `next export`.
- CORS lỗi: `UI_ORIGIN` cần chứa domain thực tế (có scheme), phân tách bằng dấu phẩy nếu nhiều origin.
- OAuth callback lỗi: đảm bảo `OAUTH_REDIRECT_URI` trùng tuyệt đối với cấu hình app và URL thực tế.
- Backend không chạy: xem logs `journalctl -u hotmail-reader-api -f`, kiểm tra `api/.venv` và `requirements.txt` đã cài.

