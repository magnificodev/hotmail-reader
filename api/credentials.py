from dataclasses import dataclass


@dataclass
class Credentials:
    email: str
    password: str | None
    refresh_token: str | None
    client_id: str | None


def parse_cred_string(cred_string: str) -> Credentials:
    parts = (cred_string or "").split("|")
    # Ensure we have exactly 4 parts
    parts += [""] * (4 - len(parts))
    email, password, refresh_token, client_id = parts[:4]
    email = email.strip()
    password = password.strip() or None
    refresh_token = refresh_token.strip() or None
    client_id = client_id.strip() or None
    return Credentials(email=email, password=password, refresh_token=refresh_token, client_id=client_id)


def select_provider(creds: Credentials) -> str:
    # Prefer Graph if refresh_token and client_id are present
    if creds.refresh_token and creds.client_id and any(creds.email.endswith(d) for d in ("@hotmail.com", "@outlook.com", "@live.com")):
        return "graph"
    if creds.password:
        return "imap"
    return "invalid"

