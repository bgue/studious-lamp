"""Identifiers only the server may set on a command (ADR-0014; security review of P1-I3).

A publication or a compensation of derived data is told apart in the ledger by its correlation id
and its event source. A client that could set either could make its own events look like part of a
publication (and have them read back as one). So a correlation id that starts with ``derive:``,
a causation id that starts with it, and a source that starts with ``import:derived-`` or
``compensation:`` are the module's alone: a client command that carries one is refused. The module
builds them itself, after the client's command has been checked, so its own calls are untouched.
Compensation does not trust them in any case: it reverses the ids a publication recorded.
"""

from __future__ import annotations

from tl_core.services.commands import Command
from tl_core.services.errors import ReservedIdentifierError

DERIVE_CORRELATION_PREFIX = "derive:"
RESERVED_SOURCE_PREFIXES = ("import:derived-", "compensation:")


def refuse_reserved(cmd: Command) -> None:
    """Raise ``ReservedIdentifierError`` when a client command carries an identifier it may not."""
    for name in ("correlation_id", "causation_id"):
        value = getattr(cmd, name)
        if isinstance(value, str) and value.startswith(DERIVE_CORRELATION_PREFIX):
            raise ReservedIdentifierError(
                f"{name} may not start with {DERIVE_CORRELATION_PREFIX!r}: the server sets it"
            )
    if cmd.source.startswith(RESERVED_SOURCE_PREFIXES):
        raise ReservedIdentifierError(
            f"source may not start with {' or '.join(map(repr, RESERVED_SOURCE_PREFIXES))}: "
            "the server sets it"
        )
