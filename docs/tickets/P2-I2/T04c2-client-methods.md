# P2-I2-T04c2 — IWP, constraint and readiness read methods on the clients and the fake

Status: staged (dispatch after T04c1 merges; read its report for the route model names)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, api, read, confidentiality
Depends on: T04c1
Branch: `p2/i2-t04c2-client-methods`
Worktree: harness-created under `/home/user/wt/i2/t04c2` (from `p2/i2` head)

## Goal
Seven read methods exist on `ClientInterface` (`tl_tui/client.py`), the embedded client, `ApiClient` and `FakeClient`, so every screen, web page and the simulator read IWPs, constraints and readiness from any of them. Pattern and steps are those of P2-I1 T03b (`docs/tickets/P2-I1/T03b-client-methods.md`; the awp CWP methods are the model: `tl_api/client/awp.py`, `embedded.py` ~1676, `client.py` ~985, `tests/fakes_awp.py`). `RemoteClient` passes through unchanged.

## Interfaces (add to `ClientInterface`; same names, parameters and errors on every implementation)
```python
from tl_mod_awp import iwp_views          # IwpRow IwpDetail ScopeRow
# route models of T04c1 (names in its report): readiness without facts_hash; constraint row with subject_key and subject_type; list with total; groups with truncated
def list_iwps(self, project, *, state=None, discipline=None, foreman=None, limit=200) -> list[iwp_views.IwpRow]
def get_iwp(self, project, number) -> iwp_views.IwpDetail            # RecordNotFoundError (missing or hidden: one text)
def list_iwp_scope(self, project, number, *, limit=200) -> list[iwp_views.ScopeRow]   # RecordNotFoundError
def get_iwp_readiness(self, project, number) -> <readiness route model>   # RecordNotFoundError: no IWP, hidden, or never evaluated
def list_constraints(self, project, *, subject=None, state=None, category=None, phase=None, blocking=None, owner=None, limit=200) -> <constraint list model: rows, total>
def constraint_groups(self, project, by) -> <groups model>              # `by` outside BY_WORDS: ValueError
def get_constraint(self, project, key) -> <constraint row model>        # RecordNotFoundError
```
Routes (T04c1): `GET /projects/{project}/awp/iwps[/{number}[/scope|/readiness]]`, `GET /projects/{project}/constraints[/groups|/{key}]`; query names as the keywords above (`subject` is a record key).
Embedded: the same calls the routes make, under the signed-in viewer: IWP reads from `iwp_views`, readiness through `visible_readiness(conn, scope, key, viewer)` (D32, never `readiness()`), constraints from `tl_core.constraints` after the same `core.constraint.view` check the route makes (a refusal is the module's refusal error, as the route's 403). Never a second SQL path.
Fake: answers from lists a test gives it (`load_iwps(project, ...)`, `load_constraints(...)`, `load_readiness(project, number, view)`), filters and sorts like the views, `RecordNotFoundError` for an unknown or unloaded number or key. `seed_iwp(client)` makes 4 IWPs (Draft, Ready, Issued, one oversize), 6 scope rows, 5 constraints on two subjects (owners, categories, ages 2/9/20 days, one blocking), one readiness of 9 checks (2 blocked, 5 `n_a`, one with a `resolve_via`).

## Context (read these, nothing else)
- `docs/reports/P2-I2/T04c1.md`, `packages/tl-api/src/tl_api/routes/constraints.py`, `routes/awp.py` (IWP and readiness routes at the end)
- `packages/tl-api/src/tl_api/client/awp.py`, `client/__init__.py` (mixin tuple), `packages/tl-tui/src/tl_tui/client.py` ~985-1030, `embedded.py` ~1674-1745
- `packages/tl-tui/tests/fakes_awp.py` (all), `tests/fakes.py` lines 217-270

## Allowed paths
- `packages/tl-api/src/tl_api/client/iwp.py` (create), `client/__init__.py` (import and one tuple entry)
- `packages/tl-tui/src/tl_tui/client.py`, `packages/tl-tui/src/tl_tui/embedded.py`
- `packages/tl-tui/tests/fakes_iwp.py` (create), `packages/tl-tui/tests/fakes.py` (mixin and `_init_iwp()` lines)
- `dev/accept/P2-I2/T04c2.py` (create), `docs/reports/P2-I2/T04c2.md` (create)

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T04c2.py
just gate tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_remote_client.py
```
`T04c2.py` (a SQLite ledger from the C2 or S4 world helpers in `dev/accept/P2-I2/`; embedded client on it, `ApiClient` over a `TestClient` of the app on a copy, `seed_iwp(FakeClient())`): `PASS <method> <n>` for the seven methods on each of the three; `PASS same` embedded and ApiClient equal for `get_iwp`, `get_iwp_readiness`, `list_constraints`, `get_constraint`; `PASS missing` all three raise `RecordNotFoundError` for `NO-SUCH`; `PASS hidden` a reader of low clearance gets the same error text for a hidden IWP as for a missing one, and no hidden constraint in `list_constraints` rows or `total`; `PASS no-hash` no `facts_hash` field on the readiness model; `PASS word` an actor without `core.constraint.view` is refused by `list_constraints` on embedded. Ends `T04c2 ok`.

## Tests to add
None (S5).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Subject `P2-I2-T04c2: ...`; trailer is the attribution lines your harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- Stop and write *Blocked* if a T04c1 route model lacks `subject_key`, or the roundtrip test needs a change other than a method list, or `ClientInterface` already holds one of the names.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
