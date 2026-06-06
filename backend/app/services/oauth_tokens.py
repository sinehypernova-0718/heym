import hashlib


def hash_oauth_token(token: str) -> str:
    """Return the database-safe hash for an OAuth access or refresh token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def oauth_token_lookup_values(token: str) -> tuple[str, ...]:
    """Accept new hashed-token rows and legacy plaintext rows during rotation."""
    hashed = hash_oauth_token(token)
    if hashed == token:
        return (hashed,)
    return (hashed, token)
