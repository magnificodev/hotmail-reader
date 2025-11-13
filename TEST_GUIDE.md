# Test Password-Based Token Refresh

## Đã hoàn thành

✅ **Tính năng password-based OAuth refresh** đã được implement:
- Tự động detect refresh token expired
- Fallback sang password-based OAuth flow
- Lấy tokens mới và retry request

## Commit History

1. **2232b1d** - feat: add password-based OAuth refresh when refresh_token expires
   - Created `api/oauth_refresh.py` với GetOAuth2Token class
   - Updated `get_outlook_access_token()` để handle expired tokens
   - Pass password parameter đến tất cả calls

2. **fd1d7b0** - fix: convert relative imports to absolute imports
   - Fixed ImportError khi run uvicorn directly
   - Changed all relative imports to absolute
   - Added test scripts

## Cách test

### Bước 1: Start server

**Option A - Windows:**
```bash
start_server.bat
```

**Option B - Manual:**
```bash
cd api
.venv/Scripts/activate  # hoặc: source .venv/bin/activate trên Linux/Mac
python -m uvicorn main:app --port 8000
```

### Bước 2: Test API (trong terminal khác)

**Option A - Dùng test script:**
```bash
cd d:/Workspace/beesmart/hotmail-reader
api/.venv/Scripts/python.exe test_api.py
```

**Option B - Dùng curl:**
```bash
curl -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{
    "credString": "TepPalmore9298@hotmail.com|VQW6V64869|M.C505_BAY.0.U.-Cj7wT4ioRiCNsCB5IW4rfxefVRwKqV0NmB8YalQVByjnq3PH2UcUyFiuEMeARSo5aG0AyvAQ0d1iaL2S646z106bt!gDPawQ*pKkEMZb28AATzQS!ONgHT8AN7UQWTSMohBVjoYReap4eM5RyDSwBlydxwULQoUy*uT0yk7eOhAP25EckSCcLMh1G7sFQTZ!RiukRCnnmQLyMcW0QP6sxuXBlsBLQqiYGVkGxosEXjK!BBMHF45FBLmA1YkEOqcYpNJNKOxvr6dvm!1JnkJl9cQYmzLQZVxMs*RoxdKdHQZWpUjFEPx4DJ5t2dK6VA7aQFQpMKyjg0TkLdlQgi0ndWmC!sw5JZocIUY3acmi6pqwVuThC1GQfaJaKWoY2V6Ue!RYyHMn8Btu*3yMyH5C7iuZuMIFWqNV!Gv72cSb9kmE|9e5f94bc-e8a4-4e73-b8be-63364c29d753",
    "page_size": 5
  }'
```

### Bước 3: Check server logs

Server sẽ log:
```
Graph API token exchange failed: ...AADSTS70000...
Refresh token expired, attempting password-based refresh for TepPalmore9298@hotmail.com...
Got new refresh token via password auth, retrying token exchange...
Token refresh successful via password fallback, provider: graph
```

## Cách hoạt động

1. **Token exchange thất bại** → Detect error codes:
   - `invalid_grant`
   - `AADSTS70000` 
   - `AADSTS50173`
   - `interaction_required`
   - `token has been revoked`

2. **Nếu có password** → Gọi `refresh_token_with_password()`:
   - Simulate browser OAuth flow
   - GET authorize URL → extract PPFT token
   - POST login với email/password
   - Handle consent page
   - Exchange code for new tokens

3. **Retry với new refresh_token** → Lưu vào cache

4. **Success!** → Return access token cho request

## Files đã thay đổi

- ✅ `api/oauth_refresh.py` - Password-based OAuth implementation
- ✅ `api/main.py` - Token refresh logic với password fallback
- ✅ `api/outlook_graph.py` - Absolute imports
- ✅ `api/outlook_imap.py` - Absolute imports
- ✅ `test_api.py` - API test script
- ✅ `test_refresh.py` - Direct module test
- ✅ `start_server.bat` - Server startup script

## Credential format

```
email|password|refresh_token|client_id
```

Example:
```
TepPalmore9298@hotmail.com|VQW6V64869|M.C505_BAY...|9e5f94bc-e8a4-4e73-b8be-63364c29d753
```

Khi refresh_token expired, system sẽ tự động dùng password để lấy token mới!
