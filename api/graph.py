import base64
from typing import Dict, List, Optional, Tuple

import httpx


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"


async def exchange_refresh_token(client_id: str, refresh_token: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
            "scope": "https://graph.microsoft.com/.default offline_access",
        }
        resp = await client.post(TOKEN_URL, data=data)
        resp.raise_for_status()
        access_token = resp.json().get("access_token")
        if not access_token:
            raise RuntimeError("No access_token from token endpoint")
        return access_token


def encode_page_token(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode()).decode()


def decode_page_token(token: str) -> str:
    return base64.urlsafe_b64decode(token.encode()).decode()


async def list_messages(access_token: str, from_filter: Optional[str], page_size: int, page_token: Optional[str]) -> Tuple[List[Dict], Optional[str]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "$select": "id,from,toRecipients,subject,receivedDateTime,bodyPreview",
        "$top": str(max(1, min(page_size, 50))),
        "$orderby": "receivedDateTime desc",
    }
    if from_filter:
        # Exact match on sender address
        params["$filter"] = f"from/emailAddress/address eq '{from_filter}'"

    url = f"{GRAPH_BASE}/me/messages"
    if page_token:
        # Use nextLink directly if provided
        url = decode_page_token(page_token)
        params = None

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("value", [])
        next_link = data.get("@odata.nextLink")
        next_token = encode_page_token(next_link) if next_link else None
        return items, next_token


async def get_message_body(access_token: str, message_id: str) -> Tuple[str, str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"$select": "body,subject,receivedDateTime"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GRAPH_BASE}/me/messages/{message_id}", headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        body = (data.get("body") or {}).get("content") or ""
        content_type = (data.get("body") or {}).get("contentType") or "html"
        subject = data.get("subject") or ""
        date = data.get("receivedDateTime") or ""
        return content_type, body, subject, date

