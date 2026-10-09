# P0-I5-T22 — `WebhookFilter.matches_row`

Status: ready
Tier: haiku
Labels: core
Depends on: — (the dataclass, the stub and the provided test are on the base branch)
Branch: `p0/i5b-t22-webhook-filter-match`

## Goal
`WebhookFilter.matches_row(row)` decides whether one outbox row passes a subscription's filter: scope, event types, record ids,
changed fields, workflow transitions, link relations, file slots and hashtags (brief 18.2). Today the stub handles the first three and
raises `NotImplementedError` as soon as one of the other five is set. After this ticket all eight parts work. A provided test file
(31 cases) must pass.

## Brief references (pasted)
> **18.2 Subscription filter model.** Every filter is a LinkML-validated `SubscriptionFilter`. It combines scope, event types (glob, e.g.
> `piping.Weld.*`), record selector (type + query-language expression, or record IDs), changed-fields, transitions, link relations, file
> slots, and hashtags. The same filter language is used in the TUI, the API, and rules.
>
> Example selectors: Field / pset property: "Changes to `Weld.status` or `psets.valve_data.size_in`". Workflow transition:
> "`Document: InReview → Issued`; `TestPackage: * → Passed`". Link relation: "Any `raised against` link added to a `Weld`". File slot:
> "New file in the `mtr` slot of any `Receipt`". Feed / hashtag: "Posts tagged `#safety` in project `P123`".

### Specification (the provided test checks it)
Every part that is set (not `None`) must match; a part that is `None` matches everything. Globs use `glob_match(pattern, text)` from
`tl_core.changefeed.filters` (case-sensitive; `*` and `?`). Implement the five missing parts in `matches_row` (keep the three that exist):

- `changed_fields`: matches when **some** pattern matches **some** entry of `row.changed_fields`, where a pattern matches a field if
  `glob_match(pattern, field)` or the field starts with `pattern + "."` (a parent path matches its children, so `psets.vt` matches
  `psets.vt.result`, but `stat` does not match `status`). A row with no changed fields never matches.
- `transitions`: each entry is `"<from> -> <to>"` (the arrow may also be `→`); use the existing `split_transition(entry)` to get the two
  patterns. The row matches when `row.from_state` and `row.to_state` are both not `None` and **some** entry has
  `glob_match(from_pattern, row.from_state)` and `glob_match(to_pattern, row.to_state)`. A row that is not a transition never matches.
- `link_relations`: some pattern matches some entry of `row.link_relations`; no relations means no match.
- `file_slots`: `row.file_slot` is not `None` and some pattern matches it.
- `hashtags`: compare with `normalise_hashtag` (already defined: lower case, leading `#` removed) on both sides; matches when the two
  sets intersect.

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I5/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- pyright is `strict` for `packages/tl-core/src`; ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv`
  prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into another command.
- A fresh worktree has no workspace packages installed: run `uv sync --all-packages` once before the first test.
- Remove the `STUB (P0-I5-T22)` sentence from the docstring of `matches_row` when you are done.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/webhooks/rows.py
@dataclass(frozen=True)
class OutboxRow:
    seq: int; event_id: str; scope: str; event_type: str; stream_id: str; stream_type: str; stream_version: int
    subject_id: str; actor: str; recorded_at: str; correlation_id: str
    schema_version: int = 1; source: str = ""
    subject_type: str | None = None; subject_key: str | None = None; subject_version: int | None = None
    changed_fields: tuple[str, ...] = ()
    from_state: str | None = None; to_state: str | None = None
    related_ids: tuple[str, ...] = ()
    link_relations: tuple[str, ...] = ()
    file_slot: str | None = None
    hashtags: tuple[str, ...] = ()
    data: Mapping[str, Any] = ...
```
```python
# packages/tl-core/src/tl_core/webhooks/filters.py (existing helpers and the class you edit)
def split_transition(entry: str) -> tuple[str, str]: ...      # "InReview -> Issued" -> ("InReview", "Issued")
def normalise_hashtag(tag: str) -> str: ...                    # "#Safety" -> "safety"

@dataclass(frozen=True)
class WebhookFilter:
    scope_selector: str | None = None
    event_types: tuple[str, ...] | None = None
    record_selector: str | None = None
    record_ids: frozenset[str] | None = None
    changed_fields: tuple[str, ...] | None = None
    transitions: tuple[str, ...] | None = None
    link_relations: tuple[str, ...] | None = None
    file_slots: tuple[str, ...] | None = None
    hashtags: tuple[str, ...] | None = None
    def matches_row(self, row: OutboxRow) -> bool: ...        # you implement the five missing parts
```
```python
# packages/tl-core/src/tl_core/changefeed/filters.py
def glob_match(pattern: str, text: str) -> bool: ...
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/webhooks/filters.py`
- `packages/tl-core/src/tl_core/webhooks/rows.py`
- `docs/tickets/P0-I5/provided/test_webhook_filter_match.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/webhooks/filters.py` (edit: `matches_row` and its docstring only)
- `packages/tl-core/tests/test_webhook_filter_match.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I5/P0-I5-T22.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I5/provided/test_webhook_filter_match.py.txt packages/tl-core/tests/test_webhook_filter_match.py`
2. Replace the `raise NotImplementedError` guard in `matches_row` with the five checks; update the docstring.
3. Run the acceptance commands, write the report, commit the code and the report.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_webhook_filter_match.py -q
just check
just test
diff docs/tickets/P0-I5/provided/test_webhook_filter_match.py.txt packages/tl-core/tests/test_webhook_filter_match.py
```
Expected: 31 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
