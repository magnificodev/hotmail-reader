import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from bs4 import BeautifulSoup


DEFAULT_REGEX = r"(?<!\d)(\d{4,8})(?!\d)"


def html_to_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html or "", "html5lib")
        return soup.get_text(" ", strip=True)
    except Exception:
        return html or ""


def extract_otp_from_text(text: str, regex: Optional[str]) -> Optional[str]:
    pattern = re.compile(regex or DEFAULT_REGEX)
    m = pattern.search(text)
    return m.group(1) if m else None


def within_window(date_iso: str, minutes: int) -> bool:
    try:
        # Graph uses ISO 8601
        dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
    except Exception:
        return True
    now = datetime.now(timezone.utc)
    return now - dt <= timedelta(minutes=minutes)

