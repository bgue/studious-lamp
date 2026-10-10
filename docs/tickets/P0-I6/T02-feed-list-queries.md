# P0-I6-T02 — Feed list queries: `list_feed` and `get_post`

Status: ready
Tier: haiku
Labels: core
Depends on: — (stubs, projector and handlers are on the base)
Branch: `p0/i6a-t02-feed-list-queries`

## Goal
`tl_core/services/feed_queries.py` answers the feed questions of brief 21.3: the feed of a project, of a record (with the one-hop
toggle) and of a hashtag, newest first, in pages, with record labels; and one post by id. The result models exist; `list_feed` and
`get_post` raise `NotImplementedError`. A provided test file (13 tests) must pass.

## Brief references (pasted)
> **21.3 Feeds:** Home, Project, Module, **Record (with linked records one hop away, toggle)**, **Hashtag/topic/code**, Person/crew/party, Saved query.
> **Noise control:** importance levels (system cards low, posts normal, signal tags high); per-feed filters (posts, events, event types).
> **21.1** Event cards are ledger events rendered by templates, aggregated by actor, type and target. Posts: edits keep visible history; **retractions leave a tombstone**.
> **21.2** A record tag "creates a suggested `references` link. The post appears in that record's feed".

### Specification (the provided test checks it)
`list_feed(uow, scope, *, record_id=None, include_linked=False, tag=None, item_type=None, limit=50, before_seq=None) -> FeedPage`
(the full rules are in the stub's docstring; this is how to build it):
1. One SELECT on `cur_feed_items i` with `WHERE` clauses joined by `AND`: `i.scope = :scope`; `i.item_type = :item_type` when given; `i.seq < :before_seq` when given.
2. `record_id`: `i.item_id IN (SELECT t.item_id FROM cur_feed_tags t WHERE t.kind = 'record' AND t.record_id IN :record_ids)` with an expanding bind parameter (`text(...).bindparams(bindparam("record_ids", expanding=True))`). `record_ids` is the record, plus with `include_linked` the records at the other end of its links: `SELECT DISTINCT c.id FROM cur_links l JOIN cur_core_record c ON c.id = CASE WHEN l.from_id = :id THEN l.to_id ELSE l.from_id END WHERE (l.from_id = :id OR l.to_id = :id) AND l.status IN ('active', 'stale', 'broken')`. (A link a post made has a post at one end, which is not in `cur_core_record`, so the join drops it; suggested links are excluded by the status list.)
3. `tag`: strip a leading `#` or `@` and lower-case it for `t.tag_key = :tag_key`; a tag starting with `@` matches `t.kind = 'mention'`, any other matches `t.kind IN ('signal', 'code', 'topic')`. Both as `i.item_id IN (SELECT t.item_id FROM cur_feed_tags t WHERE ...)`.
4. `ORDER BY i.occurred_at DESC, i.seq DESC LIMIT :limit` with `limit + 1` bound, so you can tell whether more follow. Build the SQL string from fixed fragments only; every value is a bound parameter.
5. Build a `FeedItem` per row (select `item_id, item_type, scope, actor, occurred_at, seq, summary, importance, event_count, retracted, reactions_json`), after fetching the tags of all rows in one query: `SELECT item_id, kind, tag_text, namespace, record_id, start_pos, end_pos, seq FROM cur_feed_tags WHERE item_id IN :ids ORDER BY item_id, start_pos, seq, tag_row_id` (expanding bind parameter).
   - `at`: `occurred_at` as a `datetime` (SQLite returns text: `datetime.fromisoformat`; Postgres returns a datetime: keep it).
   - Post: `tags` = one `ParsedTag(text=tag_text, kind=kind, start=start_pos, end=end_pos, namespace=namespace, record_id=record_id)` per tag row in that order; `record_ids` = the `record_id` of its `record` rows, without repeats, in order.
   - Card: `tags=()`; `record_ids` = the `record_id` of its `record` rows without repeats, in order, at most `CARD_SUBJECTS_SHOWN` (20; define this module constant).
   - `summary`: `"[retracted]"` for a retracted row, else the stored summary. `retracted`: `bool`. `reactions`: `{name: len(actors)}` from `json.loads(reactions_json)`, leaving out empty lists. `event_count` and `importance` as stored.
6. `labels`: for the record ids of the returned items, `SELECT id, key, title FROM cur_core_record WHERE id IN :ids` (expanding), mapped to `key or title`. Empty when there are no ids.
7. `next_before` is the last returned item's `seq` when the extra row existed, else `None`. `suggestions` stays empty.

`get_post(uow, scope, post_id) -> FeedItem`: the same row builder for `WHERE i.item_id = :id AND i.item_type = 'post' AND i.scope = :scope`; no row raises `PostNotFoundError(f"no post {post_id!r} in scope {scope!r}")`.

Learnings that apply:
- pyright is `strict` for `packages/tl-core/src`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt` and you copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/<ticket id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. No SQLite- or Postgres-specific SQL: bound parameters only, fixed SQL text (AGENTS.md rule 5).
- Remove the `STUB` paragraph from every docstring you fill in.
- Expanding bind parameters: `text(sql).bindparams(bindparam("ids", expanding=True))`, then pass a list. `sqlalchemy` is already a dependency.
- Rows are `Row` objects: read columns by attribute (`row.item_id`). pyright strict: annotate helper parameters; `Any` is fine for rows.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/feed/types.py (frozen)
TagKind = Literal["record", "code", "signal", "topic", "mention"]
Reaction = Literal["ack", "+1", "resolved"]
Importance = Literal["low", "normal", "high"]

# about:config default (§30 `feed.signal_tags`). Phase 0 reads this constant; settings arrive in
# P0-I8.
DEFAULT_SIGNAL_TAGS: tuple[str, ...] = ("safety", "hold", "decision", "urgent", "fyi")


@dataclass(frozen=True)
class ParsedTag:
    """One `#tag` or `@mention` found in a post body.

    text: as written, without the leading sigil (``47-1234-S03``, ``area:A12``, ``hold``,
      ``party:acme-nde``).
    kind: record (fits a numbering pattern of the scope), code (``ns:value``), signal (in the
      signal set), mention (``@``), otherwise topic. Precedence: mention, record, code, signal,
      topic.
    start, end: character offsets of the whole token including the sigil, for highlighting.
    namespace: for code and mention tags, the part before ``:`` (``area``, ``party``), else None.
    record_id: for a record tag that resolved to an existing record in the scope or company,
      else None.
    """

    text: str
    kind: TagKind
    start: int
    end: int
    namespace: str | None = None
    record_id: str | None = None


@dataclass(frozen=True)
class FeedItem:
    """One row of a feed query: a post or an event card, newest first by ``at`` then ``seq``.

    For a post, ``id`` is the post id; for a card, a deterministic card id derived from its first
    event id. ``event_count`` is 1 for a post; for a card, the number of aggregated ledger events.
    """

    id: str
    item_type: Literal["post", "card"]
    scope: str
    actor: str
    at: datetime
    seq: int
    summary: str  # post body (or "[retracted]") or the card's rendered summary
    importance: Importance
    record_ids: tuple[str, ...] = ()
    tags: tuple[ParsedTag, ...] = ()
    event_count: int = 1
    retracted: bool = False
    reactions: dict[str, int] = field(default_factory=dict[str, int])
```
```python
# packages/tl-core/src/tl_core/services/feed_queries.py (existing stub; the models are final)
from dataclasses import dataclass, field
from typing import Literal

from tl_core.feed.types import FeedItem, TagKind
from tl_core.uow import UnitOfWork

CARD_SUBJECTS_SHOWN = 20  # record ids a card item lists, in the order the events touched them


@dataclass(frozen=True)
class FeedSuggestion:
    """A pending suggestion beside a post: ``#hold`` on a post that references a record offers a
    constraint (brief 21.2). It is derived from the post's tags, never stored, and accepting it is
    not built in Phase 0 (the review queue arrives with the MCP workstream)."""

    item_id: str  # the post
    kind: Literal["constraint"]
    record_id: str
    record_key: str | None
    prompt: str  # "Create a constraint on P123-REC-0042?"


@dataclass(frozen=True)
class FeedPage:
    """One page of a feed, newest first.

    ``labels`` maps every record id the items mention (``FeedItem.record_ids``) to the record's key,
    else its title, so a client can show ``jsmith created 3 records (P1-REC-0001 ...)``.
    ``suggestions`` maps a post id to its suggestions (filled by ``feed_suggestions``, not by
    ``list_feed``). ``next_before`` is the ``before_seq`` for the next page, or None at the end.
    """

    items: list[FeedItem]
    labels: dict[str, str] = field(default_factory=dict[str, str])
    suggestions: dict[str, list[FeedSuggestion]] = field(
        default_factory=dict[str, list[FeedSuggestion]]
    )
    next_before: int | None = None


@dataclass(frozen=True)
class Completion:
    """A candidate for the composer after ``#`` or ``@``. ``text`` has no sigil."""

    text: str
    kind: TagKind
    detail: str  # the record title, "signal tag", "used 3 times", "person", "agent"


def list_feed(
    uow: UnitOfWork,
    scope: str,
    *,
    record_id: str | None = None,
    include_linked: bool = False,
    tag: str | None = None,
    item_type: Literal["post", "card"] | None = None,
    limit: int = 50,
    before_seq: int | None = None,
) -> FeedPage:
    """Feed items of ``scope``, newest first (``occurred_at`` then ``seq``, both descending).

    Filters (all optional, combined with AND):

    * ``item_type``: only posts or only cards.
    * ``record_id``: items about that record (a post that tags it, a card whose events touched it).
      With ``include_linked``, also items about records one link away: links in status active,
      stale or broken, either direction, to a record (suggested and retracted links do not count).
    * ``tag``: a hashtag (``hold``, ``#hold``, ``area:A12``; case-insensitive; matches signal, code
      and topic tags, never mentions) or, with a leading ``@``, a mention (``@party:fab-a``).
    * ``before_seq``: only items with a smaller ``seq`` (the previous page's ``next_before``).

    Retracted posts are listed as tombstones (``retracted`` true, summary ``[retracted]``), except
    in a ``tag`` feed (their non-record tags are gone). ``labels`` maps each record id of the items
    to its key, else its title. ``suggestions`` stays empty (see ``feed_suggestions``).
    ``next_before`` is the last item's ``seq`` when more items follow, else None.

    STUB: replace this paragraph and the body (P0-I6-T02).
    """
    raise NotImplementedError


def get_post(uow: UnitOfWork, scope: str, post_id: str) -> FeedItem:
    """One post as a ``FeedItem`` (with its tags and reaction counts).

    Raises ``PostNotFoundError`` when no post has this id in ``scope``.

    STUB: replace this paragraph and the body (P0-I6-T02).
    """
    raise NotImplementedError
```
```sql
-- generated: packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_feed_items.sql and cur_feed_tags.sql
CREATE TABLE IF NOT EXISTS cur_feed_items (
  item_id TEXT PRIMARY KEY,
  item_type TEXT NOT NULL,
  scope TEXT NOT NULL,
  actor TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  seq INTEGER NOT NULL,
  summary TEXT NOT NULL,
  importance TEXT NOT NULL DEFAULT 'normal',
  base_importance TEXT NOT NULL DEFAULT 'normal',
  event_type TEXT,
  event_count INTEGER NOT NULL DEFAULT 1,
  first_us INTEGER,
  first_seq INTEGER,
  open_scope TEXT,
  retracted INTEGER NOT NULL DEFAULT 0,
  retract_reason TEXT,
  edit_count INTEGER NOT NULL DEFAULT 0,
  reactions_json TEXT NOT NULL DEFAULT '{}',
  version INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_feed_items_open_scope ON cur_feed_items (open_scope);

CREATE INDEX IF NOT EXISTS ix_cur_feed_items_scope ON cur_feed_items (scope);

CREATE INDEX IF NOT EXISTS ix_cur_feed_items_seq ON cur_feed_items (seq);

CREATE TABLE IF NOT EXISTS cur_feed_tags (
  tag_row_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  kind TEXT NOT NULL,
  tag_text TEXT NOT NULL,
  tag_key TEXT NOT NULL,
  namespace TEXT,
  record_id TEXT,
  start_pos INTEGER NOT NULL,
  end_pos INTEGER NOT NULL,
  seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_feed_tags_item_id ON cur_feed_tags (item_id);

CREATE INDEX IF NOT EXISTS ix_cur_feed_tags_tag_key ON cur_feed_tags (tag_key);

CREATE INDEX IF NOT EXISTS ix_cur_feed_tags_record_id ON cur_feed_tags (record_id);
-- cur_links: link_id, scope, from_id, to_id, relation, status ('suggested'|'active'|'stale'|'broken'|'retracted'), ...
-- cur_core_record: id, key, type, scope, title, ...
```
```python
# tl_core.services.errors.PostNotFoundError (a ServiceError); tl_core.uow.UnitOfWork.conn() -> sqlalchemy Connection
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/feed_queries.py`
- `packages/tl-core/src/tl_core/feed/types.py`
- `packages/tl-core/src/tl_core/services/link_queries.py` (style of a query module with expanding parameters)
- `docs/tickets/P0-I6/provided/a-test_feed_queries.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/services/feed_queries.py` (edit)
- `tests/services/test_feed_queries.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T02.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/a-test_feed_queries.py.txt tests/services/test_feed_queries.py`
2. Implement `list_feed`, `get_post` and the private helpers you need; keep the dataclasses as they are.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest tests/services/test_feed_queries.py -q
just check
just test
```
Expected: 13 tests pass; `just check` clean; `just test` green.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. List any query you could not express without dialect-specific SQL (expected: none).

## Escalation triggers
- Stop and report *Blocked* if a pasted table or dataclass disagrees with the repo.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
