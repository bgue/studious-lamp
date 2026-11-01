# P2-I1-T03a — API read routes of the awp module

Status: ready
Tier: haiku
Review: full
Labels: api
Depends on: T10 (merged)
Branch: `p2/i1-t03a-routes`
Worktree: `/home/user/wt/i1-t03a` (from `p2/i1` head)

## Goal
Eight GET routes serve the awp read views to the web, TUI and MCP clients, plus the three things decision D15 left out of
the views for a CWP: link count, file count and timeline. Every route reads through the viewer; a missing, hidden or voided
record answers one 404 with the same text.

## Brief references (pasted; spec `docs/build-spec/specs/m3-wbs-cwp.md` §5)
GET, read level: `/projects/{project}/awp/cwps` (query `state`, `discipline`, `cwa`), `/awp/cwps/{number}`, `/awp/cwas`,
`/awp/wbs` (query `depth`), `/awp/wbs/{code:path}`, `/awp/path` (query `version`), `/awp/path/versions`, `/awp/packages`
(query `kind`), all under `/projects/{project}`. Writes are `POST /commands/<Name>` from `AWP_COMMANDS` (already wired).
`/awp/reports/{name}` is NOT here (T03c, after the reports exist). Every new GET route joins the confidentiality walk.
Timeline row: date (`recorded_at` as `YYYY-MM-DD`), who (`actor`), event (`event_type`), note (`payload.get("reason")` or
`payload.get("note")` when a string, cut to 200 characters, else `""`). Timeline oldest first.

## Interfaces (verbatim)
```python
# tl_mod_awp.views (merged): cwp_list(conn, scope, *, state=None, discipline=None, cwa=None) -> list[CwpRow];
#  cwp_detail(conn, scope, number) -> CwpDetail|None; cwa_list(conn, scope) -> list[CwaRow]; wbs_tree(conn, scope, *, depth=None)
#  -> list[WbsRow]; wbs_detail(conn, scope, code) -> WbsRow|None; path(conn, scope, version=None) -> PathView|None;
#  path_versions(conn, scope) -> list[PathVersion]; package_list(conn, scope, *, kind=None) -> list[PackageRow]  (kind EWP|PWP else ValueError)
# tl_core.services.link_queries.links_of(uow, record_id, *, include_retracted=False) -> list[LinkView]   (hidden ends left out)
# tl_core.services.queries.record_history(uow, record_id) -> list[Event]       (viewer-filtered; [] when hidden)
# tl_core.files.queries.list_files(uow, scope, record_id, *, slot=None, current_only=False) -> list[FileInfo]
# routes pattern: packages/tl-api/src/tl_api/routes/cost.py (Ctx, Reader = guard("document.read"), `with ctx.backend(True) as uow:`)
# missing -> raise tl_core.services.errors.RecordNotFoundError(f"no ... {x!r}")  # 404 record_not_found
```
Models: return the view models as they are; for the detail define `CwpDetailView(CwpDetail)` with `link_count: int`,
`file_count: int`, `timeline: list[TimelineRow]` and `TimelineRow(date, who, event, note)` in the routes file.
`package_list` with a bad `kind`: validate the query with `Literal["EWP","PWP"] | None` (422), never reach the `ValueError`.
Scope is `f"project:{project}"`. The CWP id for counts is `detail.id`.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/cost.py` (pattern), `packages/tl-api/src/tl_api/app.py` lines 290-310 (router tuple)
- `packages/tl-modules/awp/src/tl_mod_awp/views.py` (models: class bodies only)
- `packages/tl-api/tests/test_confidentiality_walk.py` lines 142-162 (`candidates`)
- `dev/accept/P2-W0/RM-S3.py` lines 60-100 (how a script builds the app and a signed-in `TestClient`)
may explore: `.accept/p2-i1.db`

## Allowed paths
- `packages/tl-api/src/tl_api/routes/awp.py` (create), `packages/tl-api/src/tl_api/routes/__init__.py` if routers are listed there,
  `packages/tl-api/src/tl_api/app.py` (import and one tuple line `awp,`)
- `packages/tl-api/tests/test_confidentiality_walk.py` (only the `"code"` entry of `candidates`: add `"1.1.1"`, `"1"`)
- `docs/reference/openapi.json` (regenerate: `uv run python -m tl_api.openapi`; `just check` fails on drift)
- `dev/accept/P2-I1/T03a.py` (create), `docs/reports/P2-I1/T03a.md` (create)

## Steps
1. Routes as above; operation ids `list_cwps get_cwp list_cwas wbs_tree get_wbs_node get_path list_path_versions list_packages`.
   `wbs_tree` query `depth` is `Query(ge=1, le=20)`; `version` is `Query(ge=1)`; a `None` from a view raises `RecordNotFoundError`.
2. `get_cwp`: `cwp_detail`, then in the same `uow` `len(links_of(uow, d.id))`, `len(list_files(uow, scope, d.id))` and the timeline
   from `record_history`.
3. Acceptance script `dev/accept/P2-I1/T03a.py`: copy `.accept/p2-i1.db` to a temp file, build the app on it (read how RM-S3 does it),
   sign in a person with a read role and call each GET once: `PASS GET <path> 200 <n> rows` (detail: counts and timeline length);
   the unknown CWP and a made-up id answer 404 with the same `error` code and text; an anonymous call answers 401. Ends `T03a ok`.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db     # if the file is missing
uv run python dev/accept/P2-I1/T03a.py
just gate packages/tl-api/tests/test_confidentiality_walk.py packages/tl-api/tests/test_openapi.py
```
Expected: `just check` clean; PASS lines and `T03a ok`; `gate: PASS`.

## Tests to add
none (T11 writes `packages/tl-api/tests/test_api_awp.py` and the five-reader awp entries of the walk).

## Report requirements
`docs/reports/P2-I1/T03a.md` <= 60 lines, <= 5 decisive output lines per command; deviations first. Pins updated outside
Allowed paths (rule 12) listed. Subject `P2-I1-T03a: ...`; no model names; commit trailer = the harness attribution line, then
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and write *Blocked* if the read guard `document.read` does not let a person with a read role call these routes, if a
  route needs an action name that does not exist, or if the walk fails on an awp route (write which).

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
