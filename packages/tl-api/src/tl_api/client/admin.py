"""The admin module over HTTP: accounts, roles, passwords and agent tokens (ADR-0009).

Every call needs a token whose account has the ``admin`` role; others get ``ForbiddenError``.
Failures raise the embedded exception classes (``AccountNotFoundError``, ``UsernameTakenError``,
``LastAdminError``, ``WeakPasswordError`` ...). Passwords and tokens never appear in exception
texts. ``issue_agent_token`` returns the token once; it cannot be read back.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_core.auth.types import AccountKind, AccountView, AgentTokenView

from tl_api.client.base import ApiClientBase, quote
from tl_api.routes.admin import IssuedToken


class AdminApi(ApiClientBase):
    def list_accounts(self) -> list[AccountView]:
        """Every account (``GET /admin/accounts``)."""
        return self._models(AccountView, self._get_json("/admin/accounts"))

    def get_account(self, account_id: str) -> AccountView:
        """One account (``GET /admin/accounts/{id}``); the id goes through ``quote``."""
        return self._model(AccountView, self._get_json(f"/admin/accounts/{quote(account_id)}"))

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
        data = self._post_json(
            "/admin/accounts",
            {
                "username": username,
                "display_name": display_name,
                "kind": kind,
                "roles": list(roles),
                "password": password,
            },
        )
        return self._model(AccountView, data)

    def set_roles(
        self,
        account_id: str,
        roles: Sequence[str],
        *,
        reason: str | None = None,
        expected_roles: Sequence[str] | None = None,
    ) -> AccountView:
        """Replace the roles (``PUT /admin/accounts/{id}/roles``).

        ``expected_roles``: the roles read before ``roles`` was computed; a change in between is
        409 ``account_state`` and nothing is written.
        """
        path = f"/admin/accounts/{quote(account_id)}/roles"
        body: dict[str, object] = {"roles": list(roles), "reason": reason}
        if expected_roles is not None:
            body["expected_roles"] = list(expected_roles)
        data = self._send("PUT", path, json=body).json()
        return self._model(AccountView, data)

    def disable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        """Disable an account (``POST /admin/accounts/{id}/disable``)."""
        data = self._post_json(f"/admin/accounts/{quote(account_id)}/disable", {"reason": reason})
        return self._model(AccountView, data)

    def enable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        """Enable an account (``POST /admin/accounts/{id}/enable``)."""
        data = self._post_json(f"/admin/accounts/{quote(account_id)}/enable", {"reason": reason})
        return self._model(AccountView, data)

    def reset_password(self, account_id: str, new_password: str) -> AccountView:
        """Set a new password without the old one (``POST /admin/accounts/{id}/password``)."""
        data = self._post_json(
            f"/admin/accounts/{quote(account_id)}/password", {"new_password": new_password}
        )
        return self._model(AccountView, data)

    def list_agent_tokens(
        self, account_id: str | None = None, *, include_revoked: bool = True
    ) -> list[AgentTokenView]:
        """Agent token metadata (``GET /admin/tokens``)."""
        data = self._get_json(
            "/admin/tokens", {"account_id": account_id, "include_revoked": include_revoked}
        )
        return self._models(AgentTokenView, data)

    def issue_agent_token(
        self, account_id: str, label: str, *, expires_in_days: int | None = 90
    ) -> tuple[AgentTokenView, str]:
        """Issue an agent token (``POST /admin/tokens``, 201). Returns the view and the token."""
        data = self._post_json(
            "/admin/tokens",
            {"account_id": account_id, "label": label, "expires_in_days": expires_in_days},
        )
        issued = self._model(IssuedToken, data)
        return issued.view, issued.token

    def revoke_agent_token(self, token_id: str, *, reason: str | None = None) -> AgentTokenView:
        """Revoke an agent token (``POST /admin/tokens/{id}/revoke``)."""
        data = self._post_json(f"/admin/tokens/{quote(token_id)}/revoke", {"reason": reason})
        return self._model(AgentTokenView, data)
