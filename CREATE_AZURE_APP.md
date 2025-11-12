# TẠO AZURE APP MỚI CHO OAUTH IMAP

## Bước 1: Vào Azure Portal

1. Truy cập: https://portal.azure.com
2. Đăng nhập bằng Microsoft account của bạn (có thể dùng chính account Hotmail)

## Bước 2: Tạo App Registration

1. Tìm "Azure Active Directory" trong search bar
2. Chọn "App registrations" từ menu bên trái
3. Click "New registration"

### Điền thông tin:

- **Name**: `Hotmail Reader IMAP` (hoặc tên bạn muốn)
- **Supported account types**: 
  - Chọn: **"Accounts in any organizational directory and personal Microsoft accounts"**
  - Hoặc: **"Personal Microsoft accounts only"**
- **Redirect URI**:
  - Platform: **Web**
  - URI: `http://localhost:8000/oauth/callback`

4. Click "Register"

## Bước 3: Lấy Application (client) ID

1. Sau khi tạo xong, bạn sẽ thấy trang "Overview"
2. Copy **Application (client) ID** - đây là CLIENT_ID mới
3. Ví dụ: `12345678-1234-1234-1234-123456789012`

## Bước 4: Thêm API Permissions

1. Từ menu bên trái, chọn "API permissions"
2. Click "Add a permission"
3. Chọn tab "APIs my organization uses"
4. Tìm và chọn "Office 365 Exchange Online" hoặc "Outlook"
5. Chọn "Delegated permissions"
6. Tìm và check:
   - `IMAP.AccessAsUser.All`
   - (Optional) `offline_access` - nếu chưa có
7. Click "Add permissions"
8. (Optional) Click "Grant admin consent" nếu được yêu cầu

## Bước 5: Cập nhật .env file

Edit file `api/.env`:

```env
CLIENT_ID=YOUR_NEW_CLIENT_ID_HERE
GRAPH_TENANT=consumers
OUTLOOK_SCOPE=offline_access https://outlook.office.com/IMAP.AccessAsUser.All
OAUTH_REDIRECT_URI=http://localhost:8000/oauth/callback
```

Thay `YOUR_NEW_CLIENT_ID_HERE` bằng Application (client) ID vừa copy.

## Bước 6: Restart Backend và Test

```bash
cd /d/Workspace/beesmart/hotmail-reader
source api/.venv/Scripts/activate
python -m uvicorn api.main:app --reload --port 8000
```

Sau đó test OAuth flow:
```bash
python oauth_flow.py
```

## Lưu ý

### Client Secret (Không cần thiết cho personal accounts)

Đối với Personal Microsoft accounts, bạn KHÔNG cần client secret.
Chỉ cần CLIENT_ID là đủ.

Nếu muốn thêm (cho production), làm thêm:
1. "Certificates & secrets" → "New client secret"
2. Copy secret value
3. Thêm vào .env: `GRAPH_CLIENT_SECRET=your_secret`

### Redirect URI cho Production

Nếu deploy lên VPS:
1. Vào app → Authentication → Redirect URIs
2. Add: `http://your-domain.com/oauth/callback`
3. Update .env trên server với domain mới

### Troubleshooting

**ERROR: "Need admin approval"**
→ Vào API permissions → Grant admin consent

**ERROR: "AADSTS65001: The user or administrator has not consented"**
→ Người dùng phải consent lần đầu. Đây là bình thường.

**ERROR: "AADSTS50011: Reply URL mismatch"**
→ Check lại redirect URI trong Azure phải giống 100% với trong .env
