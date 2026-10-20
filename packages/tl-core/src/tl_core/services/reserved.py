"""Identifiers only the server may set on a command (ADR-0014; security review of P1-I3).

A publication or a compensation of derived data is told apart in the ledger by its correlation id
and its event source. A client that could set either could make its own events look like part of a
publication (and have them read back as one). So a correlation id that starts with ``derive:``,
a causation id that starts with it, and a source that starts with ``import:derived-``,
``compensation:`` or ``svc:`` are the module's alone: a client command that carries one is refused.
(``svc:`` is the source of the services of the suite, the schedule worker and the scanner among
them; a module that tells its own events from a person's by that source relies on this.) The module
builds them itself, after the client's command has been checked, so its own calls are untouched.
Compensation does not trust them in any case: it reverses the ids a publication recorded.

P1-I7 (FANOUT D2, ADR-0017) adds the identifiers of automation. A rule, an inbound endpoint, an
action, an enricher and a thread dispatch each stamp their events with a source, a correlation id
and a causation id of their own shape (``inbound:``, ``rule:``, ``action:``, ``enricher:``,
``thread:``, ``dispatch:``); the prefixes are in ``tl_core.integration.contract`` and a client
command that carries one is refused, so no client can pose as an automation.
"""

from __future__ import annotations

from collections.abc import Mapping

from tl_core.integration.contract import (
    RESERVED_CORRELATION_PREFIXES as AUTOMATION_CORRELATION_PREFIXES,
)
from tl_core.integration.contract import RESERVED_SOURCE_PREFIXES as AUTOMATION_SOURCE_PREFIXES
from tl_core.services.commands import Command
from tl_core.services.errors import ReservedIdentifierError, RoleClaimError

DERIVE_CORRELATION_PREFIX = "derive:"
#: Correlation and causation ids a client may not set: the derivation pipeline's and automation's.
#: ``load:`` is the legacy loaders' (P1-I8): a load and its compensation carry one.
RESERVED_CORRELATION_PREFIXES = (
    DERIVE_CORRELATION_PREFIX,
    "load:",
    *AUTOMATION_CORRELATION_PREFIXES,
)
#: Event sources a client may not set: the derivation pipeline's, the suite's services (``svc:``)
#: and automation's.
RESERVED_SOURCE_PREFIXES = (
    "import:derived-",
    "compensation:",
    "svc:",
    "legacy:",
    *AUTOMATION_SOURCE_PREFIXES,
)


def refuse_reserved_fields(
    *, source: object = None, correlation_id: object = None, causation_id: object = None
) -> None:
    """The check on loose values: an API body before it becomes a command, or a command's fields."""
    for name, value in (("correlation_id", correlation_id), ("causation_id", causation_id)):
        if isinstance(value, str) and value.startswith(RESERVED_CORRELATION_PREFIXES):
            listed = " or ".join(map(repr, RESERVED_CORRELATION_PREFIXES))
            raise ReservedIdentifierError(f"{name} may not start with {listed}: the server sets it")
    if isinstance(source, str) and source.startswith(RESERVED_SOURCE_PREFIXES):
        raise ReservedIdentifierError(
            f"source may not start with {' or '.join(map(repr, RESERVED_SOURCE_PREFIXES))}: "
            "the server sets it"
        )


def refuse_reserved(cmd: Command) -> None:
    """Raise ``ReservedIdentifierError`` when a client command carries an identifier it may not."""
    refuse_reserved_fields(
        source=cmd.source, correlation_id=cmd.correlation_id, causation_id=cmd.causation_id
    )


#: The fixed refusal of a client that names workflow roles (ADR-0013, addendum P1-SEC1). It never
#: repeats what the client sent.
ROLE_CLAIM_MESSAGE = (
    "workflow roles cannot be claimed; the server derives them from the signed-in account"
)
#: The body key of a claim of workflow roles in a command body. (The accept-proposal body also
#: refuses ``roles``, its old field.)
CLAIMED_ROLE_FIELDS = frozenset({"actor_roles"})


def refuse_role_claim(
    body: Mapping[str, object], fields: frozenset[str] = CLAIMED_ROLE_FIELDS
) -> None:
    """Raise ``RoleClaimError`` when a client body names workflow roles (any of ``fields``)."""
    if not fields.isdisjoint(body):
        raise RoleClaimError(ROLE_CLAIM_MESSAGE)
