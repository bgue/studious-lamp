"""The admin module over HTTP: accounts, roles, passwords and agent tokens (ADR-0009).

Every call needs a token whose account has the ``admin`` role; others get ``ForbiddenError``.
Failures raise the embedded exception classes (``AccountNotFoundError``, ``UsernameTakenError``,
``LastAdminError``, ``WeakPasswordError`` ...). Passwords and tokens never appear in exception
texts. ``issue_agent_token`` returns the token once; it cannot be read back.

STUB (P1-I0-T04): the function bodies raise NotImplementedError; their decorators, parameters,
annotations and docstrings are final. Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from collections.abc import Sequence

from tl_core.auth.types import AccountKind, AccountView, AgentTokenView

from tl_api.client.base import ApiClientBase, quote
from tl_api.routes.admin import IssuedToken


class AdminApi(ApiClientBase):
    def list_accounts(self) -> list[AccountView]:
        """Every account (``GET /admin/accounts``)."""
        # STEPS:
        # 1. `return self._models(AccountView, self._get_json("/admin/accounts"))`.
        raise NotImplementedError

    def get_account(self, account_id: str) -> AccountView:
        """One account (``GET /admin/accounts/{id}``); the id goes through ``quote``."""
        # STEPS:
        # 1. `return self._model(AccountView,
        #    self._get_json(f"/admin/accounts/{quote(account_id)}"))`.
        raise NotImplementedError

    def create_account(
        self,
        username: str,
        display_name: str,
        *,
        kind: AccountKind = "person",
        roles: Sequence[str] = ("user",),
        password: str | None = None,
    ) -> AccountView:
        """Create an account (``POST /admin/accounts``, 201)."""
        # STEPS:
        # 1. POST `/admin/accounts` with the body shown in the test: username,
        #    display_name, kind, roles (as a list) and password; decode an
        #    `AccountView`.
        raise NotImplementedError

    def set_roles(
        self, account_id: str, roles: Sequence[str], *, reason: str | None = None
    ) -> AccountView:
        """Replace the roles (``PUT /admin/accounts/{id}/roles``)."""
        # STEPS:
        # 1. `self._send("PUT", path, json={"roles": list(roles), "reason":
        #    reason}).json()`, decode an `AccountView`.
        raise NotImplementedError

    def disable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        """Disable an account (``POST /admin/accounts/{id}/disable``)."""
        # STEPS:
        # 1. POST `.../disable` with `{"reason": reason}`; decode an `AccountView`.
        raise NotImplementedError

    def enable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        """Enable an account (``POST /admin/accounts/{id}/enable``)."""
        # STEPS:
        # 1. POST `.../enable` with `{"reason": reason}`; decode an `AccountView`.
        raise NotImplementedError

    def reset_password(self, account_id: str, new_password: str) -> AccountView:
        """Set a new password without the old one (``POST /admin/accounts/{id}/password``)."""
        # STEPS:
        # 1. POST `.../password` with `{"new_password": new_password}`; decode an
        #    `AccountView`.
        raise NotImplementedError

    def list_agent_tokens(
        self, account_id: str | None = None, *, include_revoked: bool = True
    ) -> list[AgentTokenView]:
        """Agent token metadata (``GET /admin/tokens``)."""
        # STEPS:
        # 1. GET `/admin/tokens` with params `account_id` and `include_revoked`
        #    (`_get_json` drops None); decode with `self._models(AgentTokenView,
        #    data)`.
        raise NotImplementedError

    def issue_agent_token(
        self, account_id: str, label: str, *, expires_in_days: int | None = 90
    ) -> tuple[AgentTokenView, str]:
        """Issue an agent token (``POST /admin/tokens``, 201). Returns the view and the token."""
        # STEPS:
        # 1. POST `/admin/tokens` with `account_id`, `label`, `expires_in_days`;
        #    decode `IssuedToken` and return `(issued.view, issued.token)`.
        raise NotImplementedError

    def revoke_agent_token(self, token_id: str, *, reason: str | None = None) -> AgentTokenView:
        """Revoke an agent token (``POST /admin/tokens/{id}/revoke``)."""
        # STEPS:
        # 1. POST `/admin/tokens/{quote(token_id)}/revoke` with `{"reason": reason}`;
        #    decode an `AgentTokenView`.
        raise NotImplementedError
