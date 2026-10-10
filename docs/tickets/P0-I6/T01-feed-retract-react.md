# P0-I6-T01 — Retract and react handlers

Status: ready
Tier: haiku
Labels: core
Depends on: — (the stubs, `load_post` and the projector are on the base)
Branch: `p0/i6a-t01-feed-retract-react`

## Goal
Two command handlers in `tl_core/services/feed_actions.py` exist and work: `handle_retract_post` appends `Feed.Retracted` and
`handle_react_to_post` appends `Feed.Reacted`, each on the post's own stream and inside the caller's unit of work. The command models
are final; the two handler bodies raise `NotImplementedError`. A provided test file (11 tests) must pass.

## Brief references (pasted)
> **21.1** Posts are ledger events (`Feed.Posted`, `Feed.Edited`, `Feed.Retracted`). Edits keep visible history; retractions leave a tombstone.
> **Reactions** are limited to acknowledgements (`ack`, `+1`, `resolved`), controlled by `feed.reactions.enabled`.

### Specification (the provided test checks it)
- `handle_retract_post(uow, cmd)`:
  1. `post = load_post(uow, cmd.scope, cmd.post_id)` (raises `PostNotFoundError` for an unknown post or another scope).
  2. A post that is already retracted raises `PostRetractedError(f"post {cmd.post_id!r} was already retracted")`.
  3. `uow.append(stream_id=cmd.post_id, stream_type=POST_STREAM_TYPE, scope=cmd.scope, expected_version=<cmd.expected_version if it is not None else post.version>, events=[NewEvent(event_type=FEED_RETRACTED, payload={"post_id": ..., "reason": cmd.reason})], actor=cmd.actor, source=cmd.source, correlation_id=cmd.correlation_id or new_ulid(), causation_id=cmd.causation_id)`. A wrong `expected_version` makes the ledger raise `ConcurrencyError`; let it propagate.
  4. Return `CommandResult(stream_id=cmd.post_id, key=None, version=result.new_version, events=result.events)`.
- `handle_react_to_post(uow, cmd)`:
  1. If `not reactions_enabled()` raise `ReactionsDisabledError("reactions are switched off (feed.reactions.enabled)")`. Call it as the module-level name `reactions_enabled` (the test replaces `feed_actions.reactions_enabled`).
  2. `load_post` as above; a retracted post raises `PostRetractedError`.
  3. `already = cmd.actor in post.reactions.get(cmd.reaction, [])`. If `already == cmd.on` raise `NoChangesError` (setting a reaction that is set, or clearing one that is not set).
  4. Append `Feed.Reacted` with payload `{"post_id": ..., "reaction": cmd.reaction, "on": cmd.on}`, same arguments as retract, and return the same shape of `CommandResult`.
- Handlers never commit and never catch exceptions. Authorisation is not part of Phase 0: anyone may retract or react.

Learnings that apply:
- pyright is `strict` for `packages/tl-core/src`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt` and you copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/<ticket id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. The code must pass on SQLite and on Postgres (the parity suite). No SQLite- or Postgres-specific SQL: bound parameters only, fixed SQL text (AGENTS.md rule 5).
- Remove the `STUB` paragraph from every docstring you fill in.
- Handlers read the projection of the caller's own transaction (`load_post`) and raise before they append, so a refusal leaves nothing written.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/services/feed_actions.py (existing stub; the models are final)
from pydantic import field_validator

from tl_core.feed.types import Reaction
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork


class RetractPost(Command):
    """Retract a post with a reason. ``expected_version`` None: whatever version it has now."""

    post_id: str
    reason: str
    expected_version: int | None = None

    @field_validator("reason")
    @classmethod
    def _reason_given(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class ReactToPost(Command):
    """Set (``on`` true) or clear (``on`` false) the actor's ``reaction`` on a post."""

    post_id: str
    reaction: Reaction
    on: bool = True
    expected_version: int | None = None


def handle_retract_post(uow: UnitOfWork, cmd: RetractPost) -> CommandResult:
    """Append ``Feed.Retracted`` (payload ``post_id``, ``reason``).

    STUB: replace this paragraph and the body (P0-I6-T01). Raises ``PostNotFoundError`` and
    ``PostRetractedError``.
    """
    raise NotImplementedError


def handle_react_to_post(uow: UnitOfWork, cmd: ReactToPost) -> CommandResult:
    """Append ``Feed.Reacted`` (payload ``post_id``, ``reaction``, ``on``).

    STUB: replace this paragraph and the body (P0-I6-T01). Raises ``ReactionsDisabledError``,
    ``PostNotFoundError``, ``PostRetractedError`` and ``NoChangesError``.
    """
    raise NotImplementedError
```
```python
# packages/tl-core/src/tl_core/services/feed.py (read only)
POST_STREAM_TYPE = "core.ActivityPost"

@dataclass(frozen=True)
class PostRow:
    post_id: str; scope: str; author: str; body: str; retracted: bool
    version: int                       # ledger stream_version of the post stream
    base_importance: Importance
    reactions: dict[str, list[str]]    # reaction -> sorted actors

def load_post(uow: UnitOfWork, scope: str, post_id: str) -> PostRow: ...   # raises PostNotFoundError

# tl_core.feed.types: FEED_RETRACTED = "Feed.Retracted"; FEED_REACTED = "Feed.Reacted"; Reaction = Literal["ack", "+1", "resolved"]
# tl_core.feed.config: def reactions_enabled() -> bool
# tl_core.ledger: NewEvent(event_type: str, payload: dict[str, Any]); tl_core.util: new_ulid() -> str
# tl_core.services.commands: Command (actor, source, scope, correlation_id, causation_id), CommandResult(stream_id, key, version, events)
# tl_core.services.errors: PostNotFoundError, PostRetractedError, ReactionsDisabledError, NoChangesError (all ServiceError)
# UnitOfWork.append(**kwargs) -> AppendResult(events, new_version, last_seq)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/feed_actions.py`
- `packages/tl-core/src/tl_core/services/feed.py` (the handler `handle_edit_post` is the model to follow)
- `docs/tickets/P0-I6/provided/a-test_feed_actions.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/services/feed_actions.py` (edit)
- `tests/services/test_feed_actions.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T01.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/a-test_feed_actions.py.txt tests/services/test_feed_actions.py`
2. Fill in the two handlers and add the imports you use; delete the STUB paragraphs.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest tests/services/test_feed_actions.py -q
uv run pytest tests/services/test_feed_actions.py -q --adapters sqlite,postgres
just check
just test
```
Expected (the second run needs the native Postgres, `TL_PG_URL`; the provided tests use `new_db` and run on both): 11 tests pass; `just check` clean; `just test` green.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Say whether `just test` ran in full.

## Escalation triggers
- Stop and report *Blocked* if `load_post` or the projector seems to disagree with the pasted interface.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
