from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .credentials import parse_cred_string, select_provider
from .graph import exchange_refresh_token, list_messages as graph_list_messages, get_message_body as graph_get_body
from .imap_client import connect_and_search, parse_header
from .otp_utils import html_to_text, extract_otp_from_text, within_window
from .types import EmailMessage, PageResult


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


class MessagesRequest(BaseModel):
    credString: str
    from_: Optional[str] = None
    page_size: Optional[int] = 20
    page_token: Optional[str] = None


class OtpRequest(BaseModel):
    credString: str
    from_: Optional[str] = None
    regex: Optional[str] = None
    time_window_minutes: Optional[int] = 30


@app.get("/dev/cred")
def dev_cred() -> Dict[str, Optional[str]]:
    if os.environ.get("NODE_ENV") != "development":
        return {"credString": None}
    return {"credString": os.environ.get("TEST_CRED_STRING")}


@app.post("/messages")
async def messages(req: MessagesRequest) -> PageResult:
    creds = parse_cred_string(req.credString)
    provider = select_provider(creds)
    from_filter = req.from_
    size = max(1, min(req.page_size or 20, 50))

    if provider == "graph":
        try:
            token = await exchange_refresh_token(creds.client_id or "", creds.refresh_token or "")
            raw_items, next_token = await graph_list_messages(token, from_filter, size, req.page_token)
            items: List[EmailMessage] = []
            for itm in raw_items:
                from_addr = (itm.get("from") or {}).get("emailAddress", {}).get("address", "")
                to_list = [r.get("emailAddress", {}).get("address", "") for r in (itm.get("toRecipients") or [])]
                items.append({
                    "id": itm.get("id", ""),
                    "from_": from_addr,
                    "to": [t for t in to_list if t],
                    "subject": itm.get("subject", ""),
                    "snippet": itm.get("bodyPreview", ""),
                    "date": itm.get("receivedDateTime", ""),
                })
            return {"items": items, "next_page_token": next_token}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Graph error: {type(e).__name__}")

    if provider == "imap":
        if not creds.password:
            raise HTTPException(status_code=400, detail="IMAP requires password")
        try:
            raw, next_uid = connect_and_search(creds.email, creds.password, from_filter, size, int(req.page_token) if req.page_token else None)
            items: List[EmailMessage] = []
            for uid, header_bytes in raw:
                from_raw, to_list, subject, date = parse_header(header_bytes)
                items.append({
                    "id": str(uid),
                    "from_": from_raw,
                    "to": to_list,
                    "subject": subject,
                    "snippet": "",
                    "date": date,
                })
            return {"items": items, "next_page_token": str(next_uid) if next_uid else None}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"IMAP error: {type(e).__name__}")

    raise HTTPException(status_code=400, detail="Invalid credentials: need refresh_token+client_id or password")


@app.post("/otp")
async def otp(req: OtpRequest) -> Dict[str, Any]:
    creds = parse_cred_string(req.credString)
    provider = select_provider(creds)
    from_filter = req.from_
    time_window = req.time_window_minutes or 30

    if provider == "graph":
        try:
            token = await exchange_refresh_token(creds.client_id or "", creds.refresh_token or "")
            raw_items, _ = await graph_list_messages(token, from_filter, 5, None)
            for itm in raw_items:
                msg_id = itm.get("id", "")
                ctype, body, subject, date = await graph_get_body(token, msg_id)
                text = body if (ctype or "").lower() == "text" else html_to_text(body)
                code = extract_otp_from_text(text, req.regex)
                if code and within_window(date, time_window):
                    return {"otp": code, "emailId": msg_id, "subject": subject, "date": date}
            return {"otp": None}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Graph error: {type(e).__name__}")

    if provider == "imap":
        # For IMAP, this minimal implementation does not fetch full body to keep complexity low.
        # It could be extended to fetch BODY[] for the most recent message.
        try:
            raw, _ = connect_and_search(creds.email, creds.password or "", from_filter, 5, None)
            # In a real extension, fetch full BODY[] for the first UID and parse
            return {"otp": None}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"IMAP error: {type(e).__name__}")

    raise HTTPException(status_code=400, detail="Invalid credentials")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

