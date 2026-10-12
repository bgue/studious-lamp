"""Usernames, display names and actor strings (ADR-0009 section 1)."""

from __future__ import annotations

import re
import unicodedata

from tl_core.auth.errors import InvalidAccountError
from tl_core.auth.password import is_clean
from tl_core.auth.types import AccountKind

USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.@-]{0,63}")
MAX_DISPLAY_NAME = 120
MAX_LABEL = 80
MAX_USERNAME_INPUT = 256


def normalize_username(raw: str) -> str:
    """NFKC and lower case. Sign-in and account creation both apply it."""
    return unicodedata.normalize("NFKC", raw).lower()


#: The one key every input that is not a possible username shares (lockout counters, audit rows).
#: Whatever was typed there may be a password or garbage; it is never stored or compared.
INVALID_KEY = "<invalid>"
MAX_ID = 64
MAX_REASON = 500


def username_key(raw: str) -> str:
    """The key lockout counters, audit rows and lookups use for ``raw``.

    The normalised name when it could be a username, else :data:`INVALID_KEY`. It never holds
    anything that does not match the username pattern, so it is safe to store, and never raises.
    """
    if not is_clean(raw, MAX_USERNAME_INPUT):
        return INVALID_KEY
    name = normalize_username(raw)
    return name if USERNAME_PATTERN.fullmatch(name) is not None else INVALID_KEY


def is_id(value: str) -> bool:
    """Whether ``value`` could be an account or token id (short, storable)."""
    return bool(value) and is_clean(value, MAX_ID)


def check_reason(reason: str | None) -> str | None:
    """A reason: None or blank is None; else short, storable text, or ``InvalidAccountError``."""
    if reason is None or not reason.strip():
        return None
    return check_text(reason, what="reason", limit=MAX_REASON)


def check_username(raw: str) -> str:
    """The normalised username, or ``InvalidAccountError``."""
    if len(raw) > MAX_USERNAME_INPUT:
        raise InvalidAccountError("a username is at most 64 characters")
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
