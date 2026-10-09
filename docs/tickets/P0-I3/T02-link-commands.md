# P0-I3-T02 — Link command handlers

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I3-T01, P0-I3-T03 (merged into the base of this branch)
Branch: `p0/i3-t02-link-commands`

## Goal
The nine handlers in `tl_core/services/links.py` create links (`AddLink`, `SuggestLink`), move them through their lifecycle (`AcceptLink`,
`DeclineLink`, `RepinLink`, `VerifyLink`, `FlagLink`, `RetractLink`) and flag links stale when a new revision is issued (`MarkPinsStale`). The
command models, SQL constants and signatures exist; the nine bodies raise `NotImplementedError`. A provided test file (38 tests) must pass.

## Brief references (pasted)
> **7.1** A link has its own lifecycle. Fields: `from`, `to`, `relation` (from the vocabulary), `pin` (a specific revision, or floating), `note`, `source`, `confidence` (suggested links), `status` (`suggested`, `active`, `stale`, `broken`, `retracted`), `verified_by/at`. Events: `Link.Suggested`, `Link.Added`, `Link.Accepted/Declined`, `Link.Repinned`, `Link.Verified`, `Link.Flagged`, `Link.Retracted`. **Links are never deleted.**
> **7.3** Revision pins: when a new revision is issued, pinned links go `stale`. Suggested links wait for accept or decline; **declines are remembered, so the same suggestion does not come back**. Retract, never delete, with a reason.
> **3** Cross-project links are allowed only to company-scope records.

### Specification (the provided test checks it)
A link is its own ledger stream: `stream_id = link_id` (a new ULID, `new_ulid()`), `stream_type = "core.Link"`, `scope` = the command's scope (which is the scope of the `from` record). Every handler runs inside the open unit of work, never commits, and raises before appending anything when a check fails. Use `uow.append(stream_id=..., stream_type=..., scope=..., expected_version=..., events=[NewEvent(event_type=..., payload=...)], actor=cmd.actor, source=cmd.source, correlation_id=cmd.correlation_id or new_ulid(), causation_id=cmd.causation_id)` and return `CommandResult(stream_id=link_id, key=None, version=result.new_version, events=result.events)`.

**`handle_add_link` / `handle_suggest_link`** share one private helper `_create(uow, cmd, event_type, extra)`; `event_type` is `Link.Added` or `Link.Suggested`; `extra` is `{}` or `{"confidence": cmd.confidence}`. Checks, in this order:
1. Load the `from` record (`_RECORD_SQL`, bound `id`); none raises `RecordNotFoundError(f"no record {id!r}")`. If its `scope != cmd.scope` raise `RecordNotFoundError(f"no record {cmd.from_id!r} in scope {cmd.scope!r}")`.
2. Load the `to` record the same way (no scope comparison).
3. `from_id == to_id` raises `SelfLinkError("a record cannot be linked to itself")`.
4. The `to` record's scope must be `cmd.scope` or `"company"`, else `CrossScopeLinkError(f"{target.key or cmd.to_id} is in {target.scope}; links may only point to the same scope or to company records")`.
5. A voided end raises `RecordVoidedError(f"record {row.key or row.id} is voided and cannot be linked")` (check `from`, then `to`).
6. `relation = cmd.relation or default_relation(source.type, target.type)`; then `get_vocabulary().get(relation)` (raises `UnknownRelationError` for an unknown or inverse code).
7. Rows with the same ends and relation (`_SAME_ENDS_SQL`, bound `from_id`, `to_id`, `relation`): for each row, if the event is `Link.Suggested` and `row.declined` is true raise `SuggestionDeclinedError(f"this suggestion ({relation}) was declined before; add the link by hand instead")`; else if `row.status != "retracted"` raise `DuplicateLinkError(f"a {relation} link already exists between these records ({row.status}, {row.link_id})")`. (A retracted link does not block a new one; a declined suggestion blocks only suggestions.)
8. Append with `expected_version=0` and payload `{"link_id": link_id, "from_ref": cmd.from_id, "to_ref": cmd.to_id, "relation": relation, "pin": cmd.pin, "source": cmd.link_source, "note": cmd.note, **extra}`.

**The six lifecycle handlers** share a private helper `_act(uow, cmd, event_type, payload, *, flag=None, same_pin_is_noop=False)`:
1. Load the link (`_LINK_SQL`, bound `id`); none, or `row.scope != cmd.scope`, raises `LinkNotFoundError(f"no link {cmd.link_id!r} in scope {cmd.scope!r}")`.
2. `next_status(row.status, event_type, flag=flag)` (from `tl_core.links.lifecycle`); it raises `InvalidLinkTransitionError` when the event is not allowed. Call it before anything else is written.
3. With `same_pin_is_noop` (repin only): if `row.status == "active"` and `row.pin == payload["pin"]` raise `NoChangesError(f"link {cmd.link_id} already has that pin")`. (A stale link repinned to the same pin is allowed; it returns to active.)
4. Append with `expected_version = cmd.expected_version if cmd.expected_version is not None else row.version` and payload `{"link_id": cmd.link_id, **payload}`. A wrong `expected_version` makes the ledger raise `ConcurrencyError`; let it propagate.

| Handler | Event | Payload (besides `link_id`) | `_act` options |
|---|---|---|---|
| `handle_accept_link` | `Link.Accepted` | `{"note": cmd.note}` | |
| `handle_decline_link` | `Link.Declined` | `{"reason": cmd.reason}` | |
| `handle_repin_link` | `Link.Repinned` | `{"pin": cmd.pin}` | `same_pin_is_noop=True` |
| `handle_verify_link` | `Link.Verified` | `{"note": cmd.note}` | |
| `handle_flag_link` | `Link.Flagged` | `{"status": cmd.status, "reason": cmd.reason}` | `flag=cmd.status` |
| `handle_retract_link` | `Link.Retracted` | `{"reason": cmd.reason}` | |

**`handle_mark_pins_stale`**: load the record `cmd.record_id` (missing: `RecordNotFoundError(f"no record {id!r}")`; scope differs from `cmd.scope`: `RecordNotFoundError(f"no record {id!r} in scope {cmd.scope!r}")`). Rows from `_PINNED_SQL` (bound `id`, `pin = cmd.current_pin`); none raises `NoChangesError(f"no active link to {target.key or cmd.record_id} has an older pin")`. For each row, in order, append to the **link's** stream (`stream_id=row.link_id`, `scope=row.scope`, `expected_version=row.version`) one `Link.Flagged` with payload `{"link_id": row.link_id, "status": "stale", "reason": f"revision {cmd.current_pin} issued"}`, all with one shared `correlation_id` (`cmd.correlation_id or new_ulid()`). Return `CommandResult(stream_id=cmd.record_id, key=target.key, version=0, events=<all appended events>)`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No SQLite- or Postgres-specific SQL; bound parameters only. pyright is `strict` for `packages/tl-core/src`: annotate `events: list[Event] = []`. ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back what you use (`NewEvent`, `Event`, `next_status`, `get_vocabulary`, `default_relation`, `new_ulid`, `text`, the error classes, `Any`).
- Remove the `STUB (P0-I3-T02)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/services/links.py (existing stub; models and SQL constants are final)
class AddLink(Command):  from_id: str; to_id: str; relation: str | None = None; pin: str | None = None; link_source: LinkSource = "manual"; note: str | None = None
class SuggestLink(AddLink): link_source: LinkSource = "key_detected"; confidence: float | None = Field(default=None, ge=0, le=1)
class _OnLink(Command): link_id: str; expected_version: int | None = None
class AcceptLink(_OnLink): note: str | None = None
class DeclineLink(_OnLink): reason: str | None = None
class RepinLink(_OnLink): pin: str | None = None
class VerifyLink(_OnLink): note: str | None = None
class FlagLink(_OnLink): status: Literal["stale", "broken"]; reason: str      # blank reason rejected by a validator
class RetractLink(_OnLink): reason: str                                      # blank reason rejected by a validator
class MarkPinsStale(Command): record_id: str; current_pin: str
LINK_STREAM_TYPE = "core.Link"
_RECORD_SQL   # SELECT id, key, scope, type, voided FROM cur_core_record WHERE id = :id
_LINK_SQL     # SELECT link_id, scope, status, pin, version, from_id, to_id FROM cur_links WHERE link_id = :id
_SAME_ENDS_SQL  # SELECT link_id, status, declined FROM cur_links WHERE from_id = :from_id AND to_id = :to_id AND relation = :relation
_PINNED_SQL   # SELECT link_id, scope, version FROM cur_links WHERE to_id = :id AND status = 'active' AND pin IS NOT NULL AND pin <> :pin ORDER BY created_at, link_id
def handle_add_link(uow: UnitOfWork, cmd: AddLink) -> CommandResult
def handle_suggest_link(uow: UnitOfWork, cmd: SuggestLink) -> CommandResult
def handle_accept_link / handle_decline_link / handle_repin_link / handle_verify_link / handle_flag_link / handle_retract_link(uow, cmd) -> CommandResult
def handle_mark_pins_stale(uow: UnitOfWork, cmd: MarkPinsStale) -> CommandResult
```
```python
# existing, import and use
from tl_core.links.lifecycle import next_status      # next_status(current, event_type, *, flag=None) -> status; raises InvalidLinkTransitionError
from tl_core.links.provider import get_vocabulary    # get_vocabulary().get(code) -> Relation; raises UnknownRelationError
from tl_core.links.vocabulary import default_relation  # default_relation(from_type, to_type) -> str
from tl_core.util import new_ulid
from tl_core.ledger import Event, NewEvent
from tl_core.services.errors import (CrossScopeLinkError, DuplicateLinkError, LinkNotFoundError, NoChangesError,
    RecordNotFoundError, RecordVoidedError, SelfLinkError, SuggestionDeclinedError)
# Command: actor, source, scope, correlation_id, causation_id.  CommandResult: stream_id, key, version, events.
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/links.py`
- `packages/tl-core/src/tl_core/links/lifecycle.py`
- `packages/tl-core/src/tl_core/services/records.py` (style of a handler; read `handle_void_record`)
- `docs/tickets/P0-I3/provided/test_link_commands.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/services/links.py` (edit)
- `tests/services/test_link_commands.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T02.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_link_commands.py.txt tests/services/test_link_commands.py`
2. Implement `_record`, `_create`, `_act` and the nine handlers; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest tests/services/test_link_commands.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_link_commands.py.txt tests/services/test_link_commands.py
```
Expected: 38 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file (the models, `lifecycle.py`, the projector and `errors.py` are not yours).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
