from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import secrets
import hashlib
import base64
import time
import httpx
from fastapi.responses import RedirectResponse, JSONResponse
import email as pyemail
from email.header import decode_header, make_header

from credentials import parse_cred_string, select_provider
from outlook_imap import exchange_refresh_token_outlook, imap_xoauth_list, imap_xoauth_get_body, imap_xoauth_fetch_bodies, imap_xoauth_list_and_bodies
from otp_utils import html_to_text, extract_otp_from_text, within_window
from models import EmailMessage, PageResult
from config import (
    get_ui_origins, get_client_id, get_client_secret, get_tenant,
    get_outlook_scope, get_oauth_redirect_uri, is_development, get_test_cred_string
)
from constants import (
    DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, MIN_PAGE_SIZE,
    DEFAULT_OTP_TOP_EMAILS, DEFAULT_TIME_WINDOW_MINUTES,
    STATE_TTL_SECONDS, TOKEN_EXPIRY_BUFFER_SECONDS,
    ERROR_IMAP, ERROR_INVALID_CREDENTIALS
)

app = FastAPI(title="Hotmail Reader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_ui_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


class MessagesRequest(BaseModel):
    credString: str
    from_: Optional[str] = None
    page_size: Optional[int] = Field(default=DEFAULT_PAGE_SIZE, ge=MIN_PAGE_SIZE, le=MAX_PAGE_SIZE)
    page_token: Optional[str] = None
    include_body: Optional[bool] = False


class OtpRequest(BaseModel):
    credString: str
    from_: Optional[str] = None
    regex: Optional[str] = None
    time_window_minutes: Optional[int] = Field(default=DEFAULT_TIME_WINDOW_MINUTES, ge=1)


class MessageBodyRequest(BaseModel):
    credString: str
    id: str = Field(..., description="IMAP UID")


@app.get("/dev/cred")
def dev_cred() -> Dict[str, Optional[str]]:
    if not is_development():
        return {"credString": None}
    return {"credString": get_test_cred_string()}


# ===== OAuth 2.0 Authorization Code Flow with PKCE (S256) =====
_STATE_STORE: Dict[str, Dict[str, Any]] = {}
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}


def _cleanup_expired_states() -> None:
    """Remove expired states from STATE_STORE."""
    now = time.time()
    expired = [k for k, v in _STATE_STORE.items() if now - v.get("ts", 0) > STATE_TTL_SECONDS]
    for k in expired:
        _STATE_STORE.pop(k, None)


def _cleanup_expired_tokens() -> None:
    """Remove expired tokens from TOKEN_CACHE."""
    now = time.time()
    expired = [k for k, v in _TOKEN_CACHE.items() if v.get("expires_at", 0) - TOKEN_EXPIRY_BUFFER_SECONDS <= now]
    for k in expired:
        _TOKEN_CACHE.pop(k, None)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _gen_code_verifier() -> str:
    # 43-128 chars
    return _b64url(secrets.token_bytes(64))


def _code_challenge_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return _b64url(digest)


@app.get("/oauth/authorize")
def oauth_authorize() -> RedirectResponse:
    client_id = get_client_id()
    if not client_id:
        raise HTTPException(
            status_code=400, 
            detail="OAuth flow requires CLIENT_ID in environment variables. If you already have refresh_token, use the input field instead."
        )
    tenant = get_tenant()
    scope = get_outlook_scope()
    redirect_uri = get_oauth_redirect_uri()

    # Cleanup expired states before creating new one
    _cleanup_expired_states()

    state = _b64url(secrets.token_bytes(24))
    verifier = _gen_code_verifier()
    challenge = _code_challenge_s256(verifier)
    _STATE_STORE[state] = {"verifier": verifier, "ts": time.time()}

    auth_url = (
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={httpx.QueryParams({'redirect_uri': redirect_uri})['redirect_uri']}"
        f"&response_mode=query"
        f"&scope={httpx.QueryParams({'scope': scope})['scope']}"
        f"&code_challenge_method=S256"
        f"&code_challenge={challenge}"
        f"&state={state}"
    )
    return RedirectResponse(url=auth_url, status_code=302)


@app.get("/oauth/callback")
async def oauth_callback(request: Request) -> JSONResponse:
    params = dict(request.query_params)
    code = params.get("code")
    state = params.get("state")
    error = params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"oauth_error:{error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code/state")

    # Cleanup expired states first
    _cleanup_expired_states()
    
    entry = _STATE_STORE.pop(state, None)
    if not entry:
        raise HTTPException(status_code=400, detail="state_not_found_or_expired")
    
    # Check if state is expired
    now = time.time()
    if now - entry.get("ts", 0) > STATE_TTL_SECONDS:
        raise HTTPException(status_code=400, detail="state_expired")
    
    verifier: str = entry["verifier"]

    client_id = get_client_id()
    tenant = get_tenant()
    scope = get_outlook_scope()
    redirect_uri = get_oauth_redirect_uri()
    client_secret = get_client_secret()

    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
        "scope": scope,
    }
    if client_secret:
        data["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(token_url, data=data)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            snippet = (e.response.text or "")[:300].replace("\n", " ")
            raise HTTPException(status_code=400, detail=f"token_exchange_failed: {snippet}")
        token_json = resp.json()
        refresh_token = token_json.get("refresh_token")
        access_token = token_json.get("access_token")
        if not refresh_token or not access_token:
            raise HTTPException(status_code=400, detail="missing_tokens_in_response")

        # Không gọi Graph /me nữa; nếu muốn có email, yêu cầu scope openid profile và đọc id_token.
        me_email = None

    cred_email = me_email or ""
    cred_string = f"{cred_email}||{refresh_token}|{client_id}"
    return JSONResponse({"credString": cred_string})


def _cache_key(email: str, client_id: Optional[str], refresh_token: Optional[str]) -> str:
    # Keyed by client_id + a short hash of refresh_token; email for completeness
    rt = (refresh_token or "")
    short = hashlib.sha256(rt.encode()).hexdigest()[:12]
    return f"{email}|{client_id}|{short}"


async def get_outlook_access_token(email: str, client_id: str, refresh_token: str, password: str | None = None) -> Tuple[str, str]:
    """
    Get access token and detect provider type (graph or imap).
    Returns: (access_token, provider_type)
    """
    # Cleanup expired tokens before checking cache
    _cleanup_expired_tokens()
    
    now = time.time()
    key = _cache_key(email, client_id, refresh_token)
    entry = _TOKEN_CACHE.get(key)
    if entry and entry.get("expires_at", 0) - TOKEN_EXPIRY_BUFFER_SECONDS > now:
        return entry["access_token"], entry.get("provider", "graph")
    
    # Try Graph API token exchange first (more common and reliable)
    try:
        from outlook_graph import exchange_refresh_token_graph
        access_token, expires_in, new_refresh = await exchange_refresh_token_graph(client_id, refresh_token)
        _TOKEN_CACHE[key] = {
            "access_token": access_token, 
            "expires_at": now + int(expires_in),
            "provider": "graph"
        }
        print(f"Token exchange successful via Graph API, provider: graph")
        return access_token, "graph"
    except Exception as e1:
        # Fallback to IMAP token exchange if Graph fails
        print(f"Graph API token exchange failed: {e1}, trying IMAP...")
        try:
            access_token, expires_in, new_refresh = await exchange_refresh_token_outlook(client_id, refresh_token)
            _TOKEN_CACHE[key] = {
                "access_token": access_token, 
                "expires_at": now + int(expires_in),
                "provider": "imap"
            }
            print(f"Token exchange successful via IMAP endpoint, provider: imap")
            return access_token, "imap"
        except Exception as e2:
            # Check if refresh token expired (specific error codes)
            error_str = str(e1).lower() + str(e2).lower()
            is_token_expired = any(err in error_str for err in [
                "invalid_grant", "aadsts70000", "70000", "expired", "aadsts50173", "50173",
                "interaction_required", "token has been revoked", "revoked"
            ])
            
            print(f"Token expired check: is_expired={is_token_expired}, has_password={password is not None}, password_value={password}")
            print(f"Error string sample: {error_str[:200]}")
            
            if is_token_expired and password:
                print(f"Refresh token expired, attempting password-based refresh for {email}...")
                try:
                    from oauth_refresh import refresh_token_with_password
                    token_data = await refresh_token_with_password(email, password, client_id)
                    new_refresh_token = token_data.get("refresh_token")
                    
                    if not new_refresh_token:
                        raise ValueError("No refresh_token returned from password-based auth")
                    
                    print(f"Got new refresh token via password auth, retrying token exchange...")
                    
                    # Retry with new refresh token
                    try:
                        from outlook_graph import exchange_refresh_token_graph
                        access_token, expires_in, _ = await exchange_refresh_token_graph(client_id, new_refresh_token)
                        _TOKEN_CACHE[key] = {
                            "access_token": access_token,
                            "expires_at": now + int(expires_in),
                            "provider": "graph",
                            "new_refresh_token": new_refresh_token  # Store for credential update
                        }
                        print(f"Token refresh successful via password fallback, provider: graph")
                        return access_token, "graph"
                    except Exception as e3:
                        # Try IMAP fallback with new refresh token
                        access_token, expires_in, _ = await exchange_refresh_token_outlook(client_id, new_refresh_token)
                        _TOKEN_CACHE[key] = {
                            "access_token": access_token,
                            "expires_at": now + int(expires_in),
                            "provider": "imap",
                            "new_refresh_token": new_refresh_token  # Store for credential update
                        }
                        print(f"Token refresh successful via password fallback, provider: imap")
                        return access_token, "imap"
                        
                except Exception as e_pwd:
                    print(f"Password-based token refresh failed: {e_pwd}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Token expired and password refresh failed: {e_pwd}"
                    )
            
            print(f"Both token exchange methods failed. Graph: {e1}, IMAP: {e2}")
            raise HTTPException(
                status_code=400, 
                detail=f"Token exchange failed: Graph error: {e1}, IMAP error: {e2}"
            )


def _parse_addresses(h: str | None) -> List[str]:
    """Parse email addresses from header string."""
    if not h:
        return []
    try:
        addr = pyemail.utils.getaddresses([h])
        return [a[1] or a[0] for a in addr if (a[1] or a[0])]
    except Exception:
        return []


def _extract_email_content(msg: pyemail.message.Message) -> str:
    """Extract text content from email message, preferring text/plain over HTML."""
    content = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                raw = (part.get_payload(decode=True) or b"").decode(errors="ignore")
                content = re.sub(r"\s+", " ", raw).strip()
                break
        # Tìm HTML nếu chưa có text/plain
        if not content:
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/html":
                    html_raw = (part.get_payload(decode=True) or b"").decode(errors="ignore")
                    content = html_to_text(html_raw)  # Fallback: HTML → text
                    break
    else:
        ctype = msg.get_content_type()
        payload = (msg.get_payload(decode=True) or b"").decode(errors="ignore")
        if ctype == "text/plain":
            content = re.sub(r"\s+", " ", payload).strip()
        elif ctype == "text/html":
            content = html_to_text(payload)  # Fallback: HTML → text
    return content


def _extract_email_text_and_html(msg: pyemail.message.Message) -> tuple[str, str]:
    """Extract both text and HTML content from email message."""
    text = ""
    html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True) or b""
            if ctype == "text/plain" and not text:
                raw = payload.decode(errors="ignore")
                text = re.sub(r"\s+", " ", raw).strip()
            if ctype == "text/html" and not html:
                html = payload.decode(errors="ignore")
    else:
        ctype = msg.get_content_type()
        payload = msg.get_payload(decode=True) or b""
        if ctype == "text/plain":
            raw = payload.decode(errors="ignore")
            text = re.sub(r"\s+", " ", raw).strip()
        elif ctype == "text/html":
            html = payload.decode(errors="ignore")
    if not text and html:
        text = html_to_text(html)
    return text, html


def _sanitize_error_message(error: Exception, is_production: bool = False) -> str:
    """Sanitize error messages for client responses."""
    if is_production:
        # In production, only return generic error type
        return f"{ERROR_IMAP}: {type(error).__name__}"
    # In development, include more details
    error_msg = str(error)[:200]  # Limit length
    return f"{ERROR_IMAP}: {type(error).__name__}: {error_msg}"


@app.post("/messages")
async def messages(req: MessagesRequest) -> PageResult:
    creds = parse_cred_string(req.credString)
    provider = select_provider(creds)
    from_filter = req.from_
    size = max(MIN_PAGE_SIZE, min(req.page_size or DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE))

    if provider == "outlook_graph":
        # Use Microsoft Graph API
        try:
            from outlook_graph import exchange_refresh_token_graph, graph_list_and_convert
            
            token, detected_provider = await get_outlook_access_token(creds.email, creds.client_id or "", creds.refresh_token or "", creds.password)
            
            # If detected provider is IMAP, switch to IMAP logic
            if detected_provider == "imap":
                provider = "outlook_imap"
                # Fall through to IMAP logic below
            else:
                # Get messages via Graph API
                messages_data, next_token, total_count = await graph_list_and_convert(
                    token,
                    from_filter=from_filter,
                    limit=size,
                    skip_token=req.page_token,
                    include_bodies=req.include_body or False
                )
                
                # Convert to EmailMessage format
                items: List[EmailMessage] = []
                for msg_data in messages_data:
                    items.append({
                        "id": msg_data["id"],
                        "from_": msg_data["from"],
                        "to": [msg_data["to"]] if msg_data["to"] else [],
                        "subject": msg_data["subject"],
                        "content": msg_data.get("body_text") or msg_data.get("body_preview") or "",
                        "date": msg_data["date"],
                    })
                
                return {
                    "items": items,
                    "next_page_token": next_token,
                    "total": total_count if total_count >= 0 else None
                }
        except Exception as e:
            detail = _sanitize_error_message(e, not is_development())
            raise HTTPException(status_code=400, detail=detail)
    
    if provider == "outlook_imap":
        try:
            token, _ = await get_outlook_access_token(creds.email, creds.client_id or "", creds.refresh_token or "", creds.password)
            # Use optimized function that reuses IMAP connection
            page_token_int = None
            if req.page_token:
                try:
                    page_token_int = int(req.page_token)
                except (ValueError, TypeError):
                    page_token_int = None
            raw, next_uid, bodies_map, total_count = imap_xoauth_list_and_bodies(
                creds.email, token, from_filter, size, page_token_int, req.include_body
            )
            items: List[EmailMessage] = []

            for uid, header_bytes in raw:
                msg = pyemail.message_from_bytes(header_bytes)
                from_raw = str(make_header(decode_header(msg.get("From", ""))))
                to_list = _parse_addresses(msg.get("To"))
                subject = str(make_header(decode_header(msg.get("Subject", ""))))
                date = msg.get("Date", "")
                content = ""
                if req.include_body and uid in bodies_map:
                    bmsg = pyemail.message_from_bytes(bodies_map[uid])
                    content = _extract_email_content(bmsg)

                items.append({
                    "id": str(uid),
                    "from_": from_raw,
                    "to": to_list,
                    "subject": subject,
                    "content": content if req.include_body else "",
                    "date": date,
                    })
            return {"items": items, "next_page_token": str(next_uid) if next_uid else None, "total": total_count if page_token_int is None else None}
        except Exception as e:
            detail = _sanitize_error_message(e, not is_development())
            raise HTTPException(status_code=400, detail=detail)

    raise HTTPException(status_code=400, detail=ERROR_INVALID_CREDENTIALS)


@app.post("/otp")
async def otp(req: OtpRequest) -> Dict[str, Any]:
    creds = parse_cred_string(req.credString)
    provider = select_provider(creds)
    from_filter = req.from_
    time_window = req.time_window_minutes or DEFAULT_TIME_WINDOW_MINUTES

    if provider == "outlook_graph":
        # Use Microsoft Graph API
        try:
            from outlook_graph import graph_list_and_convert
            
            token, detected_provider = await get_outlook_access_token(creds.email, creds.client_id or "", creds.refresh_token or "", creds.password)
            
            # If detected provider is IMAP, switch to IMAP logic
            if detected_provider == "imap":
                provider = "outlook_imap"
                # Fall through to IMAP logic below
            else:
                # Get recent messages
                messages_data, _, _ = await graph_list_and_convert(
                    token,
                    from_filter=from_filter,
                    limit=DEFAULT_OTP_TOP_EMAILS,
                    skip_token=None,
                    include_bodies=True
                )
                
                if not messages_data:
                    return {"otp": None}
                
                # Extract OTP from messages
                import logging
                for idx, msg_data in enumerate(messages_data):
                    logging.warning(f"[OTP DEBUG] Mail {idx+1}: subject={msg_data.get('subject')}")
                    logging.warning(f"[OTP DEBUG] body_text={repr(msg_data.get('body_text'))}")
                    logging.warning(f"[OTP DEBUG] body_html={repr(msg_data.get('body_html'))}")
                    # Get date
                    date_str = msg_data.get("date", "")
                    try:
                        # Parse email date format
                        import email.utils
                        dt_tuple = email.utils.parsedate_to_datetime(date_str)
                        if not within_window(dt_tuple, time_window):
                            continue
                    except:
                        continue

                    # Lấy text và html
                    text = msg_data.get("body_text") or msg_data.get("body_preview") or ""
                    html = msg_data.get("body_html") or ""

                    # Ưu tiên trích xuất OTP từ text
                    found = extract_otp_from_text(text, req.regex)
                    # Nếu không có, thử convert từ html sang text và trích xuất lại
                    if not found and html:
                        text_from_html = html_to_text(html)
                        found = extract_otp_from_text(text_from_html, req.regex)

                    if found:
                        return {
                            "otp": found,
                            "from": msg_data["from"],
                            "subject": msg_data["subject"],
                            "date": date_str,
                        }
                return {"otp": None}
        except Exception as e:
            detail = _sanitize_error_message(e, not is_development())
            raise HTTPException(status_code=400, detail=detail)
    
    if provider == "outlook_imap":
        try:
            token, _ = await get_outlook_access_token(creds.email, creds.client_id or "", creds.refresh_token or "", creds.password)
            # Optimize: Use batch fetch instead of individual calls
            raw, _ = imap_xoauth_list(creds.email, token, from_filter, DEFAULT_OTP_TOP_EMAILS, None)
            if not raw:
                return {"otp": None}
            
            # Batch fetch bodies in one connection
            uids = [uid for uid, _ in raw]
            bodies_map = imap_xoauth_fetch_bodies(creds.email, token, uids)
            
            for uid, _hdr in raw:
                if uid not in bodies_map:
                    continue
                body_bytes = bodies_map[uid]
                msg = pyemail.message_from_bytes(body_bytes)
                subject = msg.get("Subject", "")
                date = msg.get("Date", "")
                # Lấy text content
                text = _extract_email_content(msg)
                code = extract_otp_from_text(text, req.regex)
                if code and (not date or within_window(date, time_window)):
                    return {"otp": code, "emailId": str(uid), "subject": subject, "date": date}
            return {"otp": None}
        except Exception as e:
            detail = _sanitize_error_message(e, not is_development())
            raise HTTPException(status_code=400, detail=detail)

    raise HTTPException(status_code=400, detail=ERROR_INVALID_CREDENTIALS)


@app.post("/message")
async def message_body(req: MessageBodyRequest) -> Dict[str, Any]:
    creds = parse_cred_string(req.credString)
    provider = select_provider(creds)
    
    if provider == "outlook_graph":
        # Use Microsoft Graph API
        try:
            from outlook_graph import graph_get_message_details
            
            token, detected_provider = await get_outlook_access_token(creds.email, creds.client_id or "", creds.refresh_token or "", creds.password)
            
            # If detected provider is IMAP, switch to IMAP logic
            if detected_provider == "imap":
                provider = "outlook_imap"
                # Fall through to IMAP logic below
            else:
                # Get message details
                msg_data = await graph_get_message_details(token, req.id)
                
                return {
                    "id": req.id,
                    "subject": msg_data["subject"],
                    "date": msg_data["date"],
                    "from": msg_data["from"],
                    "to": msg_data["to"],
                    "text": msg_data.get("body_text") or "",
                    "html": msg_data.get("body_html") or "",
                }
        except Exception as e:
            detail = _sanitize_error_message(e, not is_development())
            raise HTTPException(status_code=400, detail=detail)
    
    if provider == "outlook_imap":
        try:
            token, _ = await get_outlook_access_token(creds.email, creds.client_id or "", creds.refresh_token or "", creds.password)
            body_bytes = imap_xoauth_get_body(creds.email, token, int(req.id))
            msg = pyemail.message_from_bytes(body_bytes)
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            date = msg.get("Date", "")
            from_raw = str(make_header(decode_header(msg.get("From", ""))))
            to_raw = msg.get("To", "") or ""
            # Extract text and html using shared function
            text, html = _extract_email_text_and_html(msg)
            return {"id": req.id, "subject": subject, "date": date, "from": from_raw, "to": to_raw, "text": text, "html": html}
        except Exception as e:
            detail = _sanitize_error_message(e, not is_development())
            raise HTTPException(status_code=400, detail=detail)
    
    raise HTTPException(status_code=400, detail=ERROR_INVALID_CREDENTIALS)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


