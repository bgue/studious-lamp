# P0-I6-T04 — Feed pane widget

Status: ready
Tier: haiku
Labels: tui
Depends on: — (the `ClientInterface` feed methods, the fake and the stub are on the base)
Branch: `p0/i6a-t04-feed-pane`

## Goal
`tl_tui/widgets/feed_pane.py` shows the activity feed (sketch 6): posts with highlighted `#tags`, event cards as one line, reactions and
the `#hold` suggestion, a tab strip (All, Posts, Events, #hold), and the keys `j/k`, `Enter`/`o`, `p`, `.`. The module has its
constants, the `PostRequested` message, the `FeedPane` constructor and bindings; the pure text functions and the methods raise
`NotImplementedError`. Two provided test files (19 tests and one snapshot) must pass. The app wiring (the `F` and `p` keys) is not part of
this ticket.

## Brief references (pasted)
> **21.4 Feed UX (TUI):** Feed pane (side panel or tab): `j/k` move, `Enter` open, `p` new post, `t` open thread, `f` follow, `.` react, `o` open first referenced record, `R` add to tray. Mouse: click any `#tag`, `@mention`, or key. The composer autocompletes keys, codes, topics, and people on `#` and `@`.
> **21.1** Items: an **event card** ("Jo recorded 14 welds on ISO-1234 Rev C"), a **post** (human, agent, or external-party authored). Reactions are `ack`, `+1`, `resolved`. Retractions leave a tombstone.
> **21.2** `#hold` on a post that references a record is a proposal ("Create a constraint on IWP-PIP-0042?"). Hashtags never mutate records.

Sketch 6 (the layout to follow; ours has no box frame, the pane fills its area):
```text
┌─ Feed · P123 · following ───────────── [All] Posts Events #hold ─┐
│ mlee · 09:42                                                     │
│ Spool arrived with damaged bevels #47-1234-S03 #hold             │
│ @party:fab-a  [photo ×2]                                         │
│   ack 3 · proposal: constraint on IWP-0042 [a] · thread ▸ [t]    │
│ ───────────────────────────────────────────────────────────────  │
│ ▤ jsmith recorded 14 welds on ISO-1234 rC · 09:15                │
│ ▤ SLC-IWP-0042 model slice updated · 14 objects changed          │
│ ───────────────────────────────────────────────────────────────  │
│ agent:triage ⚙ · 08:51                                           │
│ Classified 3 incoming letters → Technical (2), Quality (1)       │
│ p post · . react · o open · t open thread · f follow · j/k move  │
└──────────────────────────────────────────────────────────────────┘
```

Learnings that apply:
- pyright is `standard` for `packages/tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/P0-I6-T04.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. No business logic in the TUI: the pane calls `ClientInterface` and shows what comes back (AGENTS.md).
- `Static`, `OptionList` prompts and `DataTable` cells given a plain `str` are parsed as Rich markup, so `[x]` in a post vanished (L-P0-I3-7). Use `rich.text.Text(...)` for option text and `Static(..., markup=False)`.
- Do not name an attribute after a Textual DOM property (`visible`, `region`, `size`, ...); `self.items` and `self.labels` are fine (L-P0-I2-B4).
- Tests drive the app with `helpers.run_pilot(app, scenario)` and assert on `screen_text(app)`; there is no async pytest plugin (L-P0-I2-B2). `from fakes import FakeClient` works inside the tests directory (L-P0-I2-B1).
- The pane's own bindings fire when its option list has focus: Textual bubbles key events up to ancestors' bindings. `Enter` is the option list's own binding: handle `OptionList.OptionSelected` instead.
- Snapshot test: run `uv run pytest packages/tl-tui/tests/test_snapshots_feed.py --snapshot-update` once, check the report looks right (a header line, three entries), and commit the generated `__snapshots__/test_snapshots_feed/` directory. Allowed paths include it.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/client.py: the feed part of ClientInterface (final)
    # --- feed (P0-I6; brief 21) ---------------------------------------------------------------

    def feed_page(
        self,
        scope: str,
        *,
        record_id: str | None = None,
        include_linked: bool = False,
        tag: str | None = None,
        item_type: Literal["post", "card"] | None = None,
        limit: int = 50,
        before_seq: int | None = None,
    ) -> FeedPage:
        """Posts and cards of a project, newest first, with record labels and `#hold` suggestions.

        ``record_id`` narrows to a record's feed (``include_linked``: and the records one link
        away); ``tag`` to a hashtag (``hold``, ``area:A12``) or a mention (``@party:fab-a``);
        ``item_type`` to posts or cards. ``before_seq`` is ``FeedPage.next_before`` of the
        previous page.
        """
        ...

    def feed_post(self, cmd: PostToFeed) -> CommandResult:
        """Post to the project feed; resolved record tags get a suggested `references` link."""
        ...

    def feed_edit(self, cmd: EditPost) -> CommandResult: ...

    def feed_retract(self, cmd: RetractPost) -> CommandResult: ...

    def feed_react(self, cmd: ReactToPost) -> CommandResult: ...

    def feed_complete(
        self, scope: str, sigil: Literal["#", "@"], prefix: str, *, limit: int = 8
    ) -> list[Completion]:
        """Composer candidates after ``#`` (keys, signal tags, codes, topics) or ``@`` (people)."""
        ...
```
```python
# tl_core.feed.types (frozen)
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
# tl_core.services.feed_queries (final models)
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
# tl_core.services.feed_actions.ReactToPost(Command): post_id: str; reaction: Reaction; on: bool = True; expected_version: int | None = None
#   Command fields: actor, source, scope, correlation_id=None, causation_id=None
# tl_core.services.errors.NoChangesError (a ServiceError): the client raises it when the actor already has the requested reaction state
# tl_tui.errors: CLIENT_ERRORS (tuple of exception types), describe_error(exc) -> str
# tl_tui.messages: OpenRecord(scope, key, *, follow=False), StatusMessage(text, severity="info"|"warning"|"error")
# ClientInterface.get_record_by_id(record_id) -> dict | None   (keys include "scope", "key")
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/feed_pane.py` (the stub, with the full specification in its docstrings)
- `packages/tl-tui/src/tl_tui/widgets/links_tab.py` (style of a widget with keys and client errors)
- `packages/tl-tui/tests/fakes_feed.py` (what the fake does)
- `docs/tickets/P0-I6/provided/a-test_feed_pane.py.txt`
- `docs/tickets/P0-I6/provided/a-test_snapshots_feed.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/feed_pane.py` (edit)
- `packages/tl-tui/tests/test_feed_pane.py` (create: byte-for-byte copy of the provided file)
- `packages/tl-tui/tests/test_snapshots_feed.py` (create: byte-for-byte copy of the provided file)
- `packages/tl-tui/tests/__snapshots__/test_snapshots_feed/` (create: the generated snapshot)
- `docs/reports/P0-I6/P0-I6-T04.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/a-test_feed_pane.py.txt packages/tl-tui/tests/test_feed_pane.py` and the same for `a-test_snapshots_feed.py.txt` to `test_snapshots_feed.py`.
2. Implement the pure functions first (the first tests of the file check them), then the widget; delete the STUB paragraphs; add the imports you use.
3. Generate the snapshot, run the acceptance commands, write the report, commit everything.

## Acceptance
```
uv run pytest packages/tl-tui/tests/test_feed_pane.py packages/tl-tui/tests/test_snapshots_feed.py -q
just check
just test-tui
```
Expected: 19 tests and 1 snapshot pass; `just check` clean; `just test-tui` green.

## Tests to add
None beyond the provided files.

## Report requirements
Standard report. Say what the snapshot shows (one sentence).

## Escalation triggers
- Stop and report *Blocked* if a pasted interface disagrees with the repo, or a test cannot pass without editing a file outside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
