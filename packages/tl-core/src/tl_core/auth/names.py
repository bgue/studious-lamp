"""Usernames, display names and actor strings (ADR-0009 section 1)."""

from __future__ import annotations

import re
import unicodedata

from tl_core.auth.errors import InvalidAccountError
from tl_core.auth.types import AccountKind

USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.@-]{0,63}")
USERNAME_KEY_LENGTH = 64
MAX_DISPLAY_NAME = 120
MAX_LABEL = 80


def normalize_username(raw: str) -> str:
    """NFKC and lower case. Sign-in and account creation both apply it."""
    return unicodedata.normalize("NFKC", raw).lower()


def username_key(raw: str) -> str:
    """The key lockout counters and lookups use: the normalised name cut to 64 characters."""
    return normalize_username(raw)[:USERNAME_KEY_LENGTH]


def check_username(raw: str) -> str:
    """The normalised username, or ``InvalidAccountError``."""
    name = normalize_username(raw)
    if USERNAME_PATTERN.fullmatch(name) is None:
        raise InvalidAccountError(
            "a username is 1 to 64 characters from a-z, 0-9, '_', '.', '@' and '-', "
            "and starts with a letter or digit"
        )
    return name


def check_text(value: str, *, what: str, limit: int) -> str:
    """``value`` stripped, when it is non-empty, short enough and has no control characters."""
    cleaned = value.strip()
    if not cleaned or len(cleaned) > limit:
        raise InvalidAccountError(f"{what} must be 1 to {limit} characters")
    if any(unicodedata.category(ch).startswith("C") for ch in cleaned):
        raise InvalidAccountError(f"{what} must not contain control characters")
    return cleaned


def actor_for(kind: AccountKind, username: str) -> str:
    """``agent:<name>`` for an agent account, else ``user:<name>``."""
    return f"agent:{username}" if kind == "agent" else f"user:{username}"
