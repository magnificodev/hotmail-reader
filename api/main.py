from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dotenv import load_dotenv
import secrets
import hashlib
import base64
import time
import httpx
from fastapi.responses import RedirectResponse, JSONResponse
import email as pyemail
from email.header import decode_header, make_header

from .credentials import parse_cred_string, select_provider
from .outlook_imap import exchange_refresh_token_outlook, imap_xoauth_list, imap_xoauth_get_body, imap_xoauth_fetch_bodies, imap_xoauth_list_and_bodies
from .otp_utils import html_to_text, extract_otp_from_text, within_window
from .models import EmailMessage, PageResult


# Load env from project root and api/.env explicitly
load_dotenv()
try:
    from pathlib import Path
    load_dotenv(Path(__file__).with_name(".env"))
except Exception:
    pass

app = FastAPI(title="Hotmail Reader API")

origins = [
    os.environ.get("UI_ORIGIN", "http://localhost:3000"),
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
    page_size: Optional[int] = 20
    page_token: Optional[str] = None
    include_body: Optional[bool] = False


class OtpRequest(BaseModel):
    credString: str
    from_: Optional[str] = None
    regex: Optional[str] = None
    time_window_minutes: Optional[int] = 30


class MessageBodyRequest(BaseModel):
    credString: str
    id: str  # IMAP UID


@app.get("/dev/cred")
def dev_cred() -> Dict[str, Optional[str]]:
    if os.environ.get("NODE_ENV") != "development":
        return {"credString": None}
    return {"credString": os.environ.get("TEST_CRED_STRING")}


# ===== OAuth 2.0 Authorization Code Flow with PKCE (S256) =====
_STATE_STORE: Dict[str, Dict[str, Any]] = {}
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}


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
    client_id = os.environ.get("CLIENT_ID") or os.environ.get("GRAPH_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=400, detail="Missing CLIENT_ID in env")
    tenant = os.environ.get("GRAPH_TENANT", "consumers")
    scope = os.environ.get("GRAPH_SCOPE", "offline_access Mail.Read")
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8000/oauth/callback")

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

    entry = _STATE_STORE.pop(state, None)
    if not entry:
        raise HTTPException(status_code=400, detail="state_not_found_or_expired")
    verifier: str = entry["verifier"]

    client_id = os.environ.get("CLIENT_ID") or os.environ.get("GRAPH_CLIENT_ID")
    tenant = os.environ.get("GRAPH_TENANT", "consumers")
    scope = os.environ.get("GRAPH_SCOPE", "offline_access Mail.Read")
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8000/oauth/callback")
    client_secret = os.environ.get("GRAPH_CLIENT_SECRET")

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


async def get_outlook_access_token(email: str, client_id: str, refresh_token: str) -> str:
    now = time.time()
    key = _cache_key(email, client_id, refresh_token)
    entry = _TOKEN_CACHE.get(key)
    if entry and entry.get("expires_at", 0) - 60 > now:
        return entry["access_token"]
    access_token, expires_in, new_refresh = await exchange_refresh_token_outlook(client_id, refresh_token)
    _TOKEN_CACHE[key] = {"access_token": access_token, "expires_at": now + int(expires_in)}
    return access_token


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


@app.post("/messages")
async def messages(req: MessagesRequest) -> PageResult:
    creds = parse_cred_string(req.credString)
    provider = select_provider(creds)
    from_filter = req.from_
    size = max(1, min(req.page_size or 20, 50))

    if provider == "outlook_imap":
        try:
            token = await get_outlook_access_token(creds.email, creds.client_id or "", creds.refresh_token or "")
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
            raise HTTPException(status_code=400, detail=f"Outlook IMAP error: {type(e).__name__}: {str(e)[:200]}")

    raise HTTPException(status_code=400, detail="Invalid credentials: need refresh_token+client_id (Outlook IMAP)")


@app.post("/otp")
async def otp(req: OtpRequest) -> Dict[str, Any]:
    creds = parse_cred_string(req.credString)
    provider = select_provider(creds)
    from_filter = req.from_
    time_window = req.time_window_minutes or 30

    if provider == "outlook_imap":
        try:
            token = await get_outlook_access_token(creds.email, creds.client_id or "", creds.refresh_token or "")
            # Lấy top 5 UID mới nhất theo filter
            raw, _ = imap_xoauth_list(creds.email, token, from_filter, 5, None)
            for uid, _hdr in raw:
                body_bytes = imap_xoauth_get_body(creds.email, token, uid)
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
            raise HTTPException(status_code=400, detail=f"Outlook IMAP error: {type(e).__name__}: {str(e)[:200]}")

    raise HTTPException(status_code=400, detail="Invalid credentials: need refresh_token+client_id (Outlook IMAP)")


@app.post("/message")
async def message_body(req: MessageBodyRequest) -> Dict[str, Any]:
    creds = parse_cred_string(req.credString)
    provider = select_provider(creds)
    if provider != "outlook_imap":
        raise HTTPException(status_code=400, detail="Invalid credentials: need refresh_token+client_id (Outlook IMAP)")
    try:
        token = await get_outlook_access_token(creds.email, creds.client_id or "", creds.refresh_token or "")
        body_bytes = imap_xoauth_get_body(creds.email, token, int(req.id))
        msg = pyemail.message_from_bytes(body_bytes)
        subject = str(make_header(decode_header(msg.get("Subject", ""))))
        date = msg.get("Date", "")
        from_raw = str(make_header(decode_header(msg.get("From", ""))))
        to_raw = msg.get("To", "") or ""
        # Extract text and html
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
        return {"id": req.id, "subject": subject, "date": date, "from": from_raw, "to": to_raw, "text": text, "html": html}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Outlook IMAP error: {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


