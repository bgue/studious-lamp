# P0-I5-T21 — Markdown catalog page renderer

Status: ready
Tier: haiku
Labels: core, docs
Depends on: — (the stub, `EventTypeInfo` and the provided test are on the base branch)
Branch: `p0/i5b-t21-catalog-markdown`

## Goal
`tl_schema.catalog_markdown.render_catalog_markdown(events, *, title)` renders the browsable event catalog page: an intro, an index table
of every event type, and one section per event type with its facts, a table of ledger payload fields and a sample delivered event. It is a
pure function. The signature exists in the stub; the body raises `NotImplementedError`. A provided test file (11 tests) must pass.

## Brief references (pasted)
> **18.3 Event catalog and envelope.** A browsable, generated **event catalog** is published from it: docs, JSON Schema, sample payloads,
> and AsyncAPI. Payload modes (per subscription): **thin** (envelope + origin only), **delta** (changes + immediate links), **full**
> (the record projection at that version). Payloads always include the originating record URI, the ledger `seq`, and the stream version.

### Specification (the provided test checks it)
Let `ordered = sorted(events, key=lambda e: e.event_type)`; two events with the same `event_type` raise
`ValueError("duplicate event type in the catalog")`. The page is lines joined with `"\n"` and ends with exactly one `"\n"`:

1. `# <title>`, an empty line, then the **intro**: one line, a module constant `INTRO`. It must contain these exact substrings:
   `CloudEvents 1.0`, `Standard Webhooks`, a backtick-quoted list of the three payload modes written as
   `` `thin`, `delta` and `full` `` and the words `dedupe on the event` followed by a backtick-quoted `id`.
   Example text: "Every ledger event type that can reach a webhook subscriber, generated from the LinkML event classes. Each event
   arrives as a CloudEvents 1.0 JSON message signed with Standard Webhooks headers; the payload modes are `thin`, `delta` and `full`.
   Receivers dedupe on the event `id`."
2. An empty line, `## Event types`, an empty line, then either the table or, for no events, the single line `No event types.`
   The table header is `| Event type | CloudEvents type | Summary |` then `|---|---|---|`, then one row per event:
   ``| [`<event_type>`](#<anchor>) | `<ce_type>` | <title> |``. The anchor is `event_type.replace(".", "").lower()`.
3. For each event, in order: an empty line, `## <event_type>`, an empty line, the description (`.strip()`), an empty line, then three
   list lines ``- CloudEvents type: `<ce_type>` ``, ``- Ledger payload class: `<payload_class>` ``, `- Version: <version>`, an empty
   line, `### Payload fields`, an empty line, and then either `No fields.` (no properties) or a table.
   The table header is `| Field | Type | Required | Description |` then `|---|---|---|---|`; one row per property of
   `payload_schema["properties"]`, **sorted by name**: ``| `<name>` | <type> | yes/no | <description> |``.
   * `<type>`: the property's `"type"` if it is a string; a list of types joined with `" or "` (`["string","null"]` gives
     `string or null`); otherwise, if it has `"anyOf"`, the types of the options joined with `" or "`, skipping options without a type
     (`number or null`); otherwise `any`.
   * `yes` when the name is in `payload_schema["required"]` (missing key means none), else `no`.
   * `<description>`: the property's `"description"` (empty when absent) with all whitespace runs, newlines included, collapsed to one
     space and `|` written as `\|`.
4. Then an empty line, `### Sample delivered event`, an empty line, an opening fence line (three backticks followed by `json`), the
   sample envelope as `json.dumps(sample_envelope, indent=2, sort_keys=True)`, and a closing fence line (three backticks).
5. The same events in any order give the same page. Inputs are not modified.

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I5/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- pyright is `strict` for `packages/tl-schema/src`: JSON Schema fragments are `dict[str, Any]`; narrow `Any` values with `isinstance`
  and `typing.cast` rather than leaving partly unknown types. ruff limits lines to 100 columns; run `uv run ruff format` before
  committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into another command.
- A fresh worktree has no workspace packages installed: run `uv sync --all-packages` once before the first test.
- Remove the `STUB (P0-I5-T21)` paragraph from the module docstring when you are done.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-schema/src/tl_schema/catalog_types.py
@dataclass(frozen=True)
class EventTypeInfo:
    event_type: str; version: int; ce_type: str; title: str; description: str; payload_class: str
    payload_schema: dict[str, Any]; envelope_schema: dict[str, Any]
    sample_payload: dict[str, Any]; sample_envelope: dict[str, Any]
```
```python
# packages/tl-schema/src/tl_schema/catalog_markdown.py (stub; the signature is final)
def render_catalog_markdown(
    events: Sequence[EventTypeInfo], *, title: str = "Throughline event catalog"
) -> str: ...
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-schema/src/tl_schema/catalog_markdown.py`
- `packages/tl-schema/src/tl_schema/catalog_types.py`
- `docs/tickets/P0-I5/provided/test_catalog_markdown.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-schema/src/tl_schema/catalog_markdown.py` (edit)
- `packages/tl-schema/tests/test_catalog_markdown.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I5/P0-I5-T21.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I5/provided/test_catalog_markdown.py.txt packages/tl-schema/tests/test_catalog_markdown.py`
2. Implement `render_catalog_markdown` (and small private helpers for the cell text and the type column); delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit the code and the report.

## Acceptance
```
uv run pytest packages/tl-schema/tests/test_catalog_markdown.py -q
just check
just test
diff docs/tickets/P0-I5/provided/test_catalog_markdown.py.txt packages/tl-schema/tests/test_catalog_markdown.py
```
Expected: 11 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

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
