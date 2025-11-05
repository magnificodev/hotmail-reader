import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from bs4 import BeautifulSoup


# Compiled regex patterns for performance
_WHITESPACE_NEWLINE_PATTERN = re.compile(r"\s*\n\s*")
_MULTIPLE_SPACES_PATTERN = re.compile(r" +")

# Simple OTP pattern - only 6 digits
_OTP_PATTERNS = [
    # OTP with context keywords (highest priority)
    re.compile(r"(?:code|otp|pin|verification|mã|mật|khẩu|mã xác thực)[\s:]*[:\-]?\s*(\d{6})", re.IGNORECASE),
    # Standalone 6-digit numbers
    re.compile(r"(?<![0-9])(\d{6})(?![0-9])"),
]



def html_to_text(html: str) -> str:
    """Convert HTML to plain text reliably.

    Strategy:
    1) Try html5lib (best fidelity)
    2) Fallback to built-in 'html.parser'
    3) As last resort, strip tags with regex
    Always return normalized plain text.
    """
    raw = html or ""
    # Try with html5lib first
    try:
        soup = BeautifulSoup(raw, "html5lib")
        text = soup.get_text("\n", strip=True)
    except Exception:
        # Fallback to built-in parser
        try:
            soup = BeautifulSoup(raw, "html.parser")
            text = soup.get_text("\n", strip=True)
        except Exception:
            # Last resort: strip tags by regex
            import re as _re
            text = _re.sub(r"<[^>]*>", " ", raw)

    # Normalize whitespace
    text = _WHITESPACE_NEWLINE_PATTERN.sub(" ", text)
    text = _MULTIPLE_SPACES_PATTERN.sub(" ", text)
    return text.strip()


def _is_in_url(text: str, otp: str) -> bool:
    """
    Check if the OTP appears to be part of a URL.
    Excludes numbers in URLs, query parameters, paths, etc.
    """
    # Find all URLs in text - more comprehensive pattern
    url_pattern = re.compile(r'https?://[^\s<>"\'\)]+|www\.[^\s<>"\'\)]+|go\.\w+[^\s<>"\'\)]*|[\w\.]+\.(com|org|net|io|co|vn|jp|uk)[^\s<>"\'\)]*', re.IGNORECASE)
    urls = url_pattern.findall(text)
    
    for url in urls:
        # Check if OTP appears anywhere in the URL (query params, path, etc.)
        # More comprehensive check
        url_lower = url.lower()
        otp_pos = url.find(otp)
        if otp_pos == -1:
            continue
        
        # Check if it's in query parameters (like ?LinkID=281822 or &id=123456)
        if re.search(r'[?&][^=&]*=' + re.escape(otp) + r'(?:[^0-9&]|$)', url):
            return True
        # Check if it's in path segments (like /123456/ or /path/123456)
        if re.search(r'/' + re.escape(otp) + r'(?:[/?#]|$)', url):
            return True
        # Check if it's after domain (like example.com/123456)
        if re.search(r'\.(com|org|net|io|co|vn|jp|uk)/' + re.escape(otp), url, re.IGNORECASE):
            return True
        # Check if it's in the URL at all (catch-all for URLs)
        # If the number appears in URL and URL is substantial, likely not OTP
        if len(url) > 20 and otp in url:
            # Additional check: if it's not clearly separated by word boundaries
            # Check if it's part of a larger number sequence in URL
            url_chars_around = url[max(0, otp_pos-1):min(len(url), otp_pos+len(otp)+1)]
            # If surrounded by digits or URL characters, likely part of URL
            if re.search(r'[0-9\/\?=&]', url_chars_around):
                return True
    
    return False


def _is_valid_otp(otp: str, context: str = "") -> bool:
    """
    Validate if a 6-digit number is likely an OTP.
    Simple validation: only check URL and basic patterns.
    """
    if not otp or not otp.isdigit():
        return False
    
    # Must be exactly 6 digits
    if len(otp) != 6:
        return False
    
    # Exclude if it's in a URL
    if _is_in_url(context, otp):
        return False
    
    # Exclude numbers with too many zeros (like 000000)
    if otp.count('0') >= 5:  # 5 or more zeros
        return False
    
    # Exclude all same digits (111111, 222222, etc.)
    if len(set(otp)) == 1:
        return False
    
    # Exclude simple sequential (123456, 654321, etc.)
    is_sequential = all(int(otp[i]) == int(otp[i-1]) + 1 for i in range(1, len(otp))) or \
                   all(int(otp[i]) == int(otp[i-1]) - 1 for i in range(1, len(otp)))
    if is_sequential:
        return False
    
    return True


def extract_otp_from_text(text: str, regex: Optional[str]) -> Optional[str]:
    """
    Extract OTP from text - simple pattern: only 6-digit numbers.
    Filters out numbers in URLs and obvious non-OTP patterns.
    """
    if not text:
        return None
    
    # Use custom regex if provided
    if regex:
        try:
            pattern = re.compile(regex)
            m = pattern.search(text)
            if m:
                otp = m.group(1) if m.groups() else m.group(0)
                otp = re.sub(r'[\s\-\.]', '', otp)
                if _is_valid_otp(otp, text):
                    return otp
        except Exception:
            pass
    
    # Try patterns in order of priority
    # 1. OTP with context keywords (most reliable)
    for pattern in _OTP_PATTERNS:
        m = pattern.search(text)
        if m:
            otp = m.group(1) if m.groups() else m.group(0)
            # Clean up separators
            otp = re.sub(r'[\s\-\.]', '', otp)
            # Must be exactly 6 digits
            if len(otp) == 6 and _is_valid_otp(otp, text):
                return otp
    
    # Fallback to standalone 6-digit pattern (same as pattern 2, but with validation)
    m = re.search(r"(?<![0-9])(\d{6})(?![0-9])", text)
    if m:
        otp = m.group(1)
        if _is_valid_otp(otp, text):
            return otp
    
    return None


def within_window(date_iso: str, minutes: int) -> bool:
    try:
        # Graph uses ISO 8601
        dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
    except Exception:
        return True
    now = datetime.now(timezone.utc)
    return now - dt <= timedelta(minutes=minutes)

