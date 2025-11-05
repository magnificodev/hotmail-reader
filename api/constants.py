"""Application constants."""

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1

# OTP
DEFAULT_OTP_TOP_EMAILS = 5
DEFAULT_TIME_WINDOW_MINUTES = 30

# OAuth
STATE_TTL_SECONDS = 600  # 10 minutes
TOKEN_CACHE_CLEANUP_INTERVAL = 300  # 5 minutes
TOKEN_EXPIRY_BUFFER_SECONDS = 60  # Cleanup tokens 60s before expiry

# IMAP
OUTLOOK_IMAP_HOST = "outlook.office365.com"
OUTLOOK_IMAP_PORT = 993

# Error messages
ERROR_GENERIC = "An error occurred"
ERROR_IMAP = "IMAP error"
ERROR_INVALID_CREDENTIALS = "Invalid credentials"
ERROR_TOKEN_EXCHANGE = "Token exchange failed"

