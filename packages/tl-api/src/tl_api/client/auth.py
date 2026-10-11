"""Sign-in and the caller's own account over HTTP (ADR-0009).

``sign_in`` is a function, not a method: nothing is authenticated yet, so there is no client to
call it on. It answers the session token once; give it to ``ApiClient(base_url, out.token)``.
Failures raise the embedded exception classes (``InvalidCredentialsError``,
``AccountLockedError`` with ``locked_until``, ``AccountDisabledError``). Nothing here logs or
includes a password or a token in an exception text.

STUB (P1-I0-T03): the function bodies raise NotImplementedError; their decorators, parameters,
annotations and docstrings are final. Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

import httpx2
from tl_core.auth.types import Principal

from tl_api.client.base import DEFAULT_TIMEOUT_S, ApiClientBase, ApiUnavailableError
from tl_api.routes.auth import SignInOut


def sign_in(
    base_url: str,
    username: str,
    password: str,
    *,
    http: httpx2.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> SignInOut:
    """``POST /auth/sign-in`` with a username and password.

    Use ``http`` when given (tests pass a Starlette ``TestClient``; like ``ApiClient`` it sends the
    relative path ``/auth/sign-in``), else a client for ``base_url`` that is closed afterwards.
    A response of 400 or above raises ``ApiClientBase.error_from(response)``; a transport failure
    raises ``ApiUnavailableError``.
    """
    # STEPS:
    # 1. Use `http` when given, else build `httpx2.Client(base_url=base_url.rstrip("/"),
    #    timeout=timeout)` and close it in a `finally`.
    # 2. POST the relative path `/auth/sign-in` with `json={"username": username,
    #    "password": password}` and no Authorization header.
    # 3. Wrap `httpx2.TransportError` in `ApiUnavailableError(exc)` (`raise ... from
    #    exc`).
    # 4. For a status of 400 or more `raise ApiClientBase.error_from(response)`.
    # 5. Return `SignInOut.model_validate(response.json())`.
    raise NotImplementedError


class AuthApi(ApiClientBase):
    def sign_out(self) -> None:
        """End this client's session (``POST /auth/sign-out``, 204)."""
        # STEPS:
        # 1. Read the token with `bearer_token(request.scope["headers"])`.
        # 2. When it is not None call `sessions.sign_out(ctx.backend, token=token)`
        #    (it ignores tokens that are not sessions).
        # 3. Return `Response(status_code=204)`.
        raise NotImplementedError

    def whoami(self) -> Principal:
        """Who the token belongs to (``GET /auth/me``)."""
        # STEPS:
        # 1. Return `me`: the dependency already resolved the principal.
        raise NotImplementedError

    def change_own_password(self, current_password: str, new_password: str) -> None:
        """Change your own password (``POST /auth/password``, 204). Every session then ends."""
        # STEPS:
        # 1. If `me.kind == "agent"` or `me.via == "dev_token"` raise
        #    `ForbiddenError("this token has no password to change")`.
        # 2. Call `sessions.change_own_password(ctx.backend, account_id=me.account_id,
        #    current_password=body.current_password, new_password=body.new_password)`.
        # 3. Return `Response(status_code=204)`.
        raise NotImplementedError
