# Hotmail Reader (Next.js UI + FastAPI API)

## Chạy nhanh (DEV)

### 1) Backend (Python FastAPI)
```
cd api
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Tùy chọn: tạo file .env với TEST_CRED_STRING để test nội bộ
# NODE_ENV=development
# TEST_CRED_STRING="email|password|refresh_token|client_id"
uvicorn api.main:app --reload --port 8000
```

Endpoints:
- POST http://localhost:8000/messages
- POST http://localhost:8000/otp
- GET  http://localhost:8000/dev/cred (chỉ khi NODE_ENV=development)

### 2) Frontend (Next.js)
```
npm install
npm run dev
```
UI gọi API http://localhost:8000/...

## Định dạng chuỗi đầu vào
`email|password|refresh_token|client_id`
- Dùng Graph (khuyến nghị): `email||<refresh_token>|<client_id>`
- Dùng IMAP: `email|<password>||`

## Ghi chú
- Không log secrets. Không commit `.env`.
- OTP regex mặc định: 4–8 chữ số độc lập.

