"""Resolving what a command line names: people and record keys (FANOUT D10).

The planner and the dispatch targets share these two functions, so a mention or a key means the
same thing in every verb. Both read in the caller's transaction and write nothing.

* A mention ``jsmith`` is the active account ``jsmith`` (the actor ``user:jsmith``);
  ``agent:planner`` is the active agent account ``planner`` (``agent:planner``). Crews and
  parties do not exist yet (``crew:P-07``, ``party:acme-nde``), nor does an unknown or disabled
  account: ``unknown_mention``.
* A key is looked up exactly in the record's scope, then in ``company`` (the order the composer's
  key chips use). A key no record has is ``unknown_key``; a voided record is ``voided_key``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from tl_core.auth.names import actor_for
from tl_core.auth.queries import find_account
from tl_core.integration.contract import Problem, RecordRef
from tl_core.uow import UnitOfWork

_KEY_SQL = text(
    "SELECT id, key, type, scope, voided, version, last_seq FROM cur_core_record "
    "WHERE key = :key AND scope IN (:scope, 'company')"
)


@dataclass(frozen=True)
class Resolved:
    """What a list of names resolved to: the things found, and a problem for each that was not."""

    found: list[str]
    problems: list[Problem]


def resolve_mentions(uow: UnitOfWork, mentions: list[str]) -> Resolved:
    """Actor strings for mentions as typed (``jsmith``, ``agent:planner``), in order, no repeats."""
    found: list[str] = []
    problems: list[Problem] = []
    for mention in mentions:
        namespace, colon, name = mention.partition(":")
        if colon and namespace == "agent":
            kind, handle = "agent", name
        elif not colon:
            kind, handle = "person", mention
        else:
            problems.append(
                Problem(
                    code="unknown_mention",
                    message=f"@{mention[:60]}: crews and parties cannot be notified yet",
                )
            )
            continue
        account = find_account(uow.conn(), username=handle)
        if (
            account is None
            or account.status != "active"
            or (account.kind == "agent") != (kind == "agent")
        ):
            problems.append(
                Problem(code="unknown_mention", message=f"@{mention[:60]}: no such active account")
            )
            continue
        actor = actor_for(account.kind, account.username)
        if actor not in found:
            found.append(actor)
    return Resolved(found, problems)


def resolve_keys(
    uow: UnitOfWork, scope: str, keys: list[str]
) -> tuple[list[RecordRef], list[Problem]]:
    """The records named by keys, in order, no repeats; a problem for each key that fails."""
    refs: list[RecordRef] = []
    problems: list[Problem] = []
    for key in keys:
        rows = uow.conn().execute(_KEY_SQL, {"key": key, "scope": scope}).all()
        row = next((r for r in rows if r.scope == scope), rows[0] if rows else None)
        if row is None:
            problems.append(Problem(code="unknown_key", message=f"no record {key[:80]!r} here"))
        elif row.voided:
            problems.append(Problem(code="voided_key", message=f"record {key[:80]} is voided"))
        elif all(ref.id != row.id for ref in refs):
            refs.append(
                RecordRef(
                    id=row.id,
                    key=row.key,
                    record_type=row.type,
                    version=int(row.version),
                    seq=int(row.last_seq),
                )
            )
    return refs, problems
