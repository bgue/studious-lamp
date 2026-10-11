"""Sign-in and the caller's own account over HTTP (ADR-0009).

``sign_in`` is a function, not a method: nothing is authenticated yet, so there is no client to
call it on. It answers the session token once; give it to ``ApiClient(base_url, out.token)``.
Failures raise the embedded exception classes (``InvalidCredentialsError``,
``AccountLockedError`` with ``locked_until``, ``AccountDisabledError``). Nothing here logs or
includes a password or a token in an exception text.
"""

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
    client = (
        http if http is not None else httpx2.Client(base_url=base_url.rstrip("/"), timeout=timeout)
    )
    try:
        response = client.post("/auth/sign-in", json={"username": username, "password": password})
    except httpx2.TransportError as exc:
        raise ApiUnavailableError(exc) from exc
    finally:
        if http is None:
            client.close()
    if response.status_code >= 400:
        raise ApiClientBase.error_from(response)
    return SignInOut.model_validate(response.json())


class AuthApi(ApiClientBase):
    def sign_out(self) -> None:
        """End this client's session (``POST /auth/sign-out``, 204)."""
        self._send("POST", "/auth/sign-out")

    def whoami(self) -> Principal:
        """Who the token belongs to (``GET /auth/me``)."""
        return self._model(Principal, self._get_json("/auth/me"))

    def change_own_password(self, current_password: str, new_password: str) -> None:
        """Change your own password (``POST /auth/password``, 204). Every session then ends."""
        self._send(
            "POST",
            "/auth/password",
            json={"current_password": current_password, "new_password": new_password},
        )
