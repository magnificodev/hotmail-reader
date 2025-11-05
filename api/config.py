"""Configuration management."""

import os
from typing import List
from dotenv import load_dotenv
from pathlib import Path

# Load env from project root and api/.env explicitly
load_dotenv()
try:
    load_dotenv(Path(__file__).with_name(".env"))
except Exception:
    pass


def get_ui_origins() -> List[str]:
    """Get allowed UI origins from environment variable."""
    origin_str = os.environ.get("UI_ORIGIN", "http://localhost:3000")
    # Support comma-separated origins
    origins = [o.strip() for o in origin_str.split(",") if o.strip()]
    return origins if origins else ["http://localhost:3000"]


def get_client_id() -> str:
    """Get OAuth client ID."""
    return os.environ.get("CLIENT_ID") or os.environ.get("GRAPH_CLIENT_ID") or ""


def get_client_secret() -> str:
    """Get OAuth client secret."""
    return os.environ.get("GRAPH_CLIENT_SECRET") or ""


def get_tenant() -> str:
    """Get OAuth tenant."""
    return os.environ.get("GRAPH_TENANT", "consumers")


def get_graph_scope() -> str:
    """Get Graph API scope."""
    return os.environ.get("GRAPH_SCOPE", "offline_access Mail.Read")


def get_oauth_redirect_uri() -> str:
    """Get OAuth redirect URI."""
    return os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8000/oauth/callback")


def get_outlook_scope() -> str:
    """Get Outlook IMAP scope."""
    return os.environ.get(
        "OUTLOOK_SCOPE",
        "offline_access https://outlook.office.com/IMAP.AccessAsUser.All",
    )


def is_development() -> bool:
    """Check if running in development mode."""
    return os.environ.get("NODE_ENV") == "development" or os.environ.get("ENV") == "development"


def get_test_cred_string() -> str:
    """Get test credential string for development."""
    return os.environ.get("TEST_CRED_STRING", "")

