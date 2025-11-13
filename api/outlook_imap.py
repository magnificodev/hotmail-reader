from __future__ import annotations

import os
import imaplib
import re
from typing import List, Optional, Tuple, Dict

import httpx

from config import get_outlook_scope
from constants import OUTLOOK_IMAP_HOST, OUTLOOK_IMAP_PORT

HOST = os.getenv("OUTLOOK_IMAP_HOST", OUTLOOK_IMAP_HOST)
PORT = int(os.getenv("OUTLOOK_IMAP_PORT", str(OUTLOOK_IMAP_PORT)))

# Compiled regex patterns for performance
_UID_PATTERN = re.compile(r"UID\s+(\d+)")


async def exchange_refresh_token_outlook(client_id: str, refresh_token: str):
    from config import get_tenant, get_client_secret
    
    tenant = get_tenant()
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    # Không gửi scope khi refresh_token để tránh invalid_scope; server sẽ giữ nguyên phạm vi đã cấp
    client_secret = get_client_secret()
    data: Dict[str, str] = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(token_url, data=data)
        if resp.status_code >= 400:
            error_body = resp.text
            raise RuntimeError(f"Token exchange failed: {resp.status_code} - {error_body}")
        js = resp.json()
        access_token = js.get("access_token")
        if not access_token:
            raise RuntimeError("No access_token for Outlook IMAP")
        expires_in = js.get("expires_in") or 3600
        new_refresh = js.get("refresh_token")  # may be None if not rotated
        return access_token, int(expires_in), new_refresh


def _xoauth2_auth_string(email_addr: str, access_token: str) -> bytes:
    # SASL XOAUTH2 initial client response (raw), imaplib will base64-encode it.
    # Format:  "user=<email>\x01auth=Bearer <token>\x01\x01"
    auth_str = f"user={email_addr}\x01auth=Bearer {access_token}\x01\x01"
    return auth_str.encode("utf-8")


def imap_xoauth_list(email_addr: str, access_token: str, from_filter: Optional[str], limit: int, last_uid: Optional[int]) -> Tuple[List[Tuple[int, bytes]], Optional[int]]:
    imap = imaplib.IMAP4_SSL(HOST, PORT)
    try:
        typ, _ = imap.authenticate("XOAUTH2", lambda x: _xoauth2_auth_string(email_addr, access_token))
        if typ != "OK":
            raise imaplib.IMAP4.error("XOAUTH2 auth failed")
        typ, _ = imap.select("INBOX")
        if typ != "OK":
            raise imaplib.IMAP4.error("Cannot select INBOX")

        search_args: List[str] = ["ALL"] if not from_filter else ["FROM", from_filter]
        status, data = imap.uid("search", None, *search_args)
        if status != "OK" or not data or not data[0]:
            return [], None
        uids = [int(x) for x in data[0].decode().split() if x]
        uids.sort(reverse=True)
        if last_uid:
            uids = [u for u in uids if u < last_uid]
        take = uids[: max(1, min(limit, 50))]

        messages: List[Tuple[int, bytes]] = []
        if take:
            seq = ",".join(str(u) for u in take)
            # Request UID in response explicitly
            status_h, fetched = imap.uid("fetch", seq, "(UID RFC822.HEADER)")
            if status_h == "OK" and fetched:
                tmp: Dict[int, bytes] = {}
                for part in fetched:
                    if not isinstance(part, tuple) or not part or part[1] is None:
                        continue
                    info = (part[0] or b"").decode(errors="ignore")
                    m = _UID_PATTERN.search(info)
                    if not m:
                        continue
                    uid_val = int(m.group(1))
                    tmp[uid_val] = part[1]
                for uid in take:
                    if uid in tmp:
                        messages.append((uid, tmp[uid]))
                # Fallback: if parsing failed, do per-UID fetch to avoid empty list
                if not messages:
                    for uid in take:
                        status_h, fetched_h = imap.uid("fetch", str(uid), "(RFC822.HEADER)")
                        if status_h == "OK" and fetched_h and isinstance(fetched_h[0], tuple):
                            messages.append((uid, fetched_h[0][1]))
        # Only provide next_token when there are more items beyond the current page
        next_token = take[-1] if take and len(uids) > len(take) else None
        return messages, next_token
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def imap_xoauth_get_body(email_addr: str, access_token: str, uid: int) -> bytes:
    imap = imaplib.IMAP4_SSL(HOST, PORT)
    try:
        typ, _ = imap.authenticate("XOAUTH2", lambda x: _xoauth2_auth_string(email_addr, access_token))
        if typ != "OK":
            raise imaplib.IMAP4.error("XOAUTH2 auth failed")
        typ, _ = imap.select("INBOX")
        if typ != "OK":
            raise imaplib.IMAP4.error("Cannot select INBOX")
        status, fetched = imap.uid("fetch", str(uid), "(BODY.PEEK[])")
        if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
            raise imaplib.IMAP4.error("Fetch BODY failed")
        return fetched[0][1]
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def imap_xoauth_fetch_bodies(email_addr: str, access_token: str, uids: List[int]) -> Dict[int, bytes]:
    """Batch fetch BODY[] for given UIDs. Returns uid -> raw bytes."""
    if not uids:
        return {}
    imap = imaplib.IMAP4_SSL(HOST, PORT)
    try:
        typ, _ = imap.authenticate("XOAUTH2", lambda x: _xoauth2_auth_string(email_addr, access_token))
        if typ != "OK":
            raise imaplib.IMAP4.error("XOAUTH2 auth failed")
        typ, _ = imap.select("INBOX")
        if typ != "OK":
            raise imaplib.IMAP4.error("Cannot select INBOX")
        seq = ",".join(str(u) for u in uids)
        status, fetched = imap.uid("fetch", seq, "(UID BODY.PEEK[])")
        res: Dict[int, bytes] = {}
        if status == "OK" and fetched:
            for part in fetched:
                if not isinstance(part, tuple) or not part or part[1] is None:
                    continue
                info = (part[0] or b"").decode(errors="ignore")
                m = _UID_PATTERN.search(info)
                if not m:
                    continue
                uid_val = int(m.group(1))
                res[uid_val] = part[1]
        return res
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def imap_xoauth_list_and_bodies(
    email_addr: str, access_token: str, from_filter: Optional[str], limit: int, last_uid: Optional[int], include_bodies: bool = False
) -> Tuple[List[Tuple[int, bytes]], Optional[int], Dict[int, bytes], int]:
    """
    Fetch headers and optionally bodies in one IMAP connection.
    Returns: (headers_list, next_uid, bodies_map, total_count)
    total_count chỉ được tính khi last_uid is None (trang đầu tiên)
    """
    imap = imaplib.IMAP4_SSL(HOST, PORT)
    bodies_map: Dict[int, bytes] = {}
    total_count = 0
    try:
        typ, _ = imap.authenticate("XOAUTH2", lambda x: _xoauth2_auth_string(email_addr, access_token))
        if typ != "OK":
            raise imaplib.IMAP4.error("XOAUTH2 auth failed")
        typ, _ = imap.select("INBOX")
        if typ != "OK":
            raise imaplib.IMAP4.error("Cannot select INBOX")

        search_args: List[str] = ["ALL"] if not from_filter else ["FROM", from_filter]
        status, data = imap.uid("search", None, *search_args)
        if status != "OK" or not data or not data[0]:
            return [], None, {}, 0
        uids = [int(x) for x in data[0].decode().split() if x]
        
        # Tính total_count chỉ khi là trang đầu tiên (last_uid is None)
        if last_uid is None:
            total_count = len(uids)
        
        uids.sort(reverse=True)
        if last_uid:
            uids = [u for u in uids if u < last_uid]
        take = uids[: max(1, min(limit, 50))]

        messages: List[Tuple[int, bytes]] = []
        if take:
            seq = ",".join(str(u) for u in take)
            # Fetch headers
            status_h, fetched = imap.uid("fetch", seq, "(UID RFC822.HEADER)")
            if status_h == "OK" and fetched:
                tmp: Dict[int, bytes] = {}
                for part in fetched:
                    if not isinstance(part, tuple) or not part or part[1] is None:
                        continue
                    info = (part[0] or b"").decode(errors="ignore")
                    m = _UID_PATTERN.search(info)
                    if not m:
                        continue
                    uid_val = int(m.group(1))
                    tmp[uid_val] = part[1]
                for uid in take:
                    if uid in tmp:
                        messages.append((uid, tmp[uid]))
                # Fallback: if parsing failed, do per-UID fetch to avoid empty list
                if not messages:
                    for uid in take:
                        status_h, fetched_h = imap.uid("fetch", str(uid), "(RFC822.HEADER)")
                        if status_h == "OK" and fetched_h and isinstance(fetched_h[0], tuple):
                            messages.append((uid, fetched_h[0][1]))
            
            # Fetch bodies in the same connection if requested
            if include_bodies and messages:
                uids_to_fetch = [uid for uid, _ in messages]
                seq_bodies = ",".join(str(u) for u in uids_to_fetch)
                status_b, fetched_b = imap.uid("fetch", seq_bodies, "(UID BODY.PEEK[])")
                if status_b == "OK" and fetched_b:
                    for part in fetched_b:
                        if not isinstance(part, tuple) or not part or part[1] is None:
                            continue
                        info = (part[0] or b"").decode(errors="ignore")
                        m = _UID_PATTERN.search(info)
                        if not m:
                            continue
                        uid_val = int(m.group(1))
                        bodies_map[uid_val] = part[1]
            
            # Only provide next_token when there are more items beyond the current page
            next_token = take[-1] if take and len(uids) > len(take) else None
            return messages, next_token, bodies_map, total_count
        
        return [], None, {}, total_count
    finally:
        try:
            imap.logout()
        except Exception:
            pass
