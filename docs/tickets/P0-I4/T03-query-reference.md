# P0-I4-T03 — Query language reference page

Status: ready
Tier: haiku
Labels: docs
Depends on: — (the parser is on the base branch)
Branch: `p0/i4a-t03-query-reference`

## Goal
`docs/reference/query-language.md` explains the filter language to a person typing into the TUI filter bar, an API client, or an
agent writing an MCP search: fields, operators, values, boolean logic, text search, link terms, dates, errors and limits, with runnable
examples. A provided test file checks that every example parses, every error example fails at the position it states, and every
field and operator is documented.

## Brief references (pasted)
> **10.2 Filter bar.** Structured query builder plus text query language (e.g. `status:open discipline:PIP psets.nde.method=RT due<+7d linked:NCR`).
> **7.5 Follow, query operators** in the shared query language: `linked:NCR`, `linked(raised_against).status:open`, `path(weld>spool>iso).rev:C`,
> `count(linked:NCR)>0`, `missing(link:permit)`.
> **18.2** The same filter language is used in the TUI, the API and rules.

Phase 0 notes: `discipline` and `due` of the brief's example are not fields yet (the record envelope has no such columns); `path(...)` is
not supported yet. Do not invent fields or operators beyond the facts below.

## Facts to document (everything the page may state; check each against the examples)

**Shape.** Terms separated by spaces are ANDed. Blank text means no filter. A term is `field<operator>value`. Field names are not
case-sensitive. An unknown field is an error; to search for text that looks like a field, quote it.

**Fields** (table with columns Field, Type, Meaning; each field name in backticks):
`id` text, record id · `key` text, human-readable number unique within a scope · `type` text, record type such as `piping.Weld` ·
`scope` text, `company` or `project:<id>` · `title` text · `description` text · `status` text, workflow state, empty when the type has
none · `voided` true or false, voided records are left out unless the caller asks · `version` whole number, stream version ·
`last_seq` whole number, ledger sequence of the last event applied · `effective_schema_hash` text · `conformance` text, one of `ok`,
`warning`, `nonconformant`, `waived` · `created_at` date · `updated_at` date.
Pset values: `psets.<pset>.<property>`, `psets.<pset>.x.<property>` (custom section), `psets.prj.<pset>.<property>` (project pset).

**Operators** (table, each operator in backticks): `:` equals (same as `=`) · `=` equals, text compared exactly including case ·
`!=` not equal, also matches records with no value · `~` contains, ignoring case, text only · `<` `<=` `>` `>=` comparisons.
`status!=open` and `-status:open` mean the same.

**Values.** A bare word has no spaces, parentheses or quotes; a quoted string uses `"` or `'`, with `\"` and `\\` as escapes.
Text columns always read the value as text (`key:007` finds the key `007`). Whole-number and true/false columns check the value.
Unquoted `null` means no value (`status:null`, `status!=null`). Pset values are typed from the text: `3` number, `1.5` decimal, `true`
boolean, `+7d` relative date, otherwise text; `007` stays text; quote a value to force text (`psets.a.b:"12"`).

**Boolean logic.** A space or `AND` means both; `OR` means either; `-term` or `NOT term` negates; `NOT` binds tightest, then AND, then
`OR`; parentheses group. `or`, `and`, `not` work in any case; quote a word to search for it.

**Text search.** A word with no field searches key, title and description, ignoring case; several words must all match; a quoted
phrase matches as written; `%` and `_` are ordinary characters.

**Links.** A link is live while its status is `active`, `stale` or `broken` (suggested and retracted links do not count); both
directions count. Terms (table): `linked` any live link · `linked:NCR` a live link to a record of type `NCR` (also `quality.NCR`, ignoring
case) · `linked(raised_against)` that relation (`*` means any) · `linked(raised_against):NCR` relation and type · `linked:NCR.status:open`
the linked record must also match the condition after the dot · `linked(raised_against).(status:open type:NCR)` a group of conditions
after `.(` · `count(linked:NCR)>0` number of matching live links, compared with `=`, `!=`, `<`, `<=`, `>`, `>=` ·
`missing(link:permit)` no live link to a `permit`; `missing(link)` no links at all. `path(a>b>c)` is not supported yet.

**Dates** (`created_at`, `updated_at`; also psets that hold ISO dates for relative dates). Values: `2026-10-09` that day in the project
time zone · `2026-10-09T12:30:00Z` that instant (offsets like `+02:00` work, no offset means UTC) · `today` · `+7d`, `-3d` whole days
ahead or back. A day is a window: `=` inside the day, `<` before it, `<=` before its end, `>` after its end, `>=` from its start.
The project time zone defaults to UTC.

**Errors.** A text that does not parse raises `QuerySyntaxError`; its `position` is the 0-based offset of the first offending
character, so a filter bar can point at it.

**Limits.** At most 2000 characters, nested at most 32 levels, at most 200 terms.

## Required shape of the page (the provided test checks it)
- The first non-blank line is a `# ` title containing the word "query". The first paragraph says what the page is for.
- Level-two headings (`## `) include: `Fields`, `Operators`, `Values`, `Boolean logic`, `Links`, `Dates`, `Errors` (plus `Text search`
  and `Limits`). Use no model names, no TODO or TBD text.
- At least 30 example queries, one per line, inside fences that open with exactly ```` ```query ````. Every example must parse
  (the test calls `parse`), so use only the facts above; do not write an example you have not run. Spread them over the sections.
- At least 8 error examples inside fences that open with exactly ```` ```query-error ````, one per line, written as
  `<query>  # position <n>` (two spaces, `#`, `position`, the 0-based offset). Find each position by running it:
  `uv run python -c "from tl_core.query import parse; parse('status:')"` and reading `QuerySyntaxError.position`
  (add `print(e.position)` in an `except`). Good candidates: `status:` · `(status:open` · `status:open)` · `foo:bar` · `version:abc` ·
  `created_at>soon` · `a OR` · `path(a>b)` · `count(linked:NCR)` · an unterminated quote.
- Every field name appears in backticks (`` `status` ``) and every operator appears in backticks (`` `<=` ``).
- The terms `linked`, `count(`, `missing(`, `OR`, `NOT`, `today`, `+7d` and `psets.` all appear.

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I4/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- Docs rules: lead with what the reader needs; one idea per sentence; tables for parallel facts; commands in fenced blocks; ISO dates;
  no model names. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/query/api.py (the only calls the page's examples go through)
def parse(text: str) -> Expr | None: ...          # blank text gives None; raises QuerySyntaxError
class QuerySyntaxError(ServiceError):             # .position is the 0-based character offset
    def __init__(self, message: str, position: int) -> None: ...
```
The provided test reads `ENVELOPE_FIELDS` from `tl_core.query.fields` (the fields listed above).

## Context (read these, nothing else)
- `AGENTS.md`
- `docs/tickets/P0-I4/provided/test_reference_doc.py.txt`
- `packages/tl-core/src/tl_core/query/parser.py` (its module docstring holds the grammar; read the docstring only)
may explore: (none)

## Allowed paths
- `docs/reference/query-language.md` (create)
- `tests/query/test_reference_doc.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T03.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_reference_doc.py.txt tests/query/test_reference_doc.py`
2. Write the page. Run the test often; it names the failing example.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest tests/query/test_reference_doc.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_reference_doc.py.txt tests/query/test_reference_doc.py
```
Expected: the test file passes, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the acceptance commands, and the list of positions you checked by running them.

## Escalation triggers
- Stop and report *Blocked* if an example the facts above imply does not parse, or a fact contradicts what `parse` does.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
