from dataclasses import dataclass


@dataclass
class Credentials:
    email: str
    password: str | None
    refresh_token: str | None
    client_id: str | None


def parse_cred_string(cred_string: str) -> Credentials:
    parts = (cred_string or "").split("|")
    # Ensure at least 4 slots
    parts += [""] * (4 - len(parts))

    first, p2, p3, p4 = (parts[:4])
    first = (first or "").strip()
    p2 = (p2 or "").strip()
    p3 = (p3 or "").strip()
    p4 = (p4 or "").strip()

    email = first
    password: str | None = p2 or None
    refresh_token: str | None = p3 or None
    client_id: str | None = p4 or None

    # Support formats:
    # 1) email|password|refresh|client (chuẩn)
    # 2) email password|refresh|client (thiếu | giữa email và password)
    # 3) email password|... (khi p2 rỗng) – đã hỗ trợ trước đây

    if " " in first:
        email_part, _, maybe_pass = first.partition(" ")
        maybe_pass = maybe_pass.strip()
        if email_part:
            email = email_part.strip()
            if maybe_pass:
                if not p2:
                    # Case 3: email password|... (p2 rỗng)
                    password = maybe_pass
                else:
                    # Case 2: email password|refresh|client → shift right
                    # p2 is actually refresh_token, p3 is client_id
                    password = maybe_pass
                    if p2:
                        # shift p2 → refresh_token
                        refresh_token = p2
                    if p3 and not p4:
                        # shift p3 → client_id when p4 empty
                        client_id = p3

    # Normalize empties to None
    password = (password or "").strip() or None
    refresh_token = (refresh_token or "").strip() or None
    client_id = (client_id or "").strip() or None

    return Credentials(email=email, password=password, refresh_token=refresh_token, client_id=client_id)


def select_provider(creds: Credentials) -> str:
    """
    Determine which provider to use based on credentials.
    Returns: "outlook_graph", "outlook_imap", or "invalid"
    
    Note: We start with Graph API preference, but the actual provider will be
    auto-detected based on the token scope during token exchange.
    """
    # If has OAuth credentials (refresh_token + client_id), prefer Graph API initially
    # The actual provider (Graph or IMAP) will be detected based on token exchange result
    if creds.refresh_token and creds.client_id:
        return "outlook_graph"
    
    # If only password, would need IMAP (not implemented here for password-only)
    # For now, OAuth is required
    return "invalid"

