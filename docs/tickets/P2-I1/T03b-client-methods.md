# P2-I1-T03b — awp read methods on the TUI client, the API client and the fake

Status: ready
Tier: haiku
Review: full
Labels: tui, api
Depends on: T03a (merged)
Branch: `p2/i1-t03b-client`
Worktree: `/home/user/wt/i1/t03b` (from `p2/i1` head)

## Goal
Eight read methods exist on `ClientInterface` (`tl_tui/client.py`), on the embedded client (views under the signed-in viewer), on
`ApiClient` (the eight T03a GET routes) and on `FakeClient`, so a screen, the web and the simulator read the same CWP from any of them.
`RemoteClient` passes through with no change (a test holds the signature line, `tests/api/test_client_roundtrip.py`).

## Interfaces (add these to `ClientInterface`; same names, parameters and exceptions on every implementation)
```python
from tl_api.routes.awp import CwpDetailView   # route model: the detail with link_count, file_count, timeline  (embedded builds it, see Steps 2)
from tl_mod_awp import views as awp_views
def list_cwps(self, project: str, *, state: str | None = None, discipline: str | None = None, cwa: str | None = None) -> list[awp_views.CwpRow]
def get_cwp(self, project: str, number: str) -> CwpDetailView          # missing/hidden: RecordNotFoundError
def list_cwas(self, project: str) -> list[awp_views.CwaRow]
def wbs_tree(self, project: str, *, depth: int | None = None) -> list[awp_views.WbsRow]
def get_wbs_node(self, project: str, code: str) -> awp_views.WbsRow    # RecordNotFoundError
def get_path(self, project: str, version: int | None = None) -> awp_views.PathView   # RecordNotFoundError when none
def list_path_versions(self, project: str) -> list[awp_views.PathVersion]
def list_packages(self, project: str, *, kind: Literal["EWP", "PWP"] | None = None) -> list[awp_views.PackageRow]
```
Routes: `GET /projects/{project}/awp/{cwps,cwps/{number},cwas,wbs,wbs/{code:path},path,path/versions,packages}`; queries `state discipline cwa depth version kind`.
Pattern: `tl_api/client/schedule.py` (`self._get_json`, `self._models`, `quote`; a 404 body is rebuilt into the module error by the base), `embedded.py` lines 1347-1360
(`with self._uow(True) as uow:`), `tests/fakes_schedule.py` (a `Fake...Support` mixin with `_init_...`). If `CwpDetailView` should not be imported from
`tl_api.routes` into `tl_tui`, move nothing: import it in `client.py` and `embedded.py` only (tl-tui already depends on tl-api for `RemoteClient`).

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/client/schedule.py` and `client/__init__.py` (the mixin tuple), `packages/tl-api/src/tl_api/routes/awp.py` lines 30-100
- `packages/tl-tui/src/tl_tui/client.py` lines 745-800, `embedded.py` lines 1340-1360 (`get_cwp` copies the route body: `cwp_detail`, `links_of`, `list_files`, `record_history`)
- `packages/tl-tui/tests/fakes_schedule.py` lines 1-60 and 230-260, `fakes.py` lines 217-260
- `packages/tl-tui/tests/test_embedded_schedule.py` lines 1-60 (how a script builds an embedded client on a seed)
may explore: `.accept/p2-i1.db`

## Allowed paths
- `packages/tl-api/src/tl_api/client/awp.py` (create), `packages/tl-api/src/tl_api/client/__init__.py` (import and one tuple entry)
- `packages/tl-tui/src/tl_tui/client.py`, `packages/tl-tui/src/tl_tui/embedded.py`
- `packages/tl-tui/tests/fakes_awp.py` (create: `FakeAwpSupport`, `seed_awp(client)` makes 3 CWPs, 2 CWAs, a 3-node WBS, path v1 and v2, 1 EWP and 1 PWP), `packages/tl-tui/tests/fakes.py` (mixin and `_init_awp()` lines)
- `dev/accept/P2-I1/T03b.py` (create), `docs/reports/P2-I1/T03b.md` (create)

## Steps
1. Methods as above. `ApiClient` models: `self._models(views.CwpRow, data)` style; `get_cwp` returns `CwpDetailView.model_validate`.
2. Embedded `get_cwp`: same body as the route (`record_history` to timeline rows: date `recorded_at[:10]`, who `actor`, event `event_type`, note `payload.get("reason") or payload.get("note")` when a string, <= 200 chars else `""`). Put the shared timeline function where the route already has it (`_note`): import it, do not copy it.
3. The fake answers from lists given by the test, filters like the views (state, discipline, cwa, kind, depth), raises `RecordNotFoundError` for an unknown number or code.
4. `T03b.py` (`--db .accept/p2-i1.db`): builds the embedded client on the seed and `seed_awp(FakeClient())`; prints `PASS <method> <n> rows` for the eight methods on each; `PASS same CWP` when embedded `get_cwp(first number)` and the ApiClient (a `TestClient` on the app over a copy of the seed, as `dev/accept/P2-I1/T03a.py` does) return equal models; `PASS missing` when all three raise `RecordNotFoundError` for `NO-SUCH`. Ends `T03b ok`.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db   # if the file is missing
uv run python dev/accept/P2-I1/T03b.py --db .accept/p2-i1.db
just gate tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_embedded_schedule.py packages/tl-tui/tests/test_remote_client.py
```
Expected: `just check` clean; PASS lines and `T03b ok`; `gate: PASS`. The roundtrip test fails until every `ClientInterface` method is on `ApiClient`: that is the check that the three agree.

## Tests to add
none (T11 writes `packages/tl-tui/tests/test_client_awp.py`).

## Report requirements
`docs/reports/P2-I1/T03b.md` <= 60 lines, <= 5 decisive output lines per command; deviations first; pins updated outside Allowed paths (rule 12) listed. Subject `P2-I1-T03b: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and write *Blocked* if the roundtrip test needs a change outside Allowed paths other than a method list, or `ClientInterface` already has an awp name.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
