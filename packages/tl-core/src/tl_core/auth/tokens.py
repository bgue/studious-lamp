"""Session and agent token formats (ADR-0009 sections 4 and 5).

A token is a prefix plus 32 random bytes (256 bits), shown once to its holder. Only the SHA-256 of
the token is stored: the token is high entropy, so a fast hash is the right one, and a lookup by
hash is an index equality search. The prefix says which table to look in; it carries no security.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Literal

SESSION_PREFIX = "tls_"
AGENT_PREFIX = "tla_"
TOKEN_BYTES = 32
#: Longest bearer value looked at; anything longer is not one of ours.
MAX_TOKEN_LENGTH = 128

TokenKind = Literal["session", "agent"]


def new_session_token() -> str:
    return SESSION_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)


def new_agent_token() -> str:
    return AGENT_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)


def token_hash(token: str) -> str:
    """Hex SHA-256 of the token's UTF-8 bytes (non-ASCII input hashes fine and matches nothing)."""
    return hashlib.sha256(token.encode("utf-8", "surrogatepass")).hexdigest()


def token_kind(token: str) -> TokenKind | None:
    """Which kind of token this looks like, or ``None`` when it is not one of ours."""
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    if token.startswith(SESSION_PREFIX):
        return "session"
    if token.startswith(AGENT_PREFIX):
        return "agent"
    return None
