# Fanout plan: P0-I8 (hardening and Phase 0 exit)

Status: active. WS-A, WS-B and WS-C start now from `p0/i8`. WS-D starts when the first of them is DONE (concurrency cap, L-P0-I5-O4). WS-E starts after A–D are merged into `p0/i8`.
Orchestrator session: 2026-10-10
Brief sections: §30 (settings), §31 (extension types), §25.2–§25.4 (agent affordances, dev MCP server), §15 (targets), §16 Phase 0 and its exit, §17 (risks); build spec 05 §Increment 8, 04-gates §1

## Objective
Close Phase 0. This increment builds about:config settings v1 and extension type registry v0, the dev MCP server and scaffolding, and a measured performance pass at 100k records. It then demonstrates every §16 Phase 0 exit criterion end to end on a simulated project. A §16 checklist audit, a risk register and the Phase 0 report record what is done, what deviates and what is deferred to a human.

## Exit criteria
- [ ] **Settings v1** (`tl_core/settings/types.py`):
  - `SettingDefinition` LinkML class in `schema/core/settings.yaml`, and platform definitions in `schema/settings/platform.yaml`;
  - `Setting.Changed` and `Setting.Locked` events in the event catalog;
  - the layered resolver (default → company → project → user), with origin, the ● marker, locks and bounds, scheduled changes, required reason and risk acceptance, and per-key history with revert;
  - `tl config get|set|reset|lock|diff|export|import`, `/settings` API routes, MCP `get_settings` and `propose_setting_change` (propose-only), and the TUI about:config screen (`Ctrl+,`, sketch 14);
  - the existing hard-coded behaviour reads from settings (D2), and live keys apply without a restart.
- [ ] **Extension types v0** (`tl_core/extypes/types.py`):
  - `tl types sync|watch|ls` registers or quarantines packages and is idempotent;
  - managed and object-backed instances work through `CreateRecord.record_type = "<ns>.<Name>"` and the generic API, MCP, TUI grid and forms;
  - an object-backed body is hash-verified on read, and a mismatch is quarantined;
  - a package's `settings.yaml` registers namespaced keys;
  - the example package is `schema/fixtures/types/co.acme/LiftPlan/1.0.0/`.
- [ ] **Agent-dev baseline:**
  - the dev MCP server (`python -m tl_mcp.dev`, stdio, dev data only) has the tools `run_tests`, `gen` (with a drift report), `query_db` (read-only), `render_screen` (SVG), `rebuild_projections`, `seed` and `send_test_webhook`, and the resources schema graph, event catalog, ADRs, runbooks and test reports;
  - `tl new record-type|module|projector` scaffolding produces a schema stub, handler, tests and doc placeholders that pass `just check`;
  - every package's AGENTS.md is audited against the code;
  - the CI workflow is reviewed against 04-gates §1.
- [ ] **Performance:**
  - `just bench` (marker `bench`, not in `just test`) seeds 100k records, with links and pset values, on SQLite and Postgres;
  - it measures, against §15: grid scroll and filter p95 (query paging and the TUI grid), realtime latency between two clients, and full projection rebuild time;
  - hot spots are fixed;
  - results are in `docs/reports/P0-I8-perf.md`.
- [ ] **Phase 0 exit:** `just demo P0-I8` shows the §16 exit on a simulated project:
  - create, link and set psets on a generic record in the TUI (pilot), the API and MCP;
  - live updates between two TUIs;
  - an external webhook receiver gets a signed event for a filtered subscription;
  - a full restore from backup passes verification.
- [ ] **Phase 0 records:**
  - `docs/reports/PHASE-0-AUDIT.md`: each §16 Phase 0 bullet marked done, partial or deviation, with evidence;
  - `docs/reports/RISKS.md`: §17 plus the risks the run found;
  - `docs/reports/PHASE-0.md`;
  - 04-gates §1 all green on the trunk.

## Workstreams
| WS | Name | Branch · worktree | Base | Supervisor builds | Implementer tickets (summary) |
|---|---|---|---|---|---|
| A | Settings | `p0/i8a` · `/home/user/wt/p0-i8a` | `p0/i8` now | resolver, set/lock/reset service with validation, `SettingsReader` with bus invalidation, the cur_setting projection | LinkML class and platform.yaml; catalog entries; `tl config` CLI; API routes and error rows; MCP tools; TUI screen and snapshots; wiring D2 keys; export/import; parity tests |
| B | Extension types | `p0/i8b` · `/home/user/wt/p0-i8b` | `p0/i8` now | package validator (layout, lock, lint, compile, examples), registry sync and idempotence, body store and verified load | example package; `tl types` CLI and polling watcher; generic API and MCP for extension types; TUI grid and form from `form.yaml`; quarantine report; settings.yaml registration (after A merges); parity tests |
| C | Agent-dev | `p0/i8c` · `/home/user/wt/p0-i8c` | `p0/i8` now | dev MCP server core and its dev-data guard (D12) | each dev tool and resource; `tl new` scaffolders; AGENTS.md audit; runbook for the dev MCP server; CI review |
| D | Performance | `p0/i8d` · `/home/user/wt/p0-i8d` | `p0/i8` after one of A–C is DONE | bench harness and 100k generator, the measurement method | per-target benches; fixes for each hot spot found (index, paging, batching), each with a before/after number |
| E | Exit | `p0/i8e` | `p0/i8` after A–D are merged | the exit demo flow | §16 audit rows; RISKS.md; runbook pass; PHASE-0.md draft |

## Shared contracts
- `packages/tl-core/src/tl_core/settings/types.py` (A owns the implementation; B, C and D consume it).
- `packages/tl-core/src/tl_core/extypes/types.py` (B).
- The amendment to the proposals contract (D3): `PROPOSABLE_TOOLS["propose_setting_change"] = "ChangeSetting"`. A adds it to `tl_core/proposals/types.py` with the `ChangeSetting` command.

## Orchestrator decisions
| # | Decision |
|---|---|
| D1 | Setting definitions are data. `schema/settings/platform.yaml` is validated against the LinkML `SettingDefinition` class in `schema/core/settings.yaml`. A test keeps the pydantic model in `settings/types.py` and the generated class in agreement. `schema/**` merges are within the KICKOFF delegation (logged in APPROVALS). |
| D2 | v1 defines only keys whose behaviour exists:<br>• `feed.reactions.enabled`, `feed.signal_tags` (swap `tl_core/feed/config.py`)<br>• `webhooks.retry.max_hours`<br>• `webhooks.egress.allowlist` (dangerous)<br>• `lake.sync.interval`<br>• `ai.agents.default_mode` (enum `[propose]`, lockable; "write" is a human gate, ADR-0005)<br>• `ai.agents.daily_proposals` (default 500, replaces the constant)<br>• `project.mode` (enum live\|sandbox\|simulated\|mirror; stored and shown)<br>• `schema.conformance.mode` if the P0-I2 conformance code reads a mode<br>• `ui.tui.keymap` and `ui.tui.graphics` (user layer)<br>Brief keys for modules that do not exist yet (awp, threads, sync, links, models, uploads) are added with their module. `CARD_WINDOW_SECONDS` stays a constant, because rebuild determinism depends on it. |
| D3 | Settings follow the proposal rules. An `agent:*` actor never sets a value directly (B15 extended): the API returns 403 `agent_must_propose`, and MCP has only `propose_setting_change`. Accepting the proposal runs `ChangeSetting` as the human. Who may lock or set dangerous keys is the permission model, a human gate. v1 applies the mechanism (reason, accept_risk), not role checks, under the ADR-0005 dev identities. Approval workflows for dangerous keys are a follow-up. |
| D4 | `sensitivity: secret` is refused with `secret_setting_unavailable`, because a vault is a human gate (P0-I5 D15). No platform key is secret. |
| D5 | A scheduled change is a `Setting.Changed` event with a future `applies_at`. Resolution is time-based, so no job applies it. The reader cache expires at the next `applies_at`. History shows the change when it is recorded, and the value takes effect at `applies_at`. |
| D6 | `pending_effect` is derived. A local, non-ledger table records the last seq at which each effect was applied: `tl rebuild-projections` writes it for rebuild and reindex, and server start writes it for restart. A ledger rebuild alone always yields the same `cur_setting` rows. |
| D7 | An extension type instance is a generic record whose `record_type` is `<namespace>.<Name>` for an active registration. The 03 §7 signatures are unchanged; only the allowed values widen, so no ADR is needed. Index fields are stored as pset values under a pset named for the type, so the existing query language filters them. Non-index body fields are not filterable (§31.4). |
| D8 | Discovery uses `tl types sync <root>` and a polling `tl types watch` (an interval, mtime and lock-hash check). No watchdog dependency is added. Bucket events come later. |
| D9 | `type.lock` is canonical JSON `{"files": {relpath: sha256}}`, and `content_hash` is the sha256 of those bytes. Signing on publish (§31.1) is a follow-up; the archive `Signer` can be reused. |
| D10 | Object-backed bodies live in the existing record ObjectStore under `records/<type>/<id>/<sha256>.json` (canonical JSON), written once per hash. Only `Record.BodyStored` metadata is in the ledger. |
| D11 | v0 refuses directory-backed storage and the external `incoming/` write path with TypeIssue `unsupported`. Both are follow-ups. |
| D12 | The dev MCP server is a separate entrypoint, `python -m tl_mcp.dev`, on stdio only. It refuses any database that is not a SQLite file under the repo's `dev/` or a temp directory, or a Postgres URL whose database name starts with `tl_test` or `tl_dev`. `query_db` is read-only: it uses the P0-I7 lake guard approach for SQL (SELECT/WITH only) and a read-only connection. `run_tests` takes a marker or path filter from an allow-list, with no shell. `send_test_webhook` only targets loopback receivers. |
| D13 | Benches run on 100k `core.Record` with roughly 2 links each and 5 pset values each, on both dialects. Each target's number goes in the perf report with machine details. A miss is fixed or recorded as a deviation with its cause. Bench tests are marked `bench` and excluded from `just test` and `just test-parity`. |
| D14 | `just demo P0-I8` is the Phase 0 exit demo. The receiver in the webhook leg is a loopback HTTP server in the demo, standing in for an external one, which is allowed by the egress guard's test allow-list. The restore leg uses the P0-I7 archive and backup paths. |

## Merge order and conflict owner
A → B → C → D → E. B consumes A's `register_definitions` after A merges: B merges `p0/i8` and adds settings.yaml registration as its last ticket. D merges `p0/i8` before its final measurement. E writes `dev/demos/P0-I8.sh` and `docs/reports/P0-I8.md`. Merge commits only.

## Human gates
| Gate | Approver | Where |
|---|---|---|
| `schema/core/settings.yaml`, `schema/settings/platform.yaml`, extension type catalog entries | Orchestrator under KICKOFF delegation | APPROVALS.md |
| Secret settings and vault; who may lock or set dangerous keys; approval workflows; MCP direct-write mode | Human | Follow-ups in PHASE-0.md |
| Type package signing, directory-backed storage, external writers | Later increment | Follow-ups |

## Risks
- Settings touch many packages (feed, webhooks, lake, MCP, TUI). Only A changes them, merge order is A first, and D2 keeps the list short.
- 100k-record benches are slow on this container. Seeding must use batched unit-of-work appends, not the simulator or the API. A bench run should stay under 15 minutes.
- Concurrency: at most 3 supervisors at once, with at most 3 implementer tickets per batch.
