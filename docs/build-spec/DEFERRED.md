# Deferred side quests

Owner rule (2026-11-07): log major side quests and defer them; do none of them now unless they block the work in hand.
One line each: what, why it waits, and the phase it belongs to. Newest at the bottom of each group.

## Security reviews
| Item | Why deferred | Phase |
|---|---|---|
| Wider security review of the terminal release (beyond the release-path checks) | Release needs only the sign-in, token and server-connection paths checked | Phase 2 exit |
| Web security re-check of everything added since SEC-C4 (web look v2, wave 2 web twins) | The web stays off in production until its next review; it runs with the web increment | Web increment after wave 4 |
| Project membership on reads: unknown or not-a-member project answers the one 404 page (web and API); `item_projects` filtered by membership | Projects are not a read boundary in the MVP (roles-mvp §7) | Phase 3 I8 |
| Wave security reviews for P2-I2 to I5 beyond the per-increment Sec rows | Owner: security reviews are owner-optional; keep to what release needs | Phase 2 exit |
| Per-viewer redaction of scanned-stream events: an IWP readiness event (like a proposal or thread event) that names a hidden record is hidden whole, so a viewer may notice a missing evaluation; redact the hidden ids instead of hiding the event | ADR-0016 accepts whole-event hiding; no hidden id or key is shown | Phase 3 I8 |
| An agent's own module role is not checked when it files a proposal (`submit` skips `require_command_access`), and agents read internal records of any project (agent-first spec 3.1) | People still decide every proposal with their own access; fix with read scoping | Phase 3 |
| Refuse the public try-it `TL_OBJECT_SECRET` value in prod (P2-REL-S2 review F1); the runbook warns until then | Small server check after the terminal release | Phase 2 exit |
| Plain-http refusal only in the TUI; MCP and other ApiClient users are not guarded (P2-REL-S2 F2); runbook requires a TLS proxy | Client-side guard for other clients | Phase 2 exit |
| Split `packages/tl-schema/tests` per file in the gate: the whole folder OOMs in one pytest session on 16 GB | Gate tooling | Phase 2 exit |
| Related Activity rows miss Constraint.Cleared and Proposal.Accepted of linked records (subject is the constraint or proposal id) (P2-INS-S1 F1) | Coverage, not a leak | Phase 3 early |
| Agents and core access words: agents hold no `core.constraint.view`/`.edit`, so the MCP constraint read and propose tools were left out of P2-I2-T09b; define agent grants for core words with the ADR-0027 filing rule | Access change for agents; IWP tools cover wave 2 | Phase 3 |

## Test runs
| Item | Why deferred | Phase |
|---|---|---|
| Full per-folder run more often than once per wave close | Each ticket's own gate is the rule | wave closes only |
| The whole parity suite on Postgres | Dedicated time | Phase 2 exit |
| Phase mutation sweep (30–60 mutants) | Dedicated time | Phase 2 exit |
| `test_stream.py` can hang; a stream test flakes under load (passes alone) | Not blocking; a bounded timeout is the fix | Phase 2 exit |
| The web test seed fails on Postgres (Q4) | The web tests run on SQLite | Web increment after wave 4 |

## Refactors
| Item | Why deferred | Phase |
|---|---|---|
| Pinned module, command and tool lists computed from the registries instead of written by hand | They break on every merge of two modules (wave 1 close: 25 fixes) | Phase 2 exit |
| Tests in other packages import the materials acceptance scripts through `sys.path` (L-P2-I3-1) | Works; move shared fixtures to a test helper package | Phase 2 exit |
| `dev/gate.sh` per-folder mode as the default whole run | The four-part run no longer fits 16 GB; a script does it today | wave 3 close |
| `refresh_preview.sh` leaves the tools out when it stops on a conflict | Replaced by the demo project generator for the tour | with item 1 (generator) |

## Nice-to-haves and small follow-ups
| Item | Why deferred | Phase |
|---|---|---|
| WBS node workflow and constraint opt-in on WBS nodes (ADR-0024 plan check F10) | No wave 2 demo clause needs it; overlaps I5 progress | wave 3 |
| Rule "a new blocking constraint on an Issued IWP puts it On hold" (`field-work-packaging.md` line 58); owner of the rule open (candidate: a readiness hook calling the hold logic) | Not built in P2-I2; P2-I2 STATE Q1 | wave 3 |
| Automatic constraint population from requisitions, scaffold and purchase orders; clear-on-target-state rules; constraints on correspondence and schedule activities (ADR-0024) | Needs the wave 3 modules | wave 3 |
| P2-I2 small follow-ups: IWP register counts ignore the discipline and text filters; IWP list has no Ready/Constraints counts or state-since field (D33); backlog read limit 200; empty mark `-` vs `—`; `Rfi` humanised label | Small UX items from reviews | wave 3 |
| Six materials terminal screens have no technical-mode rows (D, E, I, M, S, W) | Missing feature, not a break | wave 3 |
| `tl mat move reserve --for-line` should take the take-off line key, not its record id | Usability; the runbook points at the API for the id | wave 3 |
| Plain mode shows `@N` in take-off line keys (`P200-200-ISO-0901@0/MTO/001`) and lot references (`P200-RCPT-0001@1`); show them in words (rev 0, line 001) so the plain-text leak check passes. The demo tour marks those two shots technical until then (P2-SEED-T03) | Display change in the materials screens; not a leak of hidden data | wave 3 |
| Locations web page: tree indent and lot counts (WEB1 D46) | Cosmetic | Web increment after wave 4 |
| WBS reload keeps a reinstated node's old title (S7 F6); the CWA target has the same reload shape | The demo needs the same tree only | wave 3 |
| `tl awp worker` has no access word; spec §3 role wording | Docs and a small gate | wave 3 |
| P2-W0 follow-ups: Add property shown to readers who would be refused; technical-mode label gaps; RFI panel overdue uses the wall clock | Small UX items | Phase 2 exit |
| Web pages for the wave 3 and 4 logs; create forms (old P2-WEB2) | Owner: CLI and TUI first | Web increment after wave 4 |
| TUI inside the web page as a second mode | Recommendation no (remote-shell-shaped surface, second UI); see the panel spec §7 | not planned |
| Drawings and model panel extras: preview pictures, `tl-tui[images]`, a following 200-column TUI pane, an external model viewer link, three web layouts | The plan check (F8, F11) keeps v1 small: TUI modal and tab, web drawer | after the web increment |

## Platform features (owner, 2026-11-07, parts B to E)
| Item | Why deferred | Phase |
|---|---|---|
| Native automation rules: an IFTTT- or n8n-style rule builder inside Throughline. Hard parts: authority (a scoped service account, or rules that only file proposals for a person to approve); confidentiality (a rule's effects must not reveal hidden records); rule management (loops, rate limits, rules versioned like schema packages). Until then external tools use the outbound webhooks and inbound mappings | Large; external tools cover it today | Phase 4 or 5 |
| Goal records; a read-only goal view walking from an end state through its open constraints to each target's allowed next actions and who may take them; agents that plan toward an end state and file proposals at each step; automatic intents from readiness and constraint clearing | Intent slot first (ADR-0025); the rest builds on it | Phase 3 |
| Knowledge graph build: the creator tool, the ledger hash chain, the record graph tab and the project graph view (ADR-0026, `specs/graph-views.md`) | Design only now; stubs go in with constraints and intents | Phase 3 (chain with replicas) to Phase 4 |
| Agent-first layer: agent accounts with module roles per project and module, proposal rationale and evidence, a batch review queue, delegation and escalation policies, an agent activity and acceptance view (design note) | Design only now; each new module from wave 3 gets a proposable path | Phase 3 to 4 |
| Insights: data-health checks (missing owner, stale draft, orphan link) on the Checks tab (roadmap insights item 1) | Part C builds the tab on existing checks first | Phase 2 exit |
| Insights: provider registry and router, existing checks wrapped as providers (item 2, ADR-0028) | Needs the contract accepted; Part C needs no registry | Phase 3 early |
| Insights: `cur_insights` projection with recompute, expiry and the dismissal table (item 3) | Needs the registry; no provider yet makes insights | Phase 3 early |
| Insights: telemetry reader (CLI, TUI log, retention, privacy review of free text) (item 4) | Part C writes the table only; a reader needs the viewer filter and a review | Phase 3 early |
| Insights: best-practice library of versioned rule packages (item 5) | Needs a rule format design and the rules-of-credit governance from wave 3 | Phase 3 early |
| Insights: retrieval index on a local similarity model, per clearance or query-filtered (item 6) | Needs a model and licence choice and a vector store in both adapters | Phase 3 mid |
| Insights: suggestions on local models, five kinds (item 7) | Needs items 2, 3 and 6 and real accept and dismiss data | Phase 3 mid |
| Insights: evaluation set from the demo project generator (item 8) | Needs the generator and the first providers | Phase 3 mid |
| Insights: offline behaviour, analysis and ask queued until reconnect (item 9) | Needs Phase 3 sync | Phase 3 mid |
| Insights: security review before any suggestion or analysis provider goes live (item 10) | Owner-optional reviews are kept to what ships; this one gates the first provider | Phase 3 mid |
| Insights: analysis jobs and the per-person inbox (item 11) | Needs a carried viewer in jobs, the queue and a spend decision for non-local models | Phase 3 late |
| Insights: Ask, a record-scoped conversation with cited answers (item 12) | Needs retrieval, analysis jobs, a streaming route and a spend decision unless local | Phase 3 to 4 |
| Insights: web versions of the Insights tab, inbox and Ask (item 13) | Owner: CLI and TUI first | Web increment after wave 4 |
| Activity and Insights extras: "show in graph" from an Activity row, related activity beyond one hop, subtab hot keys, an Activity web page | Part C keeps one hop and the TUI only | Phase 4 and the web increment |
| Intent on the remaining CLI write paths: about 440 `handle_*` calls in tl-cli skip the dispatcher, so their events keep NULL intent (P2-INT-T02 covers record create/void and link add/retract) | P2-INT D6: one wrapper per path is wide; the API, MCP propose tools and these four CLI paths carry intent now | Phase 3 (CLI dispatcher) |
| Intent on the web action route, MCP non-propose tools, and the entries that bypass the dispatcher (simulator, rule and integration runners, jobs, thread dispatch) | P2-INT S2 D5: they keep NULL intent and are reported, not extended | Phase 3 |
| `tl events` reads without intent redaction | Found at P2-INT r3; the CLI reads as the local operator | Phase 3, with the CLI dispatcher |
| A TUI live-remote timing test (`test_remote_a_write_by_another_client_marks_the_row_within_two_seconds`) fails under heavy parallel load and passes alone | Seen at the P2-INT close; timing bound, not a defect found | Next test-hardening slot |
| One write path: `tl_core.dispatch` used by the API, CLI, embedded TUI, runners, proposal accept and MCP (about 17 points) | Outside review 2026-11-09 §3: access, intent and agent checks differ by entry point | Phase 3 (before the web write paths) |
| `TableCommandRunner` (rules, inbound, thread dispatch) carries no intent; an accepted dispatch proposal's intent is lost | Outside review §3 MD | With the dispatcher |
| `POST /types/{t}/records` bypasses `run_command` (no reserved check, no intent) | Outside review §3 MD | With the dispatcher |
| MCP read-side confidentiality not traced end to end | Outside review §3 open question | Next security review |
| Hidden-vs-absent twin walker over every route, MCP tool, CLI read, lake query, webhook mode and SSE (byte compare of two seeded worlds) | Outside review §1: catches the next leak class; F1, F2, F4 were found by reading | Next slice (high priority, ~1 builder piece) |
| Module-declared subject links (`ModuleSpec.subjects`) and a `cur_core_governor` root pointer replacing `SUBJECT_LINKS` and the two-hop bound; `NOT EXISTS` hidden set for scale | Outside review §1 F5 and design; latent until a third module links subjects | Before a third module declares subject links |
| Key oracle: CreateRecord with a key used by a hidden record answers 409; known limit, rate-limit repeated 409s, counter keys in confidential scopes | Outside review §1 F3; uniqueness requires it | Known limit; mitigation with the dispatcher |
| Schema-evolution guard, remaining: (a) generate payload classes for the 163 of 252 event types that have none (append validation only reports them today); (b) declare `link_id` on Link.Added and Link.Retracted payloads (960 undeclared appends in tests) and `note` on Link.Verified; (c) then switch `TL_PAYLOAD_VALIDATION` to `enforce`; (d) static key audit, repo-wide rebuild equality, catalog `additionalProperties: false`, intent round-trip test; (e) compat gate handles `oneOf`/`allOf`/`$ref` when the catalog first uses them; versioned upcasters on the first breaking change | P2-GUARD merged 2026-11-09 (compat gate over all 252 event types in `just check`; append validation in collect mode; report docs/reports/P2-FIX/schema-guard.md) | Next slices (a, b, c first) |
| Declare `link_id` on Link.* payloads and `note` on Link.Verified (additive schema; APPROVALS) | Outside review §2 F2: written today, undeclared | With G3 |
| External-source link on every record type: source system, external id, external URL, shown as a link back to the originating record (P6 activities, legacy registers, ERP items) | Owner 2026-11-09: one more property to carry; an advantage for externally managed entities | With item 9 (design first; additive schema, APPROVALS) |
| Import and sync adapters for our record types with an hourly resync job against live legacy systems (map, upsert by external id, source-owned fields win) | Owner 2026-11-09: "add to the roadmap; the work is deferred" | Roadmap item 9, after the web increment |
| On-device client (phone or tablet) for field flows | Owner 2026-11-09: field users are terminal, web and soon on-device | Roadmap item 7b: spec and ADR first |
| Activity paging stops when a scan budget ends with only hidden candidates (older visible events unreachable); an opaque signed cursor would page on without naming a hidden seq | P2-FIX-CONF review F1 LO: safe truncation chosen | With the twin walker |
| Check whether `Constraint.Raised` `description` or `facts_hash` can carry target information | P2-FIX-CONF review F3 LO | With the twin walker |

## Terminal release follow-ups (P2-REL, 2026-11-07)
| Item | Why deferred | Phase |
|---|---|---|
| Remote CLI: `tl login --remote` and a client under every `tl` command group | Release treats `tl` as an operator tool; the TUI is the user client | Phase 3 |
| Native Windows support; Python 3.13 and later; Postgres other than 16 | Not tested; WSL2 and 3.12 only in the release | Phase 2 exit review |
| PyPI upload, signed wheels, a package index | Release is a wheel directory with `SHA256SUMS` used through `--find-links` | after first user release |
| TLS inside the server; a built-in reverse-proxy example per vendor | Deployer runs a TLS proxy (ADR-0009 deployment duty) | Phase 3 |
| In-app update check and upgrade prompt | Version warning at sign-in only | Phase 3 |
| `packages/tl-api/tests/test_commands.py` grows to about 4 GB resident, so a one-session tl-api gate is OOM-killed on the 16 GB box | Seen at the P2-REL refresh; the folder passes in four file groups | With the gate work (outside review §4) |
| Rename the distribution before publishing (`tl-cli` is an unrelated PyPI package) | Outside review §5; owner release go 2026-11-09 | Before the first public release |
| Twin walker review LO notes: scope the redacted-row `scope` mask to Postgres only; probe only delta and full webhook bodies for the `webhook-target` leak | Re-review 2026-11-10 pass with 2 LO | With the leak fixes |
| Twin-walker leaks (strict xfail in tests/confidentiality/test_twin_walk.py): `File.Attached.deduplicated` reveals a hidden file with the same bytes; webhook delta/full bodies carry a constraint's unreadable `target_id`/`target_kind`; transmittal line positions show a hidden revision's place; a feed card folding a hidden event is dropped whole; `/links/search` `link_total` counts hidden links (owner 2026-11-09: count visible only) | Found by the twin walker 2026-11-09 (strict xfail) | Next slice, before the I5 screens |
| Numbering counters reveal hidden records by gaps (gap-free numbering): known limit like the key oracle; separate counters or gaps for confidential types only if the owner asks later | Owner ruling 2026-11-09 | Known limit |
| `awp.worker.run` is asked at company scope, so a project-only controller cannot run the awp worker | Owner 2026-11-09: fine for the MVP, may change | Revisit after the pilot |
| One export framework for every record type (`tl export <type> --format csv\|jsonl\|xlsx`, `GET /records?type=&format=`, an MCP export tool; viewer-filtered; CSV formula escaping and row cap reused from P2-I5-S3) plus a basic report per module (register, status counts, ageing, overdue) on the lake | Owner 2026-11-09: "probably needed"; yes to the roadmap | Roadmap 7a, with the web increment (~6-8 points) |
| Publish LinkML outputs from `schema/` (JSON-LD context, OWL/RDF, SHACL, docs site), versioned per release and drift-checked in `just check` | Owner 2026-11-09: yes; schemas are LinkML today but only Python models, JSON Schema, DDL, AsyncAPI and OpenAPI are generated | Small item before 7a (~2-3 points) |
| Stable vocabulary address (replace the `https://example.org/throughline/` placeholder ids) | Owner 2026-11-09: defer; the product name may change | After the name is settled |
| I4-A trimmed parts: S3 (fulfil, first-in first-out lots, `stock()`, shortage constraint), T04e2 (`tl req fulfil`), T04f and T07c (labour forecast by craft and week, grid screen), T08a (`tl req report`), S4 (tests piece: each ticket carries its own tests) | Owner 2026-11-09 roadmap row 4b: I4-A keeps raise to close, the work order lifecycle, logs and the propose tool | Roadmap 3c |
| TUI write actions for requisitions and work orders (`action_ui.ACTION_UI` rows, `actions_for` on the two logs; the generic record screen reads no offers), from P2-I4A T07d item 4, 2026-11-11 | The CLI covers every write; the demo reaches the TUI only through the palette | I4-A follow-up (roadmap 3c) |
| MCP `list_requisitions` (and the other requisition read tools) ask no `requisitions.view`; the API and CLI do. Unreachable today: every account holds read in every module through the account role `user` (P2-I4A T10b, 2026-11-11, D-r3h) | Parity with the other surfaces once a role can lack a module's read word | When roles can drop a module's read |
| The shared `x.P123@1.4.0` fixture does not adopt `co.acme.engineering@3.2.0#crane_lift`; the P2-I4 demo pins it in its own schema copy (D-r3g) | A real project adopts a type pset through a schema package change | With the next P123 fixture bump |
| `packages/tl-api/pyproject.toml` does not list `tl-mod-requisitions`, though `tl_api.errors` and the routes import it (works in the workspace only), from P2-I4A S5, 2026-11-12 | A packaged tl-api install would fail to import | Next tl-api ticket or packaging pass |
| The record view clips the last line of the intent panel (the goal line) at any terminal height; highlights tour shot 11 shows two of three lines (P2-I5-T17, 2026-11-12) | A person reads the whole stated intent of an event | Next TUI record-view layout ticket |
| A single tl-api pytest session slows as it grows: in the second half of the files (about 1,100 tests) many late tests pass 4 s each, and `test_stream.py::test_mapped_errors_leave_the_connection_usable` hit its 5 s read budget on p2/punch-s3 (widened there to 30 s); something accumulates across the session (P2-PUNCH S3, 2026-11-13) | The whole suite stays fast and timing-bound tests stay meaningful in long sessions | Phase-exit test-suite care, or when a tl-api half passes 20 min |
| `tl-extract/tests/test_xlsx_hostile.py::test_elements_a_worksheet_does_not_have_are_counted_and_refused` asserts a wall-clock bound of 1.5 s; it took 2.4 s an hour into a split run on p2/punch-s3 and passes alone (2026-11-13) | A parser guard test that does not fail on a loaded machine | With the slowdown row above |
