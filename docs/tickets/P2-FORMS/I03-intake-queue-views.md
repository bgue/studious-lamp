# P2-FORMS-I03 — Read views of the intake queue (codes and items)

Status: ready
Tier: haiku
Kind: ticket
Review: full  (stranger-supplied text; confidential rows; the code hash must never leave)
Labels: module, tests, security
Depends on: S7c merged (tables, commands); CR1 merged (intake rows). Not T03 (separate file). The signed-in routes `/forms/intake/` are **I03r**, a later ticket: they need the module hooks (P2-X4, branch `p2/ip-r3`), which are not on `p2/ip`.
Branch: `p2/forms-i03-queue-views`
Worktree: harness-created under `/home/user/wt/forms/i03` (from `p2/ip` head)

## Goal
`tl_mod_forms/intake_views.py`: what the controller's queue (CLI I04, TUI I05, routes I03r) reads. Pure reads over `v_forms_intake_item` and `v_forms_intake_code`, `viewer=` keyword-only defaulting to `confidentiality.LOWEST`, the hidden filter inside the statement and before `LIMIT` (pattern: `tl_mod_requisitions/views.py`).
No access word is checked here (entry points check `forms.intake.review`, `forms.intake.issue`).

## Brief references (pasted; S7c security review, S2 and CR1 rules)
`code_hash` is a secret-adjacent value: **no read view, row type, repr or error text carries it**; select the columns by name, never `SELECT *` or the view's column set. `body_mac` and the item `salt` stay out too. The staged body is read by one function only (`item_answers`), for a Pending item,
and returns the decoded answers. An intake item is hidden through its code, a code through its `context_id` (CR1); a code with no context is not hidden by the module: the controller words guard it, so the entry point checks the word. A hidden id answers as an absent one. Item states `Pending, Accepted, Rejected`; code states `Active, Revoked`.
`IntakeItem.Accepted.on_behalf_of_claim` holds only name and company (never the phone); the body row is deleted at accept (D18).

## Interfaces
```python
# packages/tl-modules/forms/src/tl_mod_forms/intake_views.py (create)
@dataclass(frozen=True) class CodeRow:  id, state, template_id, template_version, context_id, context_type, heading, controller_role, expires_on, issued_by, revoked_by, pending: int   # `pending` = Pending items of this code the viewer may read
@dataclass(frozen=True) class ItemRow:  id, state, code_id, template_id, template_version, received_at, body_bytes, accepted_as, accepted_by, accepted_on, claim_name: str|None, claim_company: str|None, rejected_reason, rejected_by, purged_at, version
@dataclass(frozen=True) class Page[T]:  rows: list[T], total: int
def code_list(conn, scope: str, *, state: str|None=None, limit: int=100, offset: int=0, viewer=LOWEST) -> Page[CodeRow]
def item_list(conn, scope: str, *, state: str|None=None, code_id: str|None=None, limit: int=100, offset: int=0, viewer=LOWEST) -> Page[ItemRow]   # oldest first: received_at, id
def item_detail(conn, scope: str, item_id: str, *, viewer=LOWEST) -> ItemRow | None
def item_answers(conn, scope: str, item_id: str, *, viewer=LOWEST) -> list[dict[str, Any]] | None    # Pending only; None for absent, hidden, other scope, not Pending, purged, or an unreadable body
def pending_count(conn, scope: str, *, viewer=LOWEST) -> int
```
`claim_name`, `claim_company` come from `on_behalf_of_claim_json` (a column that is not valid JSON or lacks a key gives `None`; a phone key is never copied). `issued_by` and the other actor columns: take the names the generated view has (read `ddl/sqlite/v_forms_intake_code.sql`; a column the view lacks is left out of the row, say so in the report).
An unknown `state` is `ValueError("unknown state")`. Limits clamp to 1..500. A list runs at most two statements; `pending` per code is one grouped statement over the page's ids, not one per row.
`item_answers` reads `forms_intake_body.body` for the one item, checks the item is visible and Pending first, decodes `{"answers": [...]}`; it must not write, and it appears in the S6 repo test that pins who touches the body table: it only SELECTs.

## Context (read these, nothing else)
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/views.py` (pattern), `packages/tl-modules/forms/src/tl_mod_forms/names.py`, `packages/tl-modules/forms/src/tl_mod_forms/confidential.py`
- `packages/tl-modules/forms/tests/forms_world.py` (intake helpers `intake_template`, `stage_code`, `stage_item` from S7c; `hidden_record`), `packages/tl-modules/forms/tests/test_intake_item_commands.py` (how an item is staged, accepted, rejected)
- `packages/tl-schema/src/tl_schema/generated/ddl/sqlite/v_forms_intake_{code,item}.sql` (column names)
may explore: `packages/tl-modules/forms/tests/test_visibility.py` (viewers)

## Allowed paths
- `packages/tl-modules/forms/src/tl_mod_forms/intake_views.py` (create)
- `packages/tl-modules/forms/tests/test_intake_views.py`, `.../test_intake_views_walk.py` (create)
- `docs/reports/P2-FORMS/I03.md` (create)
Not allowed: `intake.py` (S6), `handlers/**`, `views.py` (T03), `module.py`, `tl_core/**`, `schema/**`, routes, any other package.

## Tests to add (lint-clean under `ruff format`, `ruff check`, strict `pyright`; each test builds its own world)
- `test_intake_views.py`: code list (state filter, pending counts, order, clamps, offset); item list oldest first, filter by state and code; detail; an accepted item shows `claim_name`/`claim_company` and has no phone anywhere in `repr`; a rejected item shows the reason; `item_answers` returns the answers of a Pending item, `None` for an accepted one (body deleted), a rejected-but-kept one
  (not Pending), an absent id and another scope's id; a body that is not JSON gives `None`.
- **Secrets**: `CodeRow`, `ItemRow` and `Page` have no attribute named `code_hash`, `body_mac`, `salt`, `body`; a code issued with a known hash: that 64-hex string and a staged body's marker text appear in no `repr` of any list or detail result and in no exception text; the module source holds no `SELECT *`, no `code_hash` and no `body_mac`
  (repo-style test over the file text); `item_answers` is the only function that names `forms_intake_body`.
- `test_intake_views_walk.py`: five readers (lowest default, a reader of each class, the controller, an admin, the system viewer) over a code whose context is restricted and one whose context is open: hidden codes and their items are absent from lists, from `total` and from `pending_count`, and `item_detail`, `item_answers` are `None`, byte-identical to an absent id; filter before LIMIT (8 items, 3 hidden, `limit=5`);
  a code with no context is listed (the module does not hide it: assert it, and say so in the report so the entry points' word checks are tested there).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-modules/forms/tests/test_intake_views.py packages/tl-modules/forms/tests/test_intake_views_walk.py packages/tl-modules/forms/tests/test_intake_body_operational.py
```
Expected: all pass, `gate: PASS`.

## Report requirements
Standard report; first line deviations or none; the final column lists; the statement count per call.

## Escalation triggers
- A column named above is absent from the generated views (report the real columns; no schema edit).
- The hidden filter needs a `confidentiality.py` change (frozen: stop).
- `item_answers` cannot read the body without a write or a helper outside Allowed paths (stop; S6 owns the body table).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
