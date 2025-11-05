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

**Ví dụ file `api/.env`:**
```env
CLIENT_ID=your_client_id
GRAPH_CLIENT_SECRET=your_client_secret
UI_ORIGIN=http://localhost:3000
NODE_ENV=development
```

### Frontend (`.env` - optional)
- `NEXT_PUBLIC_API_URL`: Backend API URL (default: http://localhost:8000)

Chỉ cần tạo file này nếu backend không chạy ở port 8000 mặc định.

## Ghi chú
- Không log secrets. Không commit `.env`.
- OTP regex mặc định: 6 chữ số độc lập.
- Token cache được cleanup tự động.
- CORS hỗ trợ multiple origins (comma-separated).

