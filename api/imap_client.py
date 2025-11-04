from __future__ import annotations

import email
import imaplib
from email.header import decode_header, make_header
from typing import List, Optional, Tuple


HOST = "outlook.office365.com"
PORT = 993


def _decode(s: bytes | str) -> str:
    if isinstance(s, str):
        return s
    try:
        return s.decode("utf-8", errors="ignore")
    except Exception:
        return s.decode(errors="ignore")


def _parse_addresses(h: str | None) -> List[str]:
    if not h:
        return []
    try:
        addr = email.utils.getaddresses([h])
        return [a[1] or a[0] for a in addr if (a[1] or a[0])]
    except Exception:
        return []


def connect_and_search(email_addr: str, password: str, from_filter: Optional[str], limit: int, last_uid: Optional[int]) -> Tuple[List[Tuple[int, bytes]], Optional[int]]:
    imap = imaplib.IMAP4_SSL(HOST, PORT)
    imap.login(email_addr, password)
    try:
        imap.select("INBOX")
        criteria = ["ALL"]
        if from_filter:
            criteria = ["FROM", f"{from_filter}"]
        status, data = imap.search(None, *criteria)
        if status != "OK":
            return [], None
        uids = [int(x) for x in _decode(data[0]).split()]
        uids.sort(reverse=True)
        if last_uid:
            uids = [u for u in uids if u < last_uid]
        selected = uids[:max(1, min(limit, 50))]
        messages: List[Tuple[int, bytes]] = []
        for uid in selected:
            status, fetched = imap.uid("fetch", str(uid), "(RFC822.HEADER RFC822.SIZE BODY.PEEK[TEXT]<0.256>)")
            if status != "OK" or not fetched or len(fetched) < 2:
                continue
            # Fallback minimal fetch of header
            status2, fetched2 = imap.uid("fetch", str(uid), "(RFC822.HEADER)")
            header_bytes = b""
            if status2 == "OK" and fetched2 and len(fetched2) >= 2 and isinstance(fetched2[0], tuple):
                header_bytes = fetched2[0][1]
            messages.append((uid, header_bytes))
        next_token = selected[-1] if selected else None
        return messages, next_token
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def parse_header(header_bytes: bytes) -> Tuple[str, List[str], str, str]:
    msg = email.message_from_bytes(header_bytes)
    from_raw = str(make_header(decode_header(msg.get("From", ""))))
    to_list = _parse_addresses(msg.get("To"))
    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    date = msg.get("Date", "")
    return from_raw, to_list, subject, date

