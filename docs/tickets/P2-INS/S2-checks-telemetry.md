# P2-INS-S2 — Checks read and telemetry stub: `record_checks`, routes, clients, `telemetry_need`, `note_need` (INS-B1 + INS-T1)

Status: ready (hold until the orchestrator dispatches; base `p2/wave2-close`)
Tier: builder
Kind: piece
Review: full
Labels: core, schema, api, tui, tests
Depends on: wave 2 close (on the base: constraints, readiness). Runs beside S1 in one workflow (plan check F9)
Branch: `p2/ins-s2-checks-telemetry`
Worktree: `/home/user/wt/ins-s2` (from `p2/ins` head)
Approver (schema): orchestrator, APPROVALS line for `schema/core/telemetry.yaml` and the setting `telemetry.retention_days`.
Approver (interface): orchestrator, one APPROVALS line with S1 (`ClientInterface.checks`, `.note_need`; routes `GET /records/{id}/checks`, `POST /insights/needs`).

## Goal
After this piece a record answers "what needs attention" through one read over five existing sources, shaped like the frozen readiness
`CheckResult`; and an operational table `telemetry_need` exists with one write path, `note_need`, with no reader. Checks are never labelled
as suggestions or machine output. Data health, stale pins and orphan links are roadmap item 1, not here.

## Brief references (pasted; spec A2.1, ADR-0028 decision 7, plan check F1 F7 F8 F12 win)
- `CheckFinding` {`source`, `subject_id`, `state` (word), `text`, `since` (ISO or None), `severity` (`blocking` | `warning`), `resolve_via`: list of `RecordRef`}. Put it in
  `tl_core/insights/types.py` next to S1's models (S1 creates that file first; add yours below, edit nothing of S1's).
- Sources (each takes the record's id, type, key and scope, and the viewer; a source that raises yields no finding and never fails the read):
  | source | read | finding when | severity |
  |---|---|---|---|
  | `readiness` (IWP only) | `tl_mod_awp.readiness.views.visible_readiness` | a check is `blocked`, `pending` or `unknown` (not `ok`, not `n_a`) | blocked: blocking; else warning |
  | `constraints` (any record) | `tl_core.constraints.queries.list_constraints(conn, scope, subject_id=id, state="Open")`, viewer-filtered; the target stays hidden as the view already does | each open constraint; text is category word, key and age, description cut at 120 characters | `blocking` severity: blocking; advisory: warning |
  | `expected_links` | `tl_core.links.expected.missing_expected_links` | each `MissingLink` | warning |
  | `clocks` | the correspondence view behind `GET /projects/{p}/clocks`, rows with `item_id = <id>` and `effective_state` expired or `days_left < 0` | each overdue clock | blocking |
  | `shortages` | `tl_mod_materials.views.mto_lines(conn, scope, short_only=True)` where the line is the record or names the record as its `work_package` | each short line, "short <qty> <uom>" | warning |
  The builder names the exact functions and signatures it found in the report. Each source is a module-level function `findings(conn, facts, viewer) -> list[CheckFinding]` in its own package
  (`tl_core/insights/checks.py` for `constraints` and `expected_links`; new `tl_mod_awp/insight_checks.py`, `tl_mod_correspondence/insight_checks.py`, `tl_mod_materials/insight_checks.py`; a module never imports another).
  One list of the module sources is assembled once in `tl_api/insights_sources.py`; the route and `EmbeddedClient.checks` both call `record_checks(conn, record, sources, viewer)` with it (no second copy).
- **Leak to close (plan check F1 and Q5):** a readiness result is computed with no viewer and `detail` may name keys. For a viewer: keep state word and counts; drop `resolve_via` records the viewer cannot read; when any were dropped replace `detail` with the fixed line "Some blocking records are not available to you." and never put a key in `text`. `visible_readiness` already drops the refs; the `detail` replacement is added in the readiness source, not in `visible_readiness` (its callers keep their behaviour).
- Order: by source (readiness, constraints, expected_links, clocks, shortages), then blocking first, then `since`. Cap 200 findings per record; at most 50 per source. A hidden or unknown record answers 404 `record_not_found` with the same body (embedded and fake: empty list). The read writes nothing.
- **Telemetry table** `schema/core/telemetry.yaml` -> `telemetry_need` (current-state DDL for both dialects through the generator, as `auth_audit` and `wh_*` do; operational, never rebuilt, not read by the archive, lake, outbox, webhooks or sync; the builder proves `rebuild-projections` leaves its rows alone). Columns, append-only, ids and words only:
  `need_id` (Ulid, identifier; ties a request to its later outcomes), `scope` (nullable), `recorded_at` (ISO UTC text with `Z`, **indexed**, the prune key), `request_kind` (`check|suggestion|analysis|ask`), `trigger` (text, `screen:insights.<subtab>`, `request`, `event:<type>`), `record_type` (required),
  `record_id` (nullable; set only for an explicit request, never by a screen opening), `viewer_role` (closed set of role words, `unknown` when none), `provider_kind` (nullable), `duration_ms` (nullable), `outcome` (`shown|accepted|dismissed|expired|unmet`), `why` (nullable, always written null; no reader and no privacy review yet).
  One row per state change, never an UPDATE. Setting `telemetry.retention_days` (default 365, bounds 30 to 3650) added to `schema/settings/platform.yaml` the way `awp.iwp.ready_lead_weeks` is.
- **`note_need`** (`tl_core/telemetry/__init__.py`): `note_need(conn, *, request_kind, trigger, record_type, viewer_role, outcome, scope=None, record_id=None, provider_kind=None, duration_ms=None, need_id=None, now=None) -> None`.
  Validates the closed sets; takes no content; runs inside `conn.begin_nested()` and swallows and logs (fixed code, no row data) any database error so it never aborts the caller's transaction, on Postgres included; prunes `recorded_at < now - retention` in the same savepoint, as `auth_audit` does. Reads of Activity and Checks never call it.
- **Route** `POST /insights/needs` (new `tl_api/routes/insights.py`, shared with the checks route; one registration line in `app.py`): body {`request_kind`, `trigger`, `record_type`, optional `record_id`}; `viewer_role` and the actor come from the token, never the body; refused for an `agent:` token (403, fixed code, and not added to any agent allow-list; prove it); process-local sliding window per actor, 30 per 10 minutes, then 429 `rate_limited` (follow `tl_api/ratelimit.py`); answers 204. `ClientInterface.note_need(...) -> None` never raises into the screen: a refusal or error is dropped. EmbeddedClient refuses an `agent:*` actor and calls `note_need` in a write unit of work; the remote client posts.

## Interfaces (shape)
```python
# tl_core.insights.checks
def record_checks(conn: Connection, record: RecordFacts, sources: Sequence[CheckSource], viewer: Viewer | None = None) -> list[CheckFinding]: ...
# ClientInterface (client.py, after `expected_links`), embedded.py (after `expected_links`), remote.py, tl_api.client (new file client/insights.py), FakeClient (end of class)
def checks(self, record_id: str) -> list[CheckFinding]: ...
def note_need(self, *, request_kind: str, trigger: str, record_type: str, record_id: str | None = None) -> None: ...
# GET /records/{record_id}/checks   guard("record.read"); POST /insights/needs
```

## Context (<= 10 files)
`tl_core/readiness/types.py` (frozen `CheckResult`, `RecordRef`); `tl_mod_awp/readiness/views.py` (`visible_readiness`); `tl_core/constraints/queries.py`; `tl_core/links/expected.py`; `tl_core/auth/audit.py` and `schema/core/auth.yaml` (`auth_audit`: retention, DDL pattern); `tl_api/ratelimit.py`, `tl_api/auth.py`; `packages/tl-api/tests/test_confidentiality_walk.py`; `tl_tui/embedded.py` (`expected_links`, a write method); `docs/adr/0028` decision 7 and plan check.

## Allowed paths
- `packages/tl-core/src/tl_core/insights/checks.py` (create), `types.py` (append `CheckFinding`, `RecordFacts` only), `packages/tl-core/src/tl_core/telemetry/__init__.py` (create), `packages/tl-core/tests/insights/test_checks.py`, `packages/tl-core/tests/telemetry/` (create)
- `schema/core/telemetry.yaml` (create, imported where `outbox.yaml` is), `schema/settings/platform.yaml` (one key), generated output by `just gen` (committed)
- `packages/tl-modules/{awp,correspondence,materials}/src/*/insight_checks.py` (create each), nothing else in a module
- `packages/tl-api/src/tl_api/routes/insights.py`, `insights_sources.py`, `client/insights.py` (create), `app.py` (one line), the `ApiClient` mixin line
- `packages/tl-tui/src/tl_tui/client.py`, `embedded.py`, `remote.py` (the two methods only, in their own places), `packages/tl-tui/tests/fakes.py`
- walking tests `packages/tl-api/tests/test_checks_walk.py`, `test_note_need_walk.py` (create): five readers x visible, hidden, missing on `/checks`, hidden equals missing; agent token 403 and a human 204 then 429 past the window on `/insights/needs`; no content column; the checks read writes nothing (statement verbs, both adapters)
- `dev/accept/P2-INS/S2.py`, `docs/reports/P2-INS/S2.md` (create)
- consequential pins (rule 12): schema and table lists, settings registry tests, route and client lists; each listed
Not allowed: `tl_core/confidentiality.py`, screens and widgets, `record_view.py`, MCP tools, any telemetry reader, route or CLI beyond the one write route.

## Acceptance (run once each)
```
just gen && NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-INS/S2.py
just gate packages/tl-core/tests/insights packages/tl-core/tests/telemetry packages/tl-api/tests/test_checks_walk.py packages/tl-api/tests/test_note_need_walk.py packages/tl-tui/tests/test_client_conformance.py
just gate-pg packages/tl-core/tests/telemetry packages/tl-api/tests/test_checks_walk.py
```
`S2.py` (SQLite tmp db, <= 70 lines, final `S2 ok`): an IWP with a blocked check, an open constraint, a missing expected link, an overdue clock and a short MTO line gives one finding per source; a hidden `resolve_via` record leaves no key in any `text`; `note_need` writes one row and a second call writes a second (append); a row older than retention is pruned; a forced database error inside `note_need` leaves the caller's transaction usable; `rebuild-projections` keeps the rows.

## Guards for the review and the sentinel plus at most 5 (name file:line; run no sweep)
The `detail` replacement and `resolve_via` filter; `n_a` and `ok` excluded; the constraint viewer filter (via the view); the closed sets and "no content" in `note_need`; `begin_nested` swallow; the retention cutoff; the agent refusal; the per-actor window; `record_id` null on screen rows.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; the functions and signatures each source used; the generated files; the `viewer_role` source; pins; guards file:line; learnings. Builder return <= 15 lines.

## Commit
`P2-INS-S2: <imperative summary>`; body says what and why; end with the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: a source cannot be read for one record without a new view or a schema change outside `telemetry.yaml`; the generator treats `telemetry_need` as a projection and rebuilds it; `begin_nested` cannot be used on the unit of work; the role word cannot be read from the principal; the registry of settings needs more than one key.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
