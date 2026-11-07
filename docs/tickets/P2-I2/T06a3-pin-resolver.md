# P2-I2-T06a3 — Pin resolver filtered by link ids; `documents_current` uses it

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, readiness
Depends on: T06a1 (merged)
Branch: `p2/i2-t06a3-pin-resolver`
Worktree: `/home/user/wt/t06a3` (from `p2/i2` head)

## Goal
`documents_current` stops resolving every document link of the scope. Today `_answer` calls `links_to_documents(conn, iwp.scope, limit=1000)`: about 4 statements per
scope link, and pins past the 1000th row are dropped, so a big scope answers a false `blocked`. After this ticket the resolver can be asked for exactly the wanted link ids, and
the check asks for the IWP's pins only; the statement count is bounded by the IWP's pins, never by the scope.

## Brief references (pasted)
> `links_to_documents(conn, scope, *, document_id=None, only_stale=False, limit=1000)` builds one SQL over `cur_links l JOIN cur_core_record d JOIN cur_core_record x`
> (`_LINKS_OF_DOCS_SQL`), adds the viewer filter for both ends (`not_hidden_each` with `document_id`, else `not_hidden`), orders by `d.key, x.key, l.link_id`, applies `LIMIT`, then calls
> `resolve_pin` per row (it reads the document, the pinned revision and the revisions of the document: 3 statements).
> Change: add keyword `link_ids: Collection[str] | None = None`. When given: `AND l.link_id IN (...)` (SQLAlchemy `bindparam(expanding=True)`; an empty collection returns `[]` without a
> statement), and the visibility test is `not_hidden_each` (few rows). Memoize `resolve_pin` per `(to_id, pin)` inside the call. All other behaviour, ordering and the default limit stay as they are;
> every existing caller is unchanged.
> `documents_current._answer`: pass `link_ids=wanted` and `limit=len(wanted)` (no `SCOPE_LIMIT`; delete the constant if nothing else uses it). `total` stays the count of pin ids read by `_pin_ids`.
> A pin whose link the viewer filter drops (hidden or missing document) is simply not in `found`: it counts as not current, exactly as today, and the answer for a hidden pinned document is byte-identical to a missing one
> (detail, counts, `resolve_via`). Keep the keys-and-counts-only contract.

## Interfaces (verbatim from repo)
```python
# packages/tl-modules/documents/src/tl_mod_documents/resolver.py
def links_to_documents(conn: Connection, scope: str, *, document_id: str | None = None,
                       only_stale: bool = False, limit: int = 1000) -> list[PinnedLink]: ...
# readiness.py: _pin_ids(conn, iwp) -> list[str] (one statement); _answer(conn, iwp) -> CheckResult; SCOPE_LIMIT
```

## Context (read these, nothing else)
- `packages/tl-modules/documents/src/tl_mod_documents/resolver.py` (lines 55-225)
- `packages/tl-modules/documents/src/tl_mod_documents/readiness.py`
- `dev/accept/P2-I2/T06a1.py`, `docs/reports/P2-I2/T06a1.md`
- `packages/tl-modules/documents/tests/test_resolver.py` (shape only)

## Allowed paths
- `packages/tl-modules/documents/src/tl_mod_documents/resolver.py` (the one function and a memo helper)
- `packages/tl-modules/documents/src/tl_mod_documents/readiness.py`
- `dev/accept/P2-I2/T06a3.py` (create), `dev/accept/P2-I2/T06a1.py` (only if a line must change; say why)
- `docs/reports/P2-I2/T06a3.md` (create)
Not here: any other file, new pytest (S5).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T06a1.py
uv run python dev/accept/P2-I2/T06a3.py
just gate packages/tl-modules/documents/tests
```
`T06a3.py` (SQLite temp ledger; one `PASS <check>` per line; final `T06a3 ok`): a scope with 1100 document links of other records plus one IWP with 3 pins (one stale): the check answers
`blocked`, `2/3`, `resolve_via` the stale one, and the statements it runs (count with an engine `before_cursor_execute` listener) are <= 12 and the same with 100 or 1100 other links; an IWP with 60 pins
returns all 60 counted (`total` 60, none dropped past any limit); `link_ids=[]` returns `[]` with no statement; `link_ids` result equals the filtered scope-wide result for the same ids; a hidden pinned
document and a missing one produce equal `CheckResult`s; the existing `links_to_documents` calls (no `link_ids`) return what they did before.

## Tests to add
None (S5 writes the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, statement counts before and after. Commit subjects `P2-I2-T06a3: ...`; the commit trailer is the attribution lines your harness
requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if the visibility filter cannot take the wanted ids without widening it, or a caller outside the allowed paths needs a changed signature.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
