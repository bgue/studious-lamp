"""Expected failures a screen must show to the user instead of crashing (brief 10.3).

Every `ClientInterface` call may raise one of `CLIENT_ERRORS`. Screens catch that tuple, show
`describe_error(exc)` in the footer or next to the field, and keep their state.
"""

from __future__ import annotations

from pydantic import ValidationError
from tl_api.client.base import ApiUnavailableError
from tl_api.errors import ApiError
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError

# `ApiError` is what the remote client raises for a refusal the server's error table has no class
# for, a rejected request body, or an unreachable server (`ApiUnavailableError`, status 0).
CLIENT_ERRORS: tuple[type[Exception], ...] = (
    ServiceError,
    ConcurrencyError,
    ValidationError,
    ApiError,
)


def describe_error(exc: BaseException) -> str:
    """One line for the user: the service message, or the failing fields of a validation error."""
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
    if isinstance(exc, ApiUnavailableError):
        return "server unreachable; check the connection and try again"
    if isinstance(exc, ConcurrencyError):
        return "this record changed since you opened it; reload and try again"
    return str(exc) or exc.__class__.__name__
