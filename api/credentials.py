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
    # Handle accidental format: "email password|refresh|client" or "email password|..."
    if not password:
        # If first part contains whitespace, try splitting into email and password
        if " " in email:
            email_part, _, maybe_pass = email.partition(" ")
            if email_part and maybe_pass:
                email = email_part.strip()
                password = maybe_pass.strip()
    password = password.strip() or None
    refresh_token = refresh_token.strip() or None
    client_id = client_id.strip() or None
    return Credentials(email=email, password=password, refresh_token=refresh_token, client_id=client_id)


def select_provider(creds: Credentials) -> str:
    # Ưu tiên Outlook IMAP XOAUTH2 theo yêu cầu hiện tại
    if creds.refresh_token and creds.client_id:
        return "outlook_imap"
    return "invalid"

