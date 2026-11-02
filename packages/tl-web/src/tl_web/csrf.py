"""CSRF protection for every unsafe ``/web`` route (spec web-client-i1 section 5).

Sign-in has no session and so no token; it is held to the origin check only (``verify_origin``).

The token is ``base64url(HMAC-SHA256(secret, "csrf|" + sha256(session_token)))`` without padding, so
it is tied to one session and cannot be computed without the server secret. A request carries it as
``X-CSRF-Token`` (htmx) or a ``csrf`` form field, compared in constant time, and must also come from
the web's own origin. A missing or foreign one is 403 ``csrf_refused``; the answer never says which
check failed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from collections.abc import Mapping
from urllib.parse import urlsplit

from fastapi import Request
from tl_api.auth import TOKEN_KEY
from tl_api.errors import ApiError
from tl_api.ratelimit import NOT_A_FAILURE_KEY
from tl_core.auth.env import dev_tokens_allowed

MIN_SECRET_BYTES = 32
_generated: bytes | None = None


class WebConfigError(RuntimeError):
    """The web client cannot start with this configuration. The text never holds the secret."""


def load_secret(env: Mapping[str, str]) -> bytes:
    """``TL_WEB_SECRET`` (at least 32 bytes), or one generated per process in dev, test and ci."""
    global _generated
    raw = env.get("TL_WEB_SECRET", "")
    if raw:
        secret = raw.encode("utf-8")
        if len(secret) < MIN_SECRET_BYTES:
            raise WebConfigError(f"TL_WEB_SECRET must be at least {MIN_SECRET_BYTES} bytes")
        return secret
    if not dev_tokens_allowed(env):
        raise WebConfigError(
            f"TL_WEB_SECRET (at least {MIN_SECRET_BYTES} bytes) is required outside dev, test, ci"
        )
    if _generated is None:
        _generated = secrets.token_bytes(MIN_SECRET_BYTES)
    return _generated


def csrf_token(session_token: str, secret: bytes) -> str:
    """The CSRF token of one session."""
    digest = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    mac = hmac.new(secret, b"csrf|" + digest.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def _refused() -> ApiError:
    return ApiError(403, "csrf_refused", "the request was refused")


def origin_matches(request: Request) -> bool:
    """``Origin`` (else the origin of ``Referer``) equals ``TL_WEB_ORIGIN``, else our own."""
    seen = request.headers.get("origin")
    if seen is None:
        referer = request.headers.get("referer")
        if referer:
            parts = urlsplit(referer)
            seen = f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None
    if not seen:
        return False
    expected = os.environ.get("TL_WEB_ORIGIN", "").strip().rstrip("/")
    if not expected:
        expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
    return seen.lower() == expected.lower()


async def verify_origin(request: Request) -> None:
    """A FastAPI dependency for sign-in: 403 ``csrf_refused`` unless the request is from our origin.

    There is no session yet, so no token; the origin check still stops a login CSRF (a foreign page
    signing the victim in as the attacker). The refusal is the one ``verify`` gives. No password was
    checked, so the per-source sign-in limit does not count it (a hostile page must not be able to
    use up the victim's budget).
    """
    if not origin_matches(request):
        request.scope[NOT_A_FAILURE_KEY] = True
        raise _refused()


async def verify(request: Request) -> None:
    """A FastAPI dependency: raise 403 ``csrf_refused`` unless the request is ours and signed."""
    session_token = request.scope.get(TOKEN_KEY)
    if not isinstance(session_token, str) or not origin_matches(request):
        raise _refused()
    supplied = request.headers.get("x-csrf-token")
    if supplied is None:
        field = (await request.form()).get("csrf")
        supplied = field if isinstance(field, str) else None
    expected = csrf_token(session_token, request.app.state.web_secret)
    if supplied is None or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode()):
        raise _refused()
