"""Object key validation shared by every backend (P0-I4)."""

from __future__ import annotations

import re

from tl_core.files.errors import InvalidObjectKey

_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*")
CONTENT_PREFIX = "sha256/"


def check_key(key: str) -> str:
    """Return ``key`` when it is a safe relative key, else raise ``InvalidObjectKey``.

    A key is one or more ``/``-separated parts. A part starts with a letter or digit and holds
    letters, digits, ``.``, ``_`` and ``-``. That rules out empty keys, a leading ``/``, ``..`` and
    ``.`` parts, backslashes and spaces, so a key can never leave a backend's root.
    """
    if _KEY.fullmatch(key) is None:
        raise InvalidObjectKey(f"not a valid object key: {key!r}")
    return key


def is_content_key(key: str) -> bool:
    """True for content-addressed keys (``sha256/...``), which are never replaced."""
    return key.startswith(CONTENT_PREFIX)
