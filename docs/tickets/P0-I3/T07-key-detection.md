# P0-I3-T07 — Key detection in text

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I3-T05 (merged into the base of this branch)
Branch: `p0/i3-t07-key-detection`

## Goal
`tl_core/numbering/detect.py` finds record keys in free text (a title, a post, a message body) using the numbering patterns that apply to a
scope, and resolves them to records, so a client can show suggestion chips ("Tab accepts it inline"). The models and signatures exist; the three
functions raise `NotImplementedError`. A provided test file (32 tests) must pass.

## Brief references (pasted)
> **7.2 Key detection:** Any recognisable key typed in a field, post, thread message, or correspondence body, or found by OCR in a document, becomes a suggestion chip; `Tab` accepts it inline.
> **7.4 Chips everywhere:** any key in any text shows as a chip with status colour; hovering (or `K`) shows a preview card.
> **8 Numbering service:** pattern-driven per project/type (e.g. `{project}-{type}-{discipline}-{seq:4}`).

### Specification (the provided test checks it)
`Pattern` (from `NumberingPattern.compiled()`) has `search_regex()` (finds a key not glued to letters, digits, `_` or `-`) and `parse(key)` (returns `None` unless the key is spelled exactly as it would be generated: `P1-REC-0012` parses, `P1-REC-00012` does not).
- `detect_keys(text_, patterns)`:
  1. For each pattern (index `i`, `compiled = pattern.compiled()`), for each `m` in `compiled.search_regex().finditer(text_)`: skip it if `compiled.parse(m.group(0)) is None`; else keep a candidate `(KeyMatch(start=m.start(), end=m.end(), key=m.group(0), pattern_id=pattern.id), i)`.
  2. Sort candidates by `(-(end - start), pattern index, start)`. Walk them in that order and keep a candidate only if it does not overlap a kept one (it overlaps unless `candidate.end <= kept.start or candidate.start >= kept.end`). So the longer match wins an overlap, then the earlier pattern.
  3. Return the kept matches sorted by `start`. The same key twice in the text gives two matches.
- `resolve_chips(uow, scope, matches, *, linked_to=None, exclude_id=None)`: for each match, in the order given:
  1. `rows = uow.conn().execute(_LOOKUP_SQL, {"key": match.key, "scope": scope}).all()`; sort so a row whose `scope == scope` comes before a company row (`sorted(rows, key=lambda r: bool(r.scope != scope))`); `found` is the first row or `None`.
  2. If `found` exists and `found.id == exclude_id`, skip the match (leave it out of the result).
  3. `link_status`: only when `found` exists and `linked_to` is not `None`: collect `status` of the rows of `_LINKED_SQL` (bound `a=linked_to`, `b=found.id`; it already ignores retracted links and looks both ways); `link_status` is the status with the smallest `_RANK` (`active` < `stale` < `broken` < `suggested`), or `None` when there are no rows.
  4. Build `KeyChip(start, end, key, pattern_id` from the match, `record_id=found.id`, `record_type=found.type`, `title=found.title`, `status=found.status`, `voided=bool(found.voided)` or `None`/`False` when no record has the key, `link_status=link_status)`.
- `suggest_chips(uow, scope, text_, *, linked_to=None, patterns=None)`: `applicable = patterns if patterns is not None else get_numbering().for_scope(scope)` (`from tl_core.numbering.config import get_numbering`); return `resolve_chips(uow, scope, detect_keys(text_, applicable), linked_to=linked_to, exclude_id=linked_to)`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No SQLite- or Postgres-specific SQL; bound parameters only. pyright is `strict` for `packages/tl-core/src`: `Result.all()` rows are partly typed, so sort with an explicit `key=lambda r: bool(r.scope != scope)` as above. ruff limits lines to 100 columns and sorts imports (`uv run ruff check --fix`, then `uv run ruff format`). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub has no SQL: add `_LOOKUP_SQL`, `_LINKED_SQL` and `_RANK` exactly as below.
- Remove the `STUB (P0-I3-T07)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/numbering/detect.py (existing stub; models and signatures are final)
class KeyMatch(BaseModel): start: int; end: int; key: str; pattern_id: str
class KeyChip(BaseModel): start: int; end: int; key: str; pattern_id: str; record_id: str | None
    record_type: str | None = None; title: str | None = None; status: str | None = None; voided: bool = False; link_status: str | None = None
def detect_keys(text_: str, patterns: Sequence[NumberingPattern]) -> list[KeyMatch]
def resolve_chips(uow: UnitOfWork, scope: str, matches: Sequence[KeyMatch], *, linked_to: str | None = None, exclude_id: str | None = None) -> list[KeyChip]
def suggest_chips(uow: UnitOfWork, scope: str, text_: str, *, linked_to: str | None = None, patterns: Sequence[NumberingPattern] | None = None) -> list[KeyChip]
```
```python
# add to the module (imports: from sqlalchemy import text)
_LOOKUP_SQL = text(
    "SELECT id, scope, type, title, status, voided FROM cur_core_record "
    "WHERE key = :key AND scope IN (:scope, 'company')"
)
_LINKED_SQL = text(
    "SELECT status FROM cur_links WHERE status <> 'retracted' AND "
    "((from_id = :a AND to_id = :b) OR (from_id = :b AND to_id = :a))"
)
_RANK = {"active": 0, "stale": 1, "broken": 2, "suggested": 3}
```
```python
# existing
class NumberingPattern(BaseModel): id: str; ...; def compiled(self) -> Pattern
class NumberingRegistry: def for_scope(self, scope: str) -> list[NumberingPattern]
def get_numbering() -> NumberingRegistry          # tl_core.numbering.config
# Pattern (tl_core.numbering.pattern): .search_regex() -> re.Pattern[str]; .parse(key) -> ParsedKey | None
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/numbering/detect.py`
- `packages/tl-core/src/tl_core/numbering/pattern.py` (read `search_regex` and `parse`)
- `docs/tickets/P0-I3/provided/test_key_detection.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/numbering/detect.py` (edit)
- `packages/tl-core/tests/test_key_detection.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T07.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_key_detection.py.txt packages/tl-core/tests/test_key_detection.py`
2. Implement the three functions; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_key_detection.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_key_detection.py.txt packages/tl-core/tests/test_key_detection.py
```
Expected: 32 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
