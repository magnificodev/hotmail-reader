# 🔐 HƯỚNG DẪN LẤY REFRESH TOKEN MỚI VỚI IMAP SCOPE

## ⚠️ Vấn đề hiện tại

Credential string của bạn có refresh token KHÔNG có quyền IMAP, nên không thể đọc email qua OAuth.

```
tiffanycascadecspss07567@hotmail.com dwkurmomxs9595|M.C534_BAY...$$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
```

**Kết quả test:**
- ✅ Token exchange: THÀNH CÔNG
- ❌ IMAP authentication: THẤT BẠI (AUTHENTICATE failed)

**Nguyên nhân:** Refresh token thiếu scope `IMAP.AccessAsUser.All`

---

## 🎯 Giải pháp: Lấy token mới

### Bước 1: Đảm bảo backend đang chạy

```bash
cd /d/Workspace/beesmart/hotmail-reader
source api/.venv/Scripts/activate
python -m uvicorn api.main:app --reload --port 8000
```

**Kiểm tra:** Mở http://localhost:8000/health - phải thấy `{"status":"ok"}`

### Bước 2: Mở OAuth Authorization URL

Có 2 cách:

**Cách 1: Dùng script tự động**
```bash
python oauth_flow.py
```

**Cách 2: Mở thủ công trong browser**
```
http://localhost:8000/oauth/authorize
```

### Bước 3: Đăng nhập Microsoft

1. Browser sẽ chuyển đến trang đăng nhập Microsoft
2. Đăng nhập bằng tài khoản: **tiffanycascadecspss07567@hotmail.com**
3. Microsoft sẽ hỏi bạn có đồng ý cho app truy cập IMAP không
4. Nhấn **Accept/Chấp nhận**

### Bước 4: Lấy credential string mới

Sau khi accept, browser sẽ redirect về `http://localhost:8000/oauth/callback` và hiển thị JSON:

```json
{
  "credString": "||M.C534_BAY.0.U.-NewRefreshToken...$$|9e5f94bc-e8a4-4e73-b8be-63364c29d753"
}
```

**⚠️ Lưu ý:** 
- CredString có thể bắt đầu bằng `||` (không có email ở đầu)
- Đây là bình thường, chúng ta sẽ thêm email vào

### Bước 5: Test credential string mới

```bash
python test_new_cred.py
```

Nhập credential string khi được hỏi. Script sẽ:
1. ✅ Parse credential
2. ✅ Exchange refresh token
3. ✅ Test IMAP connection
4. ✅ Fetch một email mẫu

Nếu tất cả pass → **CREDENTIAL MỚI HOẠT ĐỘNG!** 🎉

### Bước 6: Sử dụng credential mới

Format đúng cho app:
```
tiffanycascadecspss07567@hotmail.com||NEW_REFRESH_TOKEN|9e5f94bc-e8a4-4e73-b8be-63364c29d753
```

Thay `NEW_REFRESH_TOKEN` bằng token vừa lấy được.

---

## 🔧 Khắc phục sự cố

### ❌ Lỗi: "CLIENT_ID required"

**Nguyên nhân:** File `api/.env` thiếu CLIENT_ID

**Giải pháp:**
```bash
echo 'CLIENT_ID=9e5f94bc-e8a4-4e73-b8be-63364c29d753' >> api/.env
```

### ❌ Lỗi: "state_not_found_or_expired"

**Nguyên nhân:** Quá lâu giữa authorize và callback (>600s)

**Giải pháp:** Làm lại từ đầu, authorize và login nhanh hơn

### ❌ Lỗi: "AUTHENTICATE failed" (sau khi có token mới)

**Nguyên nhân có thể:**

1. **Azure app chưa có permission IMAP**
   - Vào Azure Portal
   - Tìm app `9e5f94bc-e8a4-4e73-b8be-63364c29d753`
   - Thêm API Permission: `Office 365 Outlook API` → `IMAP.AccessAsUser.All`
   - Grant admin consent

2. **Account type không hỗ trợ OAuth IMAP**
   - Personal Microsoft account (hotmail.com) có thể không hỗ trợ
   - Chỉ Office 365 / Outlook.com (Azure AD) mới hỗ trợ đầy đủ
   
3. **IMAP chưa được bật**
   - Vào Outlook Settings → Mail → Sync email
   - Bật "Let devices and apps use IMAP"

### 🔄 Plan B: Dùng Password

Nếu OAuth không hoạt động, thử dùng App Password:

1. Bật IMAP trong Outlook settings
2. Bật 2FA trong Microsoft account
3. Tạo App Password tại: https://account.microsoft.com/security
4. Dùng format: `email|app_password||`

---

## 📝 Files đã tạo

- `oauth_flow.py` - Script mở OAuth flow
- `test_new_cred.py` - Test credential mới
- `simple_test.py` - Test tổng hợp
- `debug_token.py` - Debug token và scope
- `test_password.py` - Test password auth
- `analyze_cred.js` - Phân tích format

---

## 📞 Next Steps

Sau khi có credential string mới:

1. Test bằng `test_new_cred.py`
2. Nếu pass → Update vào app
3. Nếu fail → Check Azure app permissions
4. Vẫn fail → Dùng Plan B (password)

**Hiện tại backend đang chạy, bạn có thể mở:**
👉 http://localhost:8000/oauth/authorize
