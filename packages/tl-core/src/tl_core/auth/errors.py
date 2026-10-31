"""Authentication and authorization failures (ADR-0009). Mapped to HTTP in ``tl_api.errors``.

The first seven are the contract's (``types.py``); the next four are ADR-0009 additions; the module
role errors (ADR-0021) come last. No message
ever holds a password, a hash or a token, and the two credential failures read the same whether
the user exists or not.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError

INVALID_CREDENTIALS_MESSAGE = "invalid username or password"


class InvalidCredentialsError(ServiceError):
    """Wrong username or password, or a bad token. One text for every cause (no enumeration)."""

    def __init__(self, message: str = INVALID_CREDENTIALS_MESSAGE) -> None:
        super().__init__(message)


class AccountLockedError(ServiceError):
    """Too many failed sign-ins; ``locked_until`` is the ISO-8601 UTC time the lock ends."""

    def __init__(self, message: str = "too many failed sign-ins", locked_until: str | None = None):
        super().__init__(message)
        self.locked_until = locked_until


class AccountDisabledError(ServiceError): ...  # correct password, but the account is disabled


class ForbiddenError(ServiceError): ...  # the principal may not run this action


class LastAdminError(ServiceError): ...  # the last active admin cannot be disabled or demoted


class WeakPasswordError(ServiceError):
    """The password breaks the policy. ``issues`` says which rules, never the password."""

    def __init__(self, message: str, issues: list[str] | None = None) -> None:
        super().__init__(message)
        self.issues: list[str] = issues if issues is not None else []


class UsernameTakenError(ServiceError): ...  # a username is unique across all account kinds


class AccountNotFoundError(ServiceError): ...  # no account with this id or username


class AgentTokenNotFoundError(ServiceError): ...  # no agent token with this id


class InvalidAccountError(ServiceError): ...  # a username, name, kind, role or label is not valid


class AccountStateError(ServiceError): ...  # already disabled, already revoked, bootstrap refused


class AuthBusyError(ServiceError):
    """Too many password hashes are running at once; nothing was written, try again shortly."""


class UnknownRoleError(ServiceError):
    """A module role that is not a role of the role table (422 ``unknown_role``)."""


class UnknownModuleError(ServiceError):
    """A module name that is not a loaded module (422 ``unknown_module``)."""


class NoSuchGrantError(ServiceError):
    """A revoke of a module role the account does not hold (404 ``no_such_grant``)."""


class NoCompanyRolesError(ServiceError):
    """A ``company`` grant for a module that does not declare ``company_roles`` (422
    ``no_company_roles``)."""


class RoleTableError(ServiceError):
    """``schema/settings/module-roles.yaml`` is unusable: fail closed at load (ADR-0021)."""
