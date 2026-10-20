# Increment plan — P1-I6 Technical / RFI and Commercial domains, escalation paths

Status: in-progress
Supervisor session: 2026-10-20
Brief sections: §9 M10 (domain layer, "Initial domains": Technical / RFI and Commercial; "Cross-domain behaviour": escalation paths, clock dashboard, evidence trail, feed and webhooks follow each domain's policy), §9 M5 (an RFI is a Technical-domain item that feeds AWP constraints), §9 M11 (the register exports to the cost system as pending or approved changes), §18.8 (the rule: an RFI answer with a cost impact proposes a linked commercial change notice and starts its clock), §18.10 (restricted classes are left out of exports), §8 (permissions), §7.2 (links)
Branch: `p1/i6` (trunk `claude/wizardly-allen-m2v96s` at 61717ad). Parallel increment: P1-I7 (`p1/i7`), whose rules engine T05 builds on.
Decisions: ADR-0010 (+ addenda), ADR-0011, ADR-0013, ADR-0016 (items of both domains are correspondence items and inherit it), ADR-0017 (rules in propose mode), and the new ADR-0019 (domain items, time bars, escalation, the evidence trail; number to be confirmed by the orchestrator).

## Objective
Give the correspondence module its second and third domains. **Technical / RFI** (requests for information, technical queries, deviation requests) is raised by anyone, issued by a document controller, answered with a statement on cost and schedule, and accepted or sent round again. **Commercial** (early warning, change notice, site instruction, quotation, claim notice, detailed claim, payment application, back-charge) has contractual time bars that count from the day the contractor became aware, values by currency and cost code, and its own workflow; its items are `restricted`. An answered RFI that says yes to cost or schedule **escalates** to a Commercial item (a draft early warning, `derived from` the RFI, whose time bar counts from the day of the answer) by a command a person runs or a rule proposes. One **evidence trail** view assembles the chain around a Commercial item (RFIs, documents at the pinned revision, cost codes, schedule activities, other correspondence) **as of a date**, by replaying the ledger. Registers and reports list both domains with the figures the brief names, the Commercial register exports to the cost system as CSV, and the feed shows a card per the domain's policy (full, minimal, none). Nothing leaves the machine: sending stays a stub.

## Demo
`just demo P1-I6` (SQLite and Postgres; `dev/demos/P1-I6.sh`, driver `dev/demos/p1_i6_demo.py`), one PASS line per clause:
1. raise an RFI pinned to `ISO-1234` rev B (`tl rfi raise`), submit it, a document controller issues it: a PDF rendition, a stub send, a response clock that ends on the day an answer is needed;
2. the client answers with `cost_impact = yes`: the RFI is Answered, its clock is met on the day, the feed shows a **full** card;
3. the rule (or `tl rfi escalate`) proposes a linked Early Warning; a controller accepts it: a Draft `P123-EW-0001`, `derived from` the RFI, restricted, with a **14-day time bar** counted from the answer;
4. the same Early Warning does not exist for a user or an agent (same answer as an unused number) and its feed card, register line and export are absent for them;
5. the Early Warning goes through commercial review, PM approval and issue: the time bar is met, a **minimal** card says only that a notice was issued;
6. the other party assesses it as partially agreed with a value: the register shows estimated against assessed per currency;
7. the **evidence trail** assembles the chain as of the answer date, and again as of today; the earlier view leaves out the later links and states;
8. `tl comm export` writes the pending and approved changes as CSV for a controller, with spreadsheet formulas quoted, and refuses to write restricted items without a named class.

## Design decisions (supervisor, within the plan)
| # | Decision |
|---|---|
| D1 | A workflow belongs to a record type (brief 8; `tl_core.workflow.loader`), and a domain has its own workflow, so each domain with its own workflow has a record type of its own: `correspondence.TechnicalItem` and `correspondence.CommercialItem` (General and Document control keep `correspondence.Correspondence`). Such an item is a row of the item table (`cur_correspondence_correspondence`: number, parties, dates, class, thread, clocks, files, register) **and** a row of its domain table (`cur_correspondence_technical_item`, `cur_correspondence_commercial_item`), both written from the stream of one record. The plan's three LinkML classes (`RFI`, `TechnicalQuery`, `DeviationRequest`) became one class with a subtype, because the three share every field and a workflow. |
| D2 | Domain data is typed columns, not psets: the export and the register need exact values and the validation of a command. Money is a decimal text with two places, hours with one, never a float; the cost-code impacts are a bounded JSON list. A domain file may still name `required_psets`. |
| D3 | Numbering: one pattern per type with a `kind` field filled from the subtype's `number_code` (`P123-RFI-0001`, `P123-EW-0001`); each kind counts on its own. |
| D4 | Access. Technical: the raiser's side (raise, update, submit, return, answer, review, reissue, close) is any signed-in person; issuing and escalating are a document controller's. Commercial items are `restricted` by default (ADR-0016's approximation of "commercial roles plus the PM"), so **every Commercial command is a controller's** and its handler refuses a viewer below that level before it writes; workflow files carry no role guard (D6b of P1-I5). No new role. |
| D5 | Time bars: a clock of kind `time_bar` with the trigger `awareness` starts when a Commercial item is made, counted from `aware_on`. An item that names a contract clause takes the clause's length and day type and cites it. Issuing the notice **meets** the bar on the issue day; a day after the due date shows as late (`time_bar_late`). Restarting or cancelling a bar is a controller's act (ADR-0016 D6). The figures in the domain file are an illustrative default that the contract overrides: **the workflow and the clock definitions are a contractual gate** (04-gates.md section 2), approved by the orchestrator. |
| D6 | Escalation (`EscalateTechnical`, controller): the new item is a Draft early warning (or another subtype) with a `derived_from` link the module writes as its own (a person cannot retract it), the day of the answer as `aware_on`, and a class no lower than the RFI's. **Nothing is written on the RFI stream**: an event there that named a restricted item would hand its number to every reader of the RFI. The RFI shows its escalations only to a reader of the new item, through the link. A rule (P1-I7, propose mode) proposes the command; a person accepts. |
| D7 | Core items and domain items share the clocks, threads, files, class and clearance commands. The commands that move a core item through Received, Triaged, Issued and Responded refuse a domain item (`require_core`); a letter cannot be triaged into a domain that has its own record type (the suggestion engine never proposes one). Re-classification between a core domain and these two is a linked new item (brief: after issue a misfiled item gets a linked item). |
| D8 | Evidence trail (T06): a replay of the ledger. "As of D" means every event recorded up to the end of day D (UTC): a record that did not exist is absent, a state is the one the workflow events had reached, a link is as its events left it, and an item's figures are folded from its events. Visibility is **today's**: a record or link the viewer cannot read now is left out, whatever its class was on D, and nothing says how many were left out. Bounded: depth, nodes and events per stream. |
| D9 | Feed policy (T08): a handler writes `feed_policy` and `feed_text` into the payload of the events that make a card (`Correspondence.Issued`, `Technical.Answered`, `Commercial.Assessed`) from the domain file; `tl_core.feed.cards` honours them (none: no card; full or minimal: a card of its own with that line, about the event's record so the class filter hides it with the record). The policy is in the event, so a rebuild never depends on a file that changed later. |
| D10 | Export to the cost system (T04c, security-sensitive): CSV of the Commercial register with status `pending` (not yet agreed) or `approved` (agreed or partially agreed), amounts exact, formulas quoted, only the classes a controller names (default `internal`, which is empty for restricted items: the controller must say `--class restricted`). |
| D11 | The constraint hook (T02) is a stub: a Protocol, `ConstraintSink`, called when an RFI is issued and when it is answered, with a default sink that records nothing; Phase 2 puts the AWP constraint behind it. |
| D12 | No new dependency. |
| D13 | A `reason` on an update of an item in review is advisory: it is recorded with the change and not required (T02a asked; the docstrings of `UpdateTechnical` and `UpdateCommercial` now say so). | 
| D14 | `expected_version=0` on a module command is treated as not given (`cmd.expected_version or item.version`), as in the 19 sites of P1-I2 and P1-I5; stream versions start at 1, so 0 is never a real version. A module-wide change to `is not None` is a follow-up for the orchestrator, not part of this increment. |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | T01 and T03 schema: `technical_item.yaml`, `commercial_item.yaml`, events, workflows, domain files, numbering, file slots, domain format extension | Schema (human-gated, SCHEMA_APPROVALS); contractual workflow and clocks (human-gated) | orchestrator | done (9d00d21) |
| S2 | T08 core: the feed policy in the card rules and the feed projector | Core projection | orchestrator | done (833fa0e) |
| S3 | Module generalisation (record type per item, `require_core`), projectors, registry reads, domain helpers, reference handlers, commands table, test world | Interfaces first; references of the tickets | — | done (122e96c) |
| S4 | T06 evidence trail | Time-travel reads, confidentiality | orchestrator, security review | done (f43aa36) |
| S5 | T04c cost-system export | Export, confidentiality | security review | done (9de0abb) |
| S6 | API routes, `ApiClient`, MCP read tools, controlling set, walking tests | Access and confidentiality surfaces | security review | done (f43aa36, 9de0abb) |
| S7 | CLI `tl rfi`, `tl comm`, `tl evidence` | Controller gates, export | security review | done (9de0abb) |
| S8 | TUI client interface and fakes | Interface other tickets consume | — | done (f43aa36, 9de0abb) |
| S9 | T05 escalation rule on the P1-I7 engine | Rules; waits for the engine | orchestrator | pending (last) |
| S11 | Residuals of the security re-check (private export file, own overflow error, scan cards tagged with their record) and the decisions D13, D14 | Confidentiality | orchestrator | done (32c7ed6, 8d2f946) |
| S17 | Fake client counts open RFIs as the report does (answered excluded); screen pilot test restored | Interface fix | none | done (b945bdf) |
| S18 | Simulator: RFI author and client representative, TechnicalDesk client methods, numbering spells the project without symbols (core change) | Core numbering | security review, orchestrator | done (6856497) |
| S19 | Demo `just demo P1-I6` (nine clauses, sqlite and postgres) | Cross-cutting | none | done |
| S20 | Ticket T11 (package docs), plan update | Docs ticket for Haiku | none | done |
| S15 | TUI domain screen (Ctrl+G), evidence text, client fake seed, embedded reads test | Screen glue and wiring | — | done (394961d) |
| S10 | Security review fixes F1 to F8 (Commercial controller gate on every command, feed cards of confidential streams, answering records readable by the item's readers, bounded evidence query, private export file, export row limit, issue day floor) | Core feed change; confidentiality | orchestrator re-check of F1 and F2 | done (eb31ba2) |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | LinkML for the Technical domain and its workflow | S | — | done | S1 (one class, see D1) |
| T02a | Technical raise, update, submit, return | H | S3 | merged (dd3260b) | passed first time; asked whether a review reason is required (D13) |
| T02b | Technical issue, answer, review, reissue, close | H | T02a | merged (116594e) | passed first time; review and reissue results now list their events (8d2f946 + S16) |
| T03 | Commercial domain: subtypes, workflow, clocks, numbering | S | — | done | S1, S3 (orchestrator approval) |
| T04a | Commercial raise, update, submit, review, return | H | S3 | merged (66f768f) | passed first time; asked about the link version (correct: links are streams of their own) and `expected_version` 0 (D14) |
| T04b | Commercial issue, assess, close, refer to legal | H | T04a | merged (755f763) | passed first time |
| T04c | Cost-system export (CSV) | S | T09b | done | S5 (9de0abb) |
| T05 | Escalation RFI to Commercial: the command (S3) and the rule on the I7 engine | S | S3, P1-I7 on trunk | pending | S9 |
| T06 | Evidence trail query | S | S3 | done | S4 (f43aa36) |
| T07a | TUI: the text of the RFI log (cells, summary, panel) | H | S8, T09a | merged 0cee9ab | the screen, the key (Ctrl+G) and the evidence text are supervisor pieces (S15) |
| T07b | TUI: the text of the Commercial register | H | S8, T09b | merged 411f397 | |
| T08 | Feed policy per domain | S | S2 | done | S2 and the handlers of S3 (L-P1-I3-5: the cards cannot be tested apart) |
| T09a | RFI log report | H | S3 | merged (63d7dc1) | passed first time; one equivalent guard added for pyright (L-P1-I6-1) |
| T09b | Commercial register report | H | S3 | merged (3f753af) | passed first time |
| T10 | Simulator: client representative answers RFIs; RFI author; demo; report | S | T02, T04, T09 | built by the supervisor (S18, S19): the owner asked for Haiku tickets only after it was built; no commercial sim actor (sim people hold role user) | S18 |
| T11 | Package READMEs and AGENTS notes for RFI, Commercial and the evidence trail | H | all code | ready | |

## Order of work
1. Plan, schema, generalisation, references, reports interfaces: done. First batch: T09a and T09b.
2. Evidence trail, export, API, MCP, CLI, TUI client interface (supervisor).
3. Second batch: TUI tickets (T07a, T07b).
4. Stub the handler files of the batch from their references and dispatch T02a and T04a (batch 2), then T02b and T04b (batch 3); the other pair stays a reference in the tree meanwhile (L-P1-I6-5). Restore the held tests (`held/test_domain_flow.py.txt`, `held/test_evidence.py.txt`) once all four are merged.
5. Third batch: simulator (T10). Ask the orchestrator whether P1-I7 is on trunk; merge it; build T05 on the real engine.
6. Demo, docs, runbook, ADR, report, gates, security review.

## Risks and escalation triggers
- **Confidentiality reaches every new read path** (registers, reports, export, evidence trail, feed cards, API, MCP). Mitigation: every read goes through `registry_domain` or the viewer filters; walking tests as five kinds of reader; the evidence trail and the export are listed for security review.
- **The time-travel query leaks** if it reads links or events without the filter, or counts what it left out. Mitigation: D8, a test that a hidden link, a hidden item and a class raised after the date show nothing.
- **P1-I7 lands late.** T05 is last; the command exists without the rule.
- Stop and escalate if a core contract must change beyond the card keys of D9 (the feed projector and `tl_core.feed.cards`; additive, reported in NOTE), or if a role other than `admin` and `document_controller` is needed.

## Blocked / Decision
None open.
