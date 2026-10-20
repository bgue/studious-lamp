# P1-I6-T11 — Package READMEs and AGENTS notes for RFI, Commercial and the evidence trail

Status: ready
Tier: haiku
Labels: docs
Depends on: — (all code is on the branch)
Branch: `p1/i6-t11-package-docs`

## Goal
Four package READMEs and four AGENTS.md files describe the P1-I6 additions, so the next agent finds them. Documentation only: no code, no test, no schema.

## Brief references (pasted)
> **Facts to write, nothing else.** Do not invent behaviour; every sentence below is checked by the supervisor.
>
> - P1-I6 adds two domains to the correspondence module: **Technical** (record type `correspondence.TechnicalItem`; kinds RFI, TQ, deviation; numbers `P123-RFI-0001`) and **Commercial** (`correspondence.CommercialItem`; kinds early warning `EW`, change notice, site instruction, quotation, claim notice, detailed claim, payment application, back charge). Each item is a row of the item table plus a domain table.
> - **Access.** Technical: raising, drafting, answering are `user`; issue and escalate are `controller`. Commercial: every command is `controller`, and any command that changes a Commercial item or its clocks (including generic link, file and property-set commands, and cancelling a time bar) needs a controller viewer whatever its access word.
> - **Time bars.** A clock of kind `time_bar` starts from the day the raiser became aware (`aware_on`); the clause overrides the length; issuing meets the bar (late if after the due day). The figures are configurable per contract and illustrative.
> - **Escalation.** `EscalateTechnical` turns an RFI with a cost or schedule impact into a linked Early Warning (Draft) and writes nothing on the RFI stream. The rule that proposes it automatically is not part of this ticket.
> - **Evidence trail.** `GET /projects/{project}/correspondence/{number}/evidence` (operation `get_evidence_trail`): the linked items and events of an item as they stood at the end of a given day (`as_of`), bounded to depth 3, 200 nodes, 1000 links, 5000 events; each node is filtered by the viewer, a hidden node does not exist.
> - **Confidentiality** (ADR-0016) applies to every read and export; a hidden item answers as an unused number. Roles come only from the signed-in account.
> - **API.** Reads (action `correspondence.read`, open to agents): `GET /projects/{project}/rfis[/{number}]` (`list_rfis`, `get_rfi`), `GET /projects/{project}/commercial[/{number}]` (`list_commercial`, `get_commercial`), `GET /projects/{project}/correspondence/{number}/evidence`. The commands of `tl_mod_correspondence.commands` are now 47, 24 of them `controller`; `docs/reference/openapi.json` is regenerated.
> - **MCP.** Five new read tools in `tl_mcp.correspondence_tools`: `list_rfis`, `get_rfi`, `list_commercial_items`, `get_commercial_item`, `get_evidence_trail`. They are read-only (`correspondence.read`); an agent never sees a Commercial item (controller only), and a hidden one answers as an unused number.
> - **CLI.** `tl rfi ls|show|raise|update|submit|return|issue|answer|review|reissue|close|escalate`; `tl comm ls|show|raise|update|submit|review|return|issue|assess|close|legal|export`; `tl evidence NUMBER --project P [--as-of DAY] [--depth 0-3] [--json]`. `tl comm export` writes a private file (mode 0600, refuses a symlink, refuses to overwrite without `--force`, at most 5000 rows) and leaves out items above internal unless the class is named. Delivery of an issued item is a stub: nothing is sent.
> - **Feed.** `Technical.Answered` and `Commercial.Assessed` (with `Correspondence.Issued`) make feed cards; the cards are tagged with the record, so a reader sees only cards of records they may read. After upgrading, run `just rebuild-projections feed` to tag cards already projected.
> - Module spec: `docs/modules/correspondence/technical-commercial.md`; decision record `docs/adr/0019-domain-items-and-evidence.md`; plan `docs/tickets/P1-I6/README.md`; runbook section "RFIs and Commercial" in `docs/runbooks/correspondence.md`; demo `just demo P1-I6`.

## Interfaces (verbatim from repo at the branch point)
None. Each README has a table `| Symbol | Kind | Purpose |` (public interface) or a table of `| ... | commands | ... |` rows; add rows in the same style as the neighbours.

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/README.md`, `packages/tl-modules/correspondence/AGENTS.md`
- `packages/tl-api/README.md`, `packages/tl-api/AGENTS.md`
- `packages/tl-mcp/README.md`, `packages/tl-mcp/AGENTS.md`
- `packages/tl-cli/README.md`, `packages/tl-cli/AGENTS.md`
- `packages/tl-tui/README.md` (as an example of how this increment was already documented there)
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/README.md`
- `packages/tl-modules/correspondence/AGENTS.md`
- `packages/tl-api/README.md`
- `packages/tl-api/AGENTS.md`
- `packages/tl-mcp/README.md`
- `packages/tl-mcp/AGENTS.md`
- `packages/tl-cli/README.md`
- `packages/tl-cli/AGENTS.md`

## Steps
1. `tl-modules/correspondence/README.md`: add a row to the public-interface table for the Technical and Commercial handlers and flows (the package `handlers` gains `technical`, `technical_flow`, `commercial`, `commercial_flow`, `escalate`; the modules `evidence`, `export`, `registry_domain`, `reports_technical`, `reports_commercial`, `views_domain` are new), change "28 commands" to 47 (24 `controller`), add `tl rfi`, `tl comm`, `tl evidence` to the used-by line, and add the new read tools to "five read tools". Change the Status line to "Introduced in P1-I5; Technical, Commercial and the evidence trail added in P1-I6 (plan: `docs/tickets/P1-I6/README.md`)".
2. `tl-modules/correspondence/AGENTS.md`: add three bullets: (a) every Commercial command and every command touching a Commercial item or its clocks needs a controller viewer (`require_controller_for`, `controller_only` guards); a new command or generic guard must keep that; (b) feed cards for a confidential stream are tagged through `subjects_of`; a new event type that makes a card must be added to `POLICY_EVENT_TYPES` deliberately; (c) the evidence trail and the export are bounded; do not raise `MAX_ROWS` (5000) or the trail bounds without an ADR.
3. `tl-api/README.md`: extend the row for `tl_api.routes.correspondence` with the new routes and the new command count, in one sentence each. `tl-api/AGENTS.md`: one bullet: a route that returns a Commercial item is controller-gated by the module, the route adds no check of its own; `export_too_large` is the error row for a register export above 5000 rows.
4. `tl-mcp/README.md`: extend the correspondence tools row with the five new tools. `tl-mcp/AGENTS.md`: one bullet: Commercial items do not exist for an agent; a new read tool on correspondence data must go through `guarded(...)` with a `resource_name`.
5. `tl-cli/README.md`: add a row for `tl rfi ...`, `tl comm ...` and `tl evidence` with the command lists above and the export rules. `tl-cli/AGENTS.md`: one bullet: files written by `tl comm export` go through `_write_private`; do not write a second path.
6. Keep each added sentence in the style of its neighbours: plain, present tense, no emoji, no model names, ISO dates if any.

## Acceptance
```
just check
git diff --stat
```
Expected: `just check` exits 0; only the eight allowed files changed.

## Tests to add
None (documentation).

## Report requirements
Standard report (`docs/templates/haiku-report.md`). List any fact above you could not match to the code you read, instead of guessing.

## Escalation triggers
- Stop and report *Blocked* if a README table has a different shape from the one described, or a fact above contradicts the code.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
