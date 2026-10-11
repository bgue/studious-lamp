"""Sign-in, sign-out, who am I, and changing your own password (ADR-0009, brief 11.1).

Thin: one `tl_core.auth` call per route. `POST /auth/sign-in` is the only route that needs no
token (`tl_api.auth.OPEN_PATHS`); every failure is a mapped error (401 `invalid_credentials`, 423
`account_locked`, 403 `account_disabled`, 422 `weak_password`) and no route catches anything. No
body, header, log line or error text may hold a password or a token except the one token that
`sign_in` returns to its caller.

STUB (P1-I0-T03): the function bodies raise NotImplementedError; their decorators, parameters,
annotations and docstrings are final (they make the committed OpenAPI document). Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from tl_core.auth import sessions
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.types import Principal

from tl_api.auth import bearer_token, current_principal, guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["auth"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Me = Annotated[Principal, Depends(current_principal)]
MAX_SECRET = 1024


class SignInBody(BaseModel):
    """Body of ``POST /auth/sign-in``."""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[str, Field(min_length=1, max_length=256)]
    password: Annotated[str, Field(min_length=1, max_length=MAX_SECRET)]


class SignInOut(BaseModel):
    """The session token (shown once), how long it lives, and who it belongs to."""

    token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the session ends.")
    principal: Principal

    def __repr__(self) -> str:
        return f"SignInOut(principal={self.principal.actor!r}, token=<hidden>)"

    __str__ = __repr__


class PasswordBody(BaseModel):
    """Body of ``POST /auth/password``."""

    model_config = ConfigDict(extra="forbid")

    current_password: Annotated[str, Field(min_length=1, max_length=MAX_SECRET)]
    new_password: Annotated[str, Field(min_length=1, max_length=MAX_SECRET)]


@router.post("/auth/sign-in", operation_id="sign_in", response_model=SignInOut)
def sign_in(body: SignInBody, ctx: Ctx) -> SignInOut:
    """Sign in with a username and password; answers a session token for `Authorization: Bearer`.

    The same 401 `invalid_credentials` answers an unknown user and a wrong password. After repeated
    failures the name is locked: 423 `account_locked` with `locked_until`, even for the right
    password. A disabled account answers 403 `account_disabled` only to the right password.
    """
    # STEPS:
    # 1. Call `sessions.sign_in(ctx.backend, username=body.username,
    #    password=body.password)`.
    # 2. Return `SignInOut(token=token,
    #    expires_in=int(sessions.SESSION_TTL.total_seconds()), principal=principal)`.
    # 3. Do not catch anything: the errors are mapped rows.
    raise NotImplementedError


@router.post("/auth/sign-out", operation_id="sign_out", status_code=204)
def sign_out(
    request: Request,
    ctx: Ctx,
    actor: Annotated[str, Depends(guard("auth.sign_out"))],
) -> Response:
    """End the session of the token in `Authorization`. Other tokens (agent, dev) are unaffected."""
    # STEPS:
    # 1. Read the token with `bearer_token(request.scope["headers"])`.
    # 2. When it is not None call `sessions.sign_out(ctx.backend, token=token)` (it
    #    ignores tokens that are not sessions).
    # 3. Return `Response(status_code=204)`.
    raise NotImplementedError


@router.get("/auth/me", operation_id="whoami", response_model=Principal)
def whoami(
    me: Me,
    actor: Annotated[str, Depends(guard("auth.me"))],
) -> Principal:
    """Who the token belongs to: actor, account id, kind, roles and how it authenticated."""
    # STEPS:
    # 1. Return `me`: the dependency already resolved the principal.
    raise NotImplementedError


@router.post("/auth/password", operation_id="change_own_password", status_code=204)
def change_own_password(
    body: PasswordBody,
    me: Me,
    ctx: Ctx,
    actor: Annotated[str, Depends(guard("auth.password"))],
) -> Response:
    """Change your own password. Every session of the account ends, this one included.

    A wrong current password is 401 `invalid_credentials` and counts towards the lockout. Agents
    and dev tokens have no password: 403 `forbidden`.
    """
    # STEPS:
    # 1. If `me.kind == "agent"` or `me.via == "dev_token"` raise `ForbiddenError("this
    #    token has no password to change")`.
    # 2. Call `sessions.change_own_password(ctx.backend, account_id=me.account_id,
    #    current_password=body.current_password, new_password=body.new_password)`.
    # 3. Return `Response(status_code=204)`.
    raise NotImplementedError
