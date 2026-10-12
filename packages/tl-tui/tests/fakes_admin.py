"""In-memory accounts and agent tokens for `FakeClient` (P1-I0): the admin group of the client.

It follows the services' rules where they are cheap and uses the services' own helpers for them
(`check_username`, `check_text`, `check_reason`, `check_policy`), so a screen sees the same errors
and messages as the embedded client; `test_embedded_admin.py` runs one script on the fake and on the
embedded client and compares what comes back. Simplified: no password is stored (`reset_password`
clears the lock and ends nothing), no session exists, ids and times are counters and a fixed clock.

``is_admin = False`` makes every call raise ``ForbiddenError`` like the API's 403. ``admin_calls``
records ``(method, arguments)`` with passwords and tokens left out.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from tl_core.auth.errors import (
    AccountNotFoundError,
    AccountStateError,
    AgentTokenNotFoundError,
    ForbiddenError,
    InvalidAccountError,
    LastAdminError,
    UsernameTakenError,
)
from tl_core.auth.names import MAX_DISPLAY_NAME, MAX_LABEL, check_reason, check_text, check_username
from tl_core.auth.password import check_policy
from tl_core.auth.types import AccountKind, AccountView, AgentTokenView, Role

_ADMIN_T0 = datetime(2026, 10, 9, 9, 0, 0, tzinfo=UTC)
_ROLES = ("admin", "user")
MAX_LIVE_TOKENS = 20


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000000Z")


class FakeAdminSupport:
    """Mixin for `FakeClient`: call `_init_admin()` from its `__init__`."""

    def _init_admin(self) -> None:
        self._accounts: dict[str, AccountView] = {}
        self._agent_tokens: list[AgentTokenView] = []
        self._account_seq = 0
        self.is_admin = True  # False: every admin call raises ForbiddenError
        self.admin_calls: list[tuple[str, dict[str, Any]]] = []
        self.last_issued_token: str | None = None

    # --- seeding ----------------------------------------------------------------------------

    def seed_account(
        self,
        username: str,
        *,
        kind: AccountKind = "person",
        roles: Sequence[Role] = ("user",),
        status: str = "active",
        locked_until: str | None = None,
        display_name: str | None = None,
    ) -> AccountView:
        """Add an account without any check (a starting state). Returns it."""
        self._account_seq += 1
        view = AccountView(
            account_id=f"01FAKEACCOUNT{self._account_seq:013d}",
            username=username,
            display_name=display_name or username.title(),
            kind=kind,
            roles=list(roles),
            status="disabled" if status == "disabled" else "active",
            locked_until=locked_until,
            created_at=_stamp(_ADMIN_T0 + timedelta(minutes=self._account_seq)),
            seq=self._account_seq,
        )
        self._accounts[view.account_id] = view
        return view

    # --- helpers ----------------------------------------------------------------------------

    def _gate(self, method: str, **arguments: Any) -> None:
        self.admin_calls.append((method, arguments))
        if not self.is_admin:
            raise ForbiddenError("this action needs the admin role")

    def _account(self, account_id: str) -> AccountView:
        found = self._accounts.get(account_id)
        if found is None:
            raise AccountNotFoundError(f"no account {account_id}")
        return found

    def _put(self, view: AccountView) -> AccountView:
        self._accounts[view.account_id] = view
        return view

    @staticmethod
    def _roles(kind: str, roles: Sequence[str]) -> list[Role]:
        unknown = sorted(set(roles) - set(_ROLES))
        if unknown:
            raise InvalidAccountError(
                f"unknown role {', '.join(unknown)}; roles are admin and user"
            )
        found: list[Role] = [r for r in ("admin", "user") if r in set(roles)]  # type: ignore[misc]
        if not found:
            raise InvalidAccountError("an account needs at least one role")
        if kind != "person" and "admin" in found:
            raise InvalidAccountError(f"a {kind} account cannot hold the admin role")
        return found

    def _last_admin(self, view: AccountView, *, still_admin: bool) -> None:
        if "admin" not in view.roles or view.status != "active" or still_admin:
            return
        others = [
            a
            for a in self._accounts.values()
            if a.account_id != view.account_id and "admin" in a.roles and a.status == "active"
        ]
        if not others:
            raise LastAdminError("the last active admin cannot be disabled or demoted")

    # --- accounts ---------------------------------------------------------------------------

    def list_accounts(self) -> list[AccountView]:
        self._gate("list_accounts")
        return list(self._accounts.values())

    def get_account(self, account_id: str) -> AccountView:
        self._gate("get_account", account_id=account_id)
        return self._account(account_id)

    def create_account(
        self,
        username: str,
        display_name: str,
        *,
        kind: AccountKind = "person",
        roles: Sequence[str] = ("user",),
        password: str | None = None,
    ) -> AccountView:
        self._gate("create_account", username=username, kind=kind, roles=list(roles))
        if password is not None and kind != "agent":
            check_policy(password, username=username)
        name = check_username(username)
        shown = check_text(display_name, what="display name", limit=MAX_DISPLAY_NAME)
        if kind not in ("person", "agent", "sim"):
            raise InvalidAccountError("kind must be person, agent or sim")
        role_list = self._roles(kind, roles)
        if password is not None and kind == "agent":
            raise InvalidAccountError("an agent account has no password; issue it a token")
        if any(a.username == name for a in self._accounts.values()):
            raise UsernameTakenError(f"the username {name!r} is taken")
        return self.seed_account(name, kind=kind, roles=role_list, display_name=shown)

    def set_roles(
        self, account_id: str, roles: Sequence[str], *, reason: str | None = None
    ) -> AccountView:
        self._gate("set_roles", account_id=account_id, roles=list(roles), reason=reason)
        check_reason(reason)
        view = self._account(account_id)
        new_roles = self._roles(view.kind, roles)
        if new_roles == view.roles:
            raise AccountStateError("the account already has these roles")
        self._last_admin(view, still_admin="admin" in new_roles)
        return self._put(view.model_copy(update={"roles": new_roles}))

    def disable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        self._gate("disable_account", account_id=account_id, reason=reason)
        check_reason(reason)
        view = self._account(account_id)
        if view.status == "disabled":
            raise AccountStateError("the account is already disabled")
        self._last_admin(view, still_admin=False)
        return self._put(view.model_copy(update={"status": "disabled"}))

    def enable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        self._gate("enable_account", account_id=account_id, reason=reason)
        check_reason(reason)
        view = self._account(account_id)
        if view.status == "active":
            raise AccountStateError("the account is already active")
        return self._put(view.model_copy(update={"status": "active"}))

    def reset_password(self, account_id: str, new_password: str) -> AccountView:
        self._gate("reset_password", account_id=account_id)
        view = self._account(account_id)
        check_policy(new_password, username=view.username)
        if view.kind == "agent":
            raise InvalidAccountError("an agent account has no password; issue it a token")
        return self._put(view.model_copy(update={"locked_until": None}))

    # --- agent tokens -----------------------------------------------------------------------

    def list_agent_tokens(
        self, account_id: str | None = None, *, include_revoked: bool = True
    ) -> list[AgentTokenView]:
        self._gate("list_agent_tokens", account_id=account_id, include_revoked=include_revoked)
        return [
            t
            for t in self._agent_tokens
            if (account_id is None or t.account_id == account_id)
            and (include_revoked or not t.revoked)
        ]

    def issue_agent_token(
        self, account_id: str, label: str, *, expires_in_days: int | None = 90
    ) -> tuple[AgentTokenView, str]:
        self._gate("issue_agent_token", account_id=account_id, label=label)
        view = self._account(account_id)
        if view.kind != "agent":
            raise InvalidAccountError("only an agent account holds agent tokens")
        if view.status != "active":
            raise AccountStateError("the agent account is disabled")
        name = check_text(label, what="label", limit=MAX_LABEL)
        live = [t for t in self._agent_tokens if t.account_id == account_id and not t.revoked]
        if len(live) >= MAX_LIVE_TOKENS:
            raise AccountStateError(
                f"the agent already has {MAX_LIVE_TOKENS} live tokens; revoke one first"
            )
        number = len(self._agent_tokens) + 1
        expires = (
            None if expires_in_days is None else _stamp(_ADMIN_T0 + timedelta(days=expires_in_days))
        )
        token = AgentTokenView(
            token_id=f"01FAKETOKEN{number:015d}",
            account_id=account_id,
            label=name,
            expires_at=expires,
            revoked=False,
            issued_by="user:fake-admin",
        )
        self._agent_tokens.append(token)
        self.last_issued_token = f"tla_fake{number:040d}"
        return token, self.last_issued_token

    def revoke_agent_token(self, token_id: str, *, reason: str | None = None) -> AgentTokenView:
        self._gate("revoke_agent_token", token_id=token_id, reason=reason)
        check_reason(reason)
        for index, token in enumerate(self._agent_tokens):
            if token.token_id == token_id:
                if token.revoked:
                    raise AccountStateError("the token is already revoked")
                self._agent_tokens[index] = token.model_copy(update={"revoked": True})
                return self._agent_tokens[index]
        raise AgentTokenNotFoundError(f"no agent token {token_id}")
