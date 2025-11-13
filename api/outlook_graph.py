"""
Microsoft Graph API client for reading Outlook emails
Alternative to IMAP that works with Mail.Read scope
"""
from __future__ import annotations

import base64
import re
from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone
import email as pyemail
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx


async def exchange_refresh_token_graph(client_id: str, refresh_token: str):
    """
    Exchange refresh token for access token using Microsoft identity platform.
    Works with Mail.Read scope (Graph API).
    """
    from config import get_tenant, get_client_secret
    
    tenant = get_tenant()
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    client_secret = get_client_secret()
    
    data: Dict[str, str] = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
        "scope": "https://graph.microsoft.com/Mail.Read",
    }
    if client_secret:
        data["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(token_url, data=data)
        print(f"Token exchange status: {resp.status_code}")
        if resp.status_code >= 400:
            print(f"Token exchange error: {resp.text}")
        resp.raise_for_status()
        js = resp.json()
        access_token = js.get("access_token")
        if not access_token:
            raise RuntimeError("No access_token for Graph API")
        print(f"Token exchange successful, access_token length: {len(access_token)}")
        expires_in = js.get("expires_in") or 3600
        new_refresh = js.get("refresh_token")
        return access_token, int(expires_in), new_refresh


async def graph_list_messages(
    access_token: str,
    from_filter: Optional[str] = None,
    limit: int = 10,
    skip_token: Optional[str] = None
) -> Tuple[List[Dict], Optional[str]]:
    """
    List messages from inbox using Microsoft Graph API.
    
    Returns:
        - List of message objects with headers
        - Next skip token for pagination
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    # Build URL
    url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
    
    # Build query parameters
    params = {
        "$top": min(limit, 50),  # Graph API max is 999, but we limit to 50
        "$select": "id,subject,from,toRecipients,receivedDateTime,hasAttachments,isRead,internetMessageId",
    }
    
    # Only add $orderby if no filter (Microsoft Graph limitation for MSA accounts)
    if not from_filter:
        params["$orderby"] = "receivedDateTime desc"
    
    if from_filter:
        # Filter by sender email
        # Note: For MSA accounts, filter + orderby together causes "InefficientFilter" error
        # So we filter only, and sort client-side if needed
        params["$filter"] = f"from/emailAddress/address eq '{from_filter}'"
    
    if skip_token:
        params["$skiptoken"] = skip_token
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params)
        print(f"Graph API request URL: {resp.url}")
        print(f"Graph API status: {resp.status_code}")
        if resp.status_code >= 400:
            print(f"Graph API error response: {resp.text}")
        resp.raise_for_status()
        
        result = resp.json()
        messages = result.get("value", [])
        
        # Extract next skip token from @odata.nextLink
        next_link = result.get("@odata.nextLink")
        next_skip_token = None
        if next_link:
            # Extract skiptoken parameter
            import urllib.parse
            parsed = urllib.parse.urlparse(next_link)
            query_params = urllib.parse.parse_qs(parsed.query)
            if "$skiptoken" in query_params:
                next_skip_token = query_params["$skiptoken"][0]
        
        return messages, next_skip_token


async def graph_get_message_body(access_token: str, message_id: str) -> str:
    """
    Get full message body (MIME content) from Graph API.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    
    # Get MIME content
    url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/$value"
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text


def _parse_graph_message_to_email_message(msg: Dict) -> Dict:
    """
    Convert Graph API message format to our EmailMessage format.
    """
    from models import EmailMessage
    
    # Extract sender
    from_obj = msg.get("from", {}).get("emailAddress", {})
    from_addr = from_obj.get("address", "")
    from_name = from_obj.get("name", "")
    from_header = f"{from_name} <{from_addr}>" if from_name else from_addr
    
    # Extract recipients
    to_list = msg.get("toRecipients", [])
    to_addrs = [r.get("emailAddress", {}).get("address", "") for r in to_list]
    to_header = ", ".join(to_addrs)
    
    # Extract subject
    subject = msg.get("subject", "")
    
    # Extract date
    received_dt = msg.get("receivedDateTime", "")
    # Parse ISO format: 2025-10-03T19:19:31Z
    try:
        dt = datetime.fromisoformat(received_dt.replace("Z", "+00:00"))
        date_header = dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    except:
        date_header = received_dt
    
    # Extract body
    body_obj = msg.get("body", {})
    body_content = body_obj.get("content", "")
    body_type = body_obj.get("contentType", "text")  # "text" or "html"
    
    # Message ID
    msg_id = msg.get("id", "")
    internet_msg_id = msg.get("internetMessageId", "")
    
    # Build email-like structure
    email_msg = {
        "id": msg_id,
        "from": from_header,
        "to": to_header,
        "subject": subject,
        "date": date_header,
        "body_preview": body_content[:200] if body_content else "",
        "body_html": body_content if body_type == "html" else "",
        "body_text": body_content if body_type == "text" else "",
        "has_attachments": msg.get("hasAttachments", False),
        "is_read": msg.get("isRead", False),
        "internet_message_id": internet_msg_id,
    }
    
    return email_msg


async def graph_list_and_convert(
    access_token: str,
    from_filter: Optional[str] = None,
    limit: int = 10,
    skip_token: Optional[str] = None,
    include_bodies: bool = False
) -> Tuple[List[Dict], Optional[str], int]:
    """
    List messages and convert to EmailMessage format.
    
    Returns:
        - List of EmailMessage dicts
        - Next skip token
        - Total count (approximate, Graph doesn't provide exact count easily)
    """
    messages, next_token = await graph_list_messages(
        access_token,
        from_filter=from_filter,
        limit=limit,
        skip_token=skip_token
    )
    
    # Convert to our format
    converted = []
    for msg in messages:
        converted.append(_parse_graph_message_to_email_message(msg))
    
    # Sort by date descending (client-side) if we have filter
    # (Graph API doesn't support $orderby + $filter for MSA accounts)
    if from_filter and converted:
        try:
            from email.utils import parsedate_to_datetime
            converted.sort(
                key=lambda x: parsedate_to_datetime(x.get("date", "")) if x.get("date") else datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )
        except:
            pass  # If sorting fails, keep original order
    
    # If include_bodies, we already have body preview
    # For full MIME content, would need separate call to /$value endpoint
    
    # Graph API doesn't easily provide total count without additional query
    # We'll return -1 to indicate unknown
    total_count = -1
    
    return converted, next_token, total_count


async def graph_get_message_details(access_token: str, message_id: str) -> Dict:
    """
    Get full message details including body.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
    params = {
        "$select": "id,subject,from,toRecipients,receivedDateTime,body,hasAttachments,isRead,internetMessageId"
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        
        msg = resp.json()
        return _parse_graph_message_to_email_message(msg)
