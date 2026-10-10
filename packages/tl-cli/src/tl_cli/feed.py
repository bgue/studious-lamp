"""The `tl feed` group: post, list, retract and react (P0-I6-T05; brief 21).

Each subcommand parses options, makes one call into `tl_core.services`, and prints. Rules (tag
parsing, link suggestions, tombstones, reactions) live in the services. A post is named by the id
that `post` and `ls` print.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal, NoReturn, cast

import typer
from pydantic import ValidationError
from tl_adapters.sqlite.uow import open_uow
from tl_core.feed.types import FeedItem, Importance, Reaction
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.services.feed import PostToFeed, handle_post
from tl_core.services.feed_actions import (
    ReactToPost,
    RetractPost,
    handle_react_to_post,
    handle_retract_post,
)
from tl_core.services.feed_queries import FeedPage, list_feed
from tl_core.services.queries import get_record

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
    """
    when = item.at.strftime("%Y-%m-%d %H:%M")
    line = f"{item.id}  {item.item_type}  {when}  {_author(item)}  {item.summary}"
    line += _labels_suffix(item, page)
    if item.item_type == "post" and item.reactions:
        counts = ", ".join(f"{name} {item.reactions[name]}" for name in sorted(item.reactions))
        line += f"  [{counts}]"
    return line


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
    """
    db: Path = ctx.obj
    if importance not in ("low", "normal", "high"):
        _fail(f"--importance must be low, normal or high, not {importance!r}")
    level = cast(Importance, importance)
    with _service_errors(), open_uow(db) as uow:
        result = handle_post(
            uow,
            PostToFeed(
                actor=actor,
                source="cli",
                scope=f"project:{project}",
                body=body,
                importance=level,
            ),
        )
    typer.echo(f"posted {result.stream_id}")
    tags = result.events[0].payload.get("tags") or []
    if tags:
        parts = [
            f"{'@' if tag['kind'] == 'mention' else '#'}{tag['text']} ({tag['kind']})"
            for tag in tags
        ]
        typer.echo(f"tags {', '.join(parts)}")
    suggested = len(result.events) - 1
    if suggested:
        typer.echo(f"suggested {suggested} link" + ("" if suggested == 1 else "s"))


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
    """
    db: Path = ctx.obj
    scope = f"project:{project}"
    if posts and events:
        _fail("--posts and --events exclude each other")
    if linked and record is None:
        _fail("--linked needs --record")
    item_type: Literal["post", "card"] | None = "post" if posts else ("card" if events else None)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        record_id: str | None = None
        if record is not None:
            row = get_record(uow, scope, record)
            if row is None:
                _fail(f"no record with key {record!r} in project {project!r}")
            record_id = str(row["id"])
        page = list_feed(
            uow,
            scope,
            record_id=record_id,
            include_linked=linked,
            tag=tag,
            item_type=item_type,
            limit=n,
        )
    for item in page.items:
        typer.echo(item_line(item, page))


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
    """
    db: Path = ctx.obj
    with _service_errors(), open_uow(db) as uow:
        handle_retract_post(
            uow,
            RetractPost(
                actor=actor,
                source="cli",
                scope=f"project:{project}",
                post_id=post_id,
                reason=reason,
            ),
        )
    typer.echo(f"retracted {post_id}")


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
    """
    db: Path = ctx.obj
    if reaction not in ("ack", "+1", "resolved"):
        _fail(f"--reaction must be ack, +1 or resolved, not {reaction!r}")
    with _service_errors(), open_uow(db) as uow:
        handle_react_to_post(
            uow,
            ReactToPost(
                actor=actor,
                source="cli",
                scope=f"project:{project}",
                post_id=post_id,
                reaction=cast(Reaction, reaction),
                on=not off,
            ),
        )
    verb = "cleared" if off else "reacted"
    typer.echo(f"{verb} {post_id} {reaction}")
