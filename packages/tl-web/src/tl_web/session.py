"""The cookie session of the web client: flags, the Set-Cookie text and the sign-in call.

The cookie value is the same opaque 12-hour session token ``POST /auth/sign-in`` returns. It is
never logged, echoed or put in a redirect; the password never leaves the sign-in handler.
"""

from __future__ import annotations

from tl_api.auth import SESSION_COOKIE
from tl_api.settings import is_loopback
from tl_core.auth.env import dev_tokens_allowed

COOKIE_PATH = "/web"
#: Twelve hours, the session lifetime of ``tl_core.auth.sessions.SESSION_TTL``.
MAX_AGE = 43200


def cookie_flags(host: str, env: str) -> tuple[str, ...]:
    """The attributes of the session cookie for a request to ``host`` under ``TL_ENV`` ``env``.

    ``Secure`` is dropped only for a loopback host in dev, test or ci; every other combination
    (any other host, any other environment, an unset one) keeps it.
    """
    flags = ["HttpOnly", "SameSite=Strict", f"Path={COOKIE_PATH}", f"Max-Age={MAX_AGE}"]
    if not (is_loopback(host) and dev_tokens_allowed(env)):
        flags.append("Secure")
    return tuple(flags)


def session_cookie(token: str, host: str, env: str) -> str:
    """The ``Set-Cookie`` value that starts a session."""
    return "; ".join((f"{SESSION_COOKIE}={token}", *cookie_flags(host, env)))


def expired_cookie(host: str, env: str) -> str:
    """The ``Set-Cookie`` value that ends the cookie now (same path and flags, so it matches)."""
    flags = [f for f in cookie_flags(host, env) if not f.startswith("Max-Age=")]
    return "; ".join(
        (f"{SESSION_COOKIE}=", *flags, "Max-Age=0", "Expires=Thu, 01 Jan 1970 00:00:00 GMT")
    )
