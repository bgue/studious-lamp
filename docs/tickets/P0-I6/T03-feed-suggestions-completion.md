# P0-I6-T03 — `#hold` suggestions and composer completion

Status: ready
Tier: haiku
Labels: core
Depends on: — (the models are in `feed_queries.py` on the base)
Branch: `p0/i6a-t03-feed-suggestions-completion`

## Goal
`tl_core/services/feed_completion.py` has two read functions: `feed_suggestions` derives the pending "create a constraint?" suggestion
that sits beside a `#hold` post that references a record, and `complete_tags` answers the composer after `#` or `@`. Both raise
`NotImplementedError` now; a provided test file (13 tests) must pass.

## Brief references (pasted)
> **21.2** `#safety #hold #decision #urgent #fyi` are signal tags (`feed.signal_tags`). "Hashtags never mutate records. Any change a tag implies is a proposal ("This post mentions #47-1234-S03 with #hold. Create a constraint on IWP-PIP-0042?"), accepted with one key."
> **21.4** "The composer autocompletes keys, codes, topics, and people on `#` and `@`."
> The suggestion is a stub in Phase 0: it is derived from the post and never stored, and nothing accepts it yet (the review queue arrives with the MCP workstream).

### Specification (the provided test checks it; the docstrings in the stub have the full rules)
`feed_suggestions(uow, items) -> dict[str, list[FeedSuggestion]]`:
- Keep the items that are posts, not retracted, have at least one `record_ids` entry and a tag with `kind == "signal"` whose `tag_key(tag)` (from `tl_core.feed.tags`) is `"hold"`. None: return `{}` without querying.
- Look the keys up once: `SELECT id, key FROM cur_core_record WHERE id IN :ids` (expanding bind parameter), over all record ids of the kept items. A voided record is still looked up.
- For each kept item, in order, and each of its `record_ids` in order, add `FeedSuggestion(item_id=item.id, kind="constraint", record_id=rid, record_key=<key or None>, prompt=f"Create a constraint on {key or rid}?")` under `item.id`.

`complete_tags(uow, scope, sigil, prefix, *, limit=8) -> list[Completion]`: build the lists below, concatenate in this order, return the first `limit`.
- Prefix pattern: lower-case the prefix, escape `\`, `%` and `_` with a backslash (the backslash first), append `%`; use it with `LIKE :p ESCAPE '\'` (in the Python source the SQL text holds `ESCAPE '\\'`, a single backslash in SQL).
- `#`:
  1. Records: `SELECT key, title FROM cur_core_record WHERE scope IN (:scope, 'company') AND voided = :no AND key IS NOT NULL AND LOWER(key) LIKE :p ESCAPE '\' ORDER BY key LIMIT :limit` (`:no` bound `False`). `Completion(key, "record", title)`.
  2. Signal tags from `signal_tags()` (`tl_core.feed.config`) whose lower-case form starts with the lower-case prefix, in that order: `Completion(word, "signal", "signal tag")`.
  3. Used codes and topics: `SELECT tag_key, kind, COUNT(*) AS n FROM cur_feed_tags WHERE scope = :scope AND kind IN ('code', 'topic') AND tag_key LIKE :p ESCAPE '\' GROUP BY tag_key, kind ORDER BY n DESC, tag_key LIMIT :limit`. `Completion(tag_key, kind, "used 3 times")`, or `"used 1 time"` for one.
- `@`:
  1. Used mentions: the same query with `kind IN ('mention')`, `Completion(tag_key, "mention", "used N times")`.
  2. Authors: `SELECT DISTINCT actor FROM cur_feed_items WHERE scope = :scope AND item_type = 'post' ORDER BY actor`. `user:jsmith` becomes text `jsmith`, detail `person`; `agent:triage` stays `agent:triage`, detail `agent`; other actors (`svc:`) are skipped. Keep an author whose text, lower-cased, starts with the lower-cased prefix and is not already listed (compare lower-cased texts). `Completion(text, "mention", detail)`.

Learnings that apply:
- pyright is `strict` for `packages/tl-core/src`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt` and you copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/<ticket id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. No SQLite- or Postgres-specific SQL: bound parameters only, fixed SQL text (AGENTS.md rule 5).
- Remove the `STUB` paragraph from every docstring you fill in.
- Expanding bind parameters: `text(sql).bindparams(bindparam("ids", expanding=True))`.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/services/feed_completion.py (existing stub)
from collections.abc import Sequence
from typing import Literal

from tl_core.feed.types import FeedItem
from tl_core.services.feed_queries import Completion, FeedSuggestion
from tl_core.uow import UnitOfWork


def feed_suggestions(uow: UnitOfWork, items: Sequence[FeedItem]) -> dict[str, list[FeedSuggestion]]:
    """Suggestions for the posts among ``items``, keyed by post id.

    A post that is not retracted, has the signal tag ``hold`` and references at least one record
    gets one ``FeedSuggestion`` per referenced record, in the order of ``record_ids``:
    kind ``constraint``, prompt ``Create a constraint on <key>?`` (the record's key, else its id).
    Posts with no suggestion are absent from the result.

    STUB: replace this paragraph and the body (P0-I6-T03).
    """
    raise NotImplementedError


def complete_tags(
    uow: UnitOfWork, scope: str, sigil: Literal["#", "@"], prefix: str, *, limit: int = 8
) -> list[Completion]:
    """Candidates for the composer after ``sigil`` and the typed ``prefix`` (case-insensitive).

    After ``#``, in this order and at most ``limit`` in all:

    1. Records of the scope and the company, never voided, whose key starts with the prefix, by
       key (kind ``record``, detail the title).
    2. Signal tags that start with the prefix, in the order of ``signal_tags()`` (kind ``signal``,
       detail ``signal tag``).
    3. Codes and topics already used in posts of the scope whose lower-cased text starts with the
       prefix, most used first then by text (kind ``code`` or ``topic``, text lower-case, detail
       ``used 3 times`` or ``used 1 time``).

    After ``@``: mentions already used in the scope (most used first, then by text; kind
    ``mention``, text lower-case, detail ``used N times``), then authors of posts in the scope that
    are people or agents: ``user:jsmith`` completes as ``jsmith`` (detail ``person``),
    ``agent:triage`` as ``agent:triage`` (detail ``agent``); ``svc:`` actors are left out. Authors
    already listed as a mention are not repeated. Authors are matched on the text they complete to.

    STUB: replace this paragraph and the body (P0-I6-T03).
    """
    raise NotImplementedError
```
```python
# packages/tl-core/src/tl_core/services/feed_queries.py (read only: the models)
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
```
```python
# tl_core.feed.types.FeedItem (frozen dataclass): id, item_type ("post"|"card"), scope, actor, at, seq, summary, importance,
#   record_ids: tuple[str, ...], tags: tuple[ParsedTag, ...], event_count, retracted: bool, reactions: dict[str, int]
# tl_core.feed.types.ParsedTag: text, kind ("record"|"code"|"signal"|"topic"|"mention"), start, end, namespace, record_id
# tl_core.feed.tags.tag_key(tag) -> tag.text.lower();  tl_core.feed.config.signal_tags() -> ("safety", "hold", "decision", "urgent", "fyi")
```
```sql
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
-- cur_feed_items(item_id, item_type, scope, actor, ...); cur_core_record(id, key, type, scope, title, voided, ...)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/feed_completion.py`
- `packages/tl-core/src/tl_core/services/feed_queries.py`
- `packages/tl-core/src/tl_core/services/link_queries.py` (see `_like` and the LIKE/ESCAPE style)
- `docs/tickets/P0-I6/provided/a-test_feed_completion.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/services/feed_completion.py` (edit)
- `tests/services/test_feed_completion.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T03.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/a-test_feed_completion.py.txt tests/services/test_feed_completion.py`
2. Implement the two functions (and a private prefix-pattern helper); delete the STUB paragraphs; add the imports you use.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest tests/services/test_feed_completion.py -q
just check
just test
```
Expected: 13 tests pass; `just check` clean; `just test` green.

## Tests to add
None beyond the provided file. (The provided test file imports `get_post` and `list_feed` from `feed_queries`; the first test run on the bare base fails on `NotImplementedError` there, which is why T02 and T03 are verified together after both merge. `feed_completion` itself does not call them.)

## Report requirements
Standard report.

## Escalation triggers
- Stop and report *Blocked* if the test needs `get_post` or `list_feed` to work to pass tests of *your* functions: report which test. (The reviewer will run the file on a base that has T02 merged.)

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
