# Module spec: Technical / RFI and Commercial domains

Status: accepted for Phase 1. Written by: P1-I6 supervisor. Brief sections: §9 (M10), §16, §18.10, §7.3.
Decisions: ADR-0019 (this increment), ADR-0016 (confidentiality), ADR-0013 (document controller), ADR-0015 (cost and schedule).
Read first: `README.md` in this directory (the correspondence core).

## Purpose
Two domains of the correspondence module have a workflow, data and clocks of their own. **Technical** is a question to the
designer or the client (RFI), a technical query (TQ) or a request to deviate from the design (deviation). **Commercial** is a
notice or a claim under the contract: early warning, change notice, site instruction we received, quotation, claim notice,
detailed claim, payment application, back-charge. An answered RFI that says "yes" to cost or schedule impact leads to a linked
Commercial item. The chain around a Commercial item can be read as the ledger knew it on any past day (the evidence trail).

## Record types
| Type | Tables | Numbered | Workflow |
|---|---|---|---|
| `correspondence.TechnicalItem` | `cur_correspondence_correspondence` + `cur_correspondence_technical_item` | `P123-RFI-0001`, `P123-TQ-0001`, `P123-DEV-0001` | `correspondence.technical` |
| `correspondence.CommercialItem` | `cur_correspondence_correspondence` + `cur_correspondence_commercial_item` | `P123-EW-0001`, `-CN-`, `-SI-`, `-QT-`, `-CL-`, `-DC-`, `-PA-`, `-BC-` | `correspondence.commercial` |

An item is a row of the item table (number, parties, dates, class, thread, clocks, files, the register) and a row of its
domain table, written from the events of one stream: `Correspondence.Defined`, then `Technical.Defined` or
`Commercial.Defined`. The register, the clocks, the threads, the files and the class commands work on the new items
unchanged. The commands that move a plain letter through Received, Triaged, Issued and Responded refuse them
(`require_core`), and a letter cannot be triaged or re-classified into either domain.

## Workflows
No transition carries a role guard; the access word of each command decides who may run it.

| `correspondence.technical` | |
|---|---|
| Draft | `submit` to Internal review; `void` to Void |
| Internal review | `return` to Draft; `issue` to Issued; `void` to Void |
| Issued | `await_response` to Awaiting response (issuing does both moves) |
| Awaiting response | `answer` to Answered; `close` to Closed |
| Answered | `accept` to Accepted; `reject` to Rejected |
| Rejected | `reissue` to Internal review; `close` to Closed (with a reason) |
| Accepted | `close` to Closed |

| `correspondence.commercial` (contractual definition, approved under ADR-0008 decision 6) | |
|---|---|
| Draft | `submit` to Commercial review; `receive` to Awaiting assessment (a site instruction we received); `void` to Void |
| Commercial review | `review` to PM approval; `return` to Draft; `void` to Void |
| PM approval | `issue` to Issued; `return` to Draft; `void` to Void |
| Issued | `await_assessment` to Awaiting assessment (issuing does both moves) |
| Awaiting assessment | `agree` to Agreed; `dispute` to Disputed; `part_agree` to Partially agreed |
| Agreed, Partially agreed | `close` to Closed |
| Disputed | `close` to Closed (with a reason); `escalate` to Escalated (the legal route) |

## Commands and who may run them
`tl_mod_correspondence.commands.API_COMMANDS` lists them; `user` is any signed-in person, `controller` an admin or a document
controller (action `control.command.<Name>`). An agent never runs a command; it proposes, and a person accepts.

| Access | Commands |
|---|---|
| user | `RaiseTechnical`, `UpdateTechnical`, `SubmitTechnical`, `ReturnTechnical`, `AnswerTechnical`, `ReviewTechnicalAnswer`, `ReissueTechnical`, `CloseTechnical` |
| controller | `IssueTechnical`, `EscalateTechnical`, and **every Commercial command**: `RaiseCommercial`, `UpdateCommercial`, `SubmitCommercial`, `ReviewCommercial`, `ReturnCommercial`, `IssueCommercial`, `AssessCommercial`, `CloseCommercial`, `ReferCommercialToLegal` |

A Commercial item is `restricted` by default (commercial roles and the project manager is what ADR-0016 can say today: the
document controller and admin), so a handler refuses a viewer below that level before it reads or writes
(`require_controller_viewer`). Who acts comes from the signed-in account; a command has no field for roles (P1-SEC1).

## Data
Typed columns, not property sets. Money is a decimal text with two places (`12500.00`), hours one (`240.5`), both read as
`Decimal`; a currency is three upper-case letters; amounts of different currencies are never added. The cost-code impacts of a
notice are a bounded list (50) of `{cost_code, amount, hours, quantity, uom}`, one entry per cost code. `[0-9]` is the only
digit accepted.

| Technical | Commercial |
|---|---|
| question (also the register text), proposed solution, discipline, required by (also the register's response date), the raiser's cost and schedule flags, the answer, the answered day, the answerer's cost and schedule statement, the item that carries the answer, the answering revision, the review decision, day and note | contract clause, the day the contractor became aware, the item it was escalated from, currency, estimated value and hours, cost-code impacts, schedule impact (days and note), entitlement basis, the assessment (status, value, day, note) |

## Clocks
Technical: one `response_from_them` clock starts at issue and counts to the day the answer is needed; the answer meets it and
closing the item cancels it. Commercial: a `time_bar` clock starts when the item is made and counts from `aware_on` (today or
earlier); a named contract clause sets its length and day type and is cited; issuing the notice **meets** the bar on the issue
day (a bar met after its due day, or expired, is reported as late); the assessment clock starts at issue and the assessment
meets it. The figures in `schema/fixtures/correspondence/domains/commercial.yaml` are illustrative and configurable per contract.

## Escalation
`EscalateTechnical` (controller) makes a Draft early warning from an answered RFI: `aware_on` is the answer day, the class is
the higher of the RFI's and `restricted`, and a `derived_from` link written by the module (a person cannot retract it) joins
them. Nothing is written on the RFI's stream; the RFI shows its escalations (`TechnicalView.escalations`) only for items the
reader can read. A rule (P1-I7) proposes the command when an answer says yes to cost or schedule impact.

## Reports and reads
| Read | Surface |
|---|---|
| RFI log: every Technical item with raised, issued, needed and answered days, response days, on time, overdue, the impact flags of both sides, and counts | `reports_technical.rfi_log`; API `GET /projects/{project}/rfis`; MCP `list_rfis`; CLI `tl rfi ls` |
| One RFI | API `GET /projects/{project}/rfis/{number}`; MCP `get_rfi`; CLI `tl rfi show` |
| Commercial register: every notice and claim with clause, time bar (due, days left, late), estimated and assessed value, variance; totals per currency | `reports_commercial.commercial_register`; API `GET /projects/{project}/commercial`; MCP `list_commercial_items`; CLI `tl comm ls` |
| One Commercial item | API `GET /projects/{project}/commercial/{number}`; MCP `get_commercial_item`; CLI `tl comm show` |
| Evidence trail | `evidence.evidence_trail`; API `GET /projects/{project}/correspondence/{number}/evidence`; MCP `get_evidence_trail`; CLI `tl evidence` |
| Cost-system export | `export.commercial_export`; CLI `tl comm export` only |

Every read goes through `registry_domain` or the viewer filters; an item the reader may not see is not in a list and answers
"not found" with the words of an unused number.

## The evidence trail
A replay of the ledger. "As of D" means every event recorded up to the end of day D (UTC): a record that did not exist is
absent, the title, state and void flag are those the events had reached, a link is as its own events left it, and the figures
of an item are folded from its events. Visibility is **today's**: a record or link the reader cannot read now is left out
whatever its class was on D, and nothing says how many were left out. The walk is breadth first and bounded (depth 3, 200
records, 1000 links, 5000 events per stream); `truncated` says a bound was hit.

## The export
`tl comm export --project P --class restricted [--out file]` writes the pending (issued, awaiting assessment, disputed,
escalated) and approved (agreed, partly agreed) changes as CSV. It is a bulk export (§18.10): the classes are named (default
`internal`, which holds no Commercial item), `restricted` needs a controller viewer, `privileged` is never exported, a cell
that a spreadsheet would run as a formula starts with a quote, and the count of readable items left out for their class is
told on standard error.

## Feed
`feed_policy` (`full`, `minimal`, `none`) and `feed_text` are keys of the event payload of `Correspondence.Issued`,
`Technical.Answered` and `Commercial.Assessed`, written by the handler from the domain file. Technical is `full`, Commercial
`minimal` ("A commercial notice was issued"). `tl_core.feed.cards` makes a card of its own for `full` and `minimal`, about the
event's own record (the class filter hides it with the record), and none for `none`.

## The constraint hook
`constraints.ConstraintSink` is called when an RFI is issued and when it is answered. The default sink records nothing;
Phase 2 puts the AWP constraint behind it.

## Tests
`packages/tl-modules/correspondence/tests/`: `test_technical.py`, `test_technical_flow.py`, `test_commercial.py`,
`test_commercial_flow.py` (one per ticket), `test_domain_flow.py` (an RFI to a notice), `test_reports_technical.py`,
`test_reports_commercial.py`, `test_evidence.py`, `test_export.py`; the five-reader walks are
`packages/tl-api/tests/test_confidentiality_walk.py` and `packages/tl-mcp/tests/test_confidentiality_walk.py`.
