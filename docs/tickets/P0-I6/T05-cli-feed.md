# P0-I6-T05 — `tl feed post|ls|retract|react`

Status: ready
Tier: haiku
Labels: cli
Depends on: P0-I6-T01, P0-I6-T02 (both merged on the base before dispatch)
Branch: `p0/i6a-t05-cli-feed`

## Goal
The `tl feed` command group exists: `post` posts to a project feed, `ls` lists it, `retract` and `react` act on a post. Each subcommand
parses options, makes one call into `tl_core.services`, and prints. The module has the option declarations, the helpers and the wiring
in `main.py`; `item_line` and the four commands raise `NotImplementedError`. A provided test file (12 tests) must pass.

## Brief references (pasted)
> **21.1** Posts are ledger events (`Feed.Posted`, `Feed.Edited`, `Feed.Retracted`). Retractions leave a tombstone. Reactions are limited to `ack`, `+1`, `resolved`.
> **21.2** `#NCR-P123-0042` is a record reference: a suggested `references` link is made and the post appears in that record's feed. `#safety #hold ...` are signal tags. `@party:acme-nde` is a mention.
> **21.3** Feeds: Project, Record (with linked records one hop away, toggle), Hashtag/topic/code.
> Build spec 02: the CLI contains no rules. Errors print `error: <message>` on stderr and exit 1 (see `tl_cli/link.py`).

### Specification
The stub's docstrings give the exact output of each command; `item_line` formats one line of `ls`. The provided test checks all of it.
`ctx.obj` is the ledger path (`Path`), set by the root callback. Project `P123` means scope `project:P123`. The default actor is `user:dev`,
the source is `cli`.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/P0-I6-T05.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from every docstring you fill in.
- Follow `tl_cli/link.py`: `_service_errors()` turns `ServiceError`, `ConcurrencyError` and pydantic `ValidationError` into `error:` and exit 1; `typer.testing.CliRunner` keeps stderr separate (`result.stderr`).
- ruff's autofix removed the unused imports of the stub; add back the ones you use (`handle_post`, `PostToFeed`, `list_feed`, ...).

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/feed.py (existing stub; the option declarations are final)
"""The `tl feed` group: post, list, retract and react (P0-I6-T05; brief 21).

STUB (P0-I6-T05): ``item_line`` and the four commands raise NotImplementedError.

Each subcommand parses options, makes one call into `tl_core.services`, and prints. Rules (tag
parsing, link suggestions, tombstones, reactions) live in the services. A post is named by the id
that `post` and `ls` print.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_core.feed.types import FeedItem
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.services.feed_queries import FeedPage

app = typer.Typer(
    help="Post to the project feed, list it, retract a post, react.", no_args_is_help=True
)

_DEFAULT_ACTOR = "user:dev"
_Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
MAX_LABELS = 3


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1."""
    try:
        yield
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _author(item: FeedItem) -> str:
    name = item.actor.removeprefix("user:")
    return f"{name} !" if item.importance == "high" and not item.retracted else name


def _labels_suffix(item: FeedItem, page: FeedPage) -> str:
    names = [page.labels[r] for r in item.record_ids if r in page.labels]
    if item.item_type != "card" or not names:
        return ""
    more = f" +{len(names) - MAX_LABELS}" if len(names) > MAX_LABELS else ""
    return f" ({', '.join(names[:MAX_LABELS])}{more})"


def item_line(item: FeedItem, page: FeedPage) -> str:
    """``<id>  post  2026-10-09 09:42  mlee !  Spool arrived #hold  [ack 2, +1 1]``.

    Columns are separated by two spaces: the item id, ``item.item_type``, ``item.at`` as ``%Y-%m-%d
    %H:%M``, ``_author(item)``, then the summary followed by ``_labels_suffix(item, page)``, and for
    a post with reactions ``  [<name> <count>, ...]`` sorted by name (``[+1 1, ack 2]``).

    STUB: replace this paragraph and the body (P0-I6-T05).
    """
    raise NotImplementedError


@app.command("post")
def post(
    ctx: typer.Context,
    project: _Project,
    body: Annotated[str, typer.Argument(help="Text of the post, with its #tags and @mentions.")],
    importance: Annotated[
        str, typer.Option("--importance", help="low, normal or high.")
    ] = "normal",
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Post BODY to the project feed. Tagged records get a suggested link.

    ``--importance`` other than low, normal or high: ``_fail`` with ``--importance must be low,
    normal or high, not 'x'``. Open a write unit of work (``open_uow(db)`` inside
    ``_service_errors``), call ``handle_post(uow, PostToFeed(actor=..., source="cli",
    scope=f"project:{project}", body=..., importance=...))``. Print ``posted <post id>``; then, when
    the posted event's payload has tags, ``tags `` and the tags joined by ``, `` as ``#text (kind)``
    (``@text (kind)`` for a mention); then, when the result holds more events than ``Feed.Posted``,
    ``suggested N link`` or ``suggested N links``.

    STUB: replace this paragraph and the body (P0-I6-T05).
    """
    raise NotImplementedError


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    record: Annotated[
        str | None, typer.Option("--record", help="Only items about this record key.")
    ] = None,
    linked: Annotated[
        bool, typer.Option("--linked", help="With --record: also records one link away.")
    ] = False,
    tag: Annotated[
        str | None, typer.Option("--tag", help="A hashtag (hold, area:A12) or @mention.")
    ] = None,
    posts: Annotated[bool, typer.Option("--posts", help="Only posts.")] = False,
    events: Annotated[bool, typer.Option("--events", help="Only event cards.")] = False,
    n: Annotated[int, typer.Option("-n", min=1, help="How many items (newest first).")] = 20,
) -> None:
    """List the feed, newest first.

    ``--posts`` with ``--events``: ``_fail("--posts and --events exclude each other")``.
    ``--linked`` without ``--record``: ``_fail("--linked needs --record")``. In a read-only unit of
    work resolve ``--record`` with ``get_record(uow, scope, key)`` (no record: ``_fail(f"no record
    with key {record!r} in project {project!r}")``), then ``list_feed(uow, scope, record_id=...,
    include_linked=linked, tag=tag, item_type="post" for --posts / "card" for --events / None,
    limit=n)``. Print ``item_line(item, page)`` for each item. Nothing is printed for an empty feed.

    STUB: replace this paragraph and the body (P0-I6-T05).
    """
    raise NotImplementedError


@app.command("retract")
def retract(
    ctx: typer.Context,
    project: _Project,
    post_id: Annotated[str, typer.Argument(help="Post id from `tl feed ls`.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the post is retracted.")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Retract a post. A tombstone stays in the feed; the history stays in the ledger.

    Write unit of work, ``handle_retract_post(uow, RetractPost(actor=..., source="cli",
    scope=f"project:{project}", post_id=..., reason=...))`` inside ``_service_errors``. Print
    ``retracted <post id>``.

    STUB: replace this paragraph and the body (P0-I6-T05).
    """
    raise NotImplementedError


@app.command("react")
def react(
    ctx: typer.Context,
    project: _Project,
    post_id: Annotated[str, typer.Argument(help="Post id from `tl feed ls`.")],
    reaction: Annotated[str, typer.Option("--reaction", help="ack, +1 or resolved.")] = "ack",
    off: Annotated[bool, typer.Option("--off", help="Clear the reaction instead.")] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Set (or with --off clear) the actor's reaction on a post.

    ``--reaction`` other than ack, +1 or resolved: ``_fail("--reaction must be ack, +1 or resolved,
    not 'x'")``. Write unit of work, ``handle_react_to_post(uow, ReactToPost(actor=...,
    source="cli", scope=..., post_id=..., reaction=..., on=not off))`` inside ``_service_errors``.
    Print ``reacted <post id> <reaction>``, or ``cleared <post id> <reaction>`` with ``--off``.

    STUB: replace this paragraph and the body (P0-I6-T05).
    """
    raise NotImplementedError
```
```python
# tl_core.services.feed:       PostToFeed(Command): body: str; importance: "low"|"normal"|"high" = "normal"; post_id: str | None = None
#                              handle_post(uow, cmd) -> CommandResult   (events[0] is Feed.Posted with payload["tags"], one more Link.Suggested per suggested link)
# tl_core.services.feed_actions: RetractPost(Command): post_id, reason, expected_version=None; ReactToPost(Command): post_id, reaction, on=True, expected_version=None
#                              handle_retract_post(uow, cmd), handle_react_to_post(uow, cmd) -> CommandResult
# tl_core.services.feed_queries: list_feed(uow, scope, *, record_id=None, include_linked=False, tag=None, item_type=None, limit=50, before_seq=None) -> FeedPage
#                              FeedPage(items: list[FeedItem], labels: dict[str, str], suggestions, next_before)
# tl_core.feed.types.FeedItem: id, item_type ("post"|"card"), scope, actor, at (datetime), seq, summary, importance, record_ids, tags, event_count, retracted, reactions: dict[str, int]
# tl_core.services.queries.get_record(uow, scope, key) -> dict | None
# Command fields: actor, source, scope, correlation_id=None, causation_id=None.  Errors: tl_core.services.errors.ServiceError and subclasses.
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/feed.py`
- `packages/tl-cli/src/tl_cli/link.py` (style: `_service_errors`, `_fail`, options)
- `docs/tickets/P0-I6/provided/a-test_cli_feed.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/feed.py` (edit)
- `packages/tl-cli/tests/test_cli_feed.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T05.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/a-test_cli_feed.py.txt packages/tl-cli/tests/test_cli_feed.py`
2. Implement `item_line`, then the four commands; delete the STUB paragraphs; add the imports you use.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_feed.py -q
just check
just test
```
Expected: 12 tests pass; `just check` clean; `just test` green.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. Paste the output of `uv run tl --db <tmp> feed ls --project P123` after a post and a record create.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
