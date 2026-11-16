# P2-QR-T12 - Docs: QR codes at the workface (module pages, runbook, reference, AGENTS row)

Status: staged (r6; dispatch after QR-T11 merges; with INSP-T15 and PTW-T16 in one batch; base `p2/ip-r3` head at dispatch)
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: P2-QR-T11 (demo merged; verbs and texts final)
Branch: `p2/qr-t12-docs`
Worktree: `/home/user/wt/qr/t12` (from `p2/ip-r3`)

## Goal
The QR increment is documented for a person and for the next agent, as built. Pattern: `docs/tickets/P2-PUNCH/T09-docs.md`. Write only what is built: issue, rotate, revoke, label (tag size only; the `card` and `sheet` sizes are refused with the fixed text), resolve, list, export over `tl qr`; the three API routes; the web scan page `/web/q` and `/web/q/{code}` (sign-in bounce first, one byte-identical miss page, the miss counter and its 429, headers, the log filter and the proxy note); the frozen card contract and how a module ships a card (`throughline.scan_cards`; the three cards built: IWP, inspection, permit); the setting `api.public_base_url` and `qr.codes_per_record_max`; ADR-0030 (accepted). Not built (list once, pointing at `docs/build-spec/DEFERRED.md` and the plan's follow-up slice): the scaffold card (T05, waits for the scaffold module on trunk), client methods, the terminal print action, the web print form, `tl qr sheet`, PDF labels, anonymous scans. A tour shot of the scan page does not exist (the tour drives the terminal only); say where the page text is shown (the demo clause 2 and 7). Read `.claude/skills/throughline-docs/SKILL.md` first.

## Brief
1. `packages/tl-modules/qr/README.md` and `AGENTS.md`: as-built words (`qr.view`, `qr.issue`, `qr.revoke`; `qr.read` is the route guard on no agent list), hash-only storage, the one-exit resolver, the secret code leaves only through `service.issue` and `rotate` (D12), `label_fields`, the package rules.
2. Root `AGENTS.md` "Where things go": one row for QR (module package, schema `schema/modules/qr/`, contract `packages/tl-core/src/tl_core/qr/`, CLI `cli.py`, API `routes.py`, web `packages/tl-web/src/tl_web/pages/scan.py`, `scan_limit.py`, demo `dev/demos/P2-QR.sh`, runbook). Append only; the other two increments append in the same batch.
3. `docs/runbooks/qr-labels.md` (create: set the base address, print a label for an IWP, rotate when a label is lost, revoke, what each refusal means quoted from the reports, the proxy note for the access log and the real client address, the miss limit), `docs/reference/qr.md` (create: routes, verbs, setting keys, the card contract fields and bounds, how to add a card), `docs/modules/qr/README.md` (create: model `docs/modules/correspondence/`).
4. `docs/reference/access-words.md`: the three QR words, copied from the yaml.

## Context (read these, nothing else)
- `.claude/skills/throughline-docs/SKILL.md`, `docs/reports/P2-QR/*.md`, `docs/reports/P2-IP/QRT11.md`, `docs/adr/0030-*.md` (decision section only), `docs/build-spec/specs/qr-workface.md` (sections 1-6)
- `docs/runbooks/punch-list.md` (shape only), `packages/tl-core/src/tl_core/qr/types.py`

## Allowed paths
- `packages/tl-modules/qr/README.md`, `packages/tl-modules/qr/AGENTS.md`, `AGENTS.md` (one row), `docs/modules/qr/`, `docs/runbooks/qr-labels.md`, `docs/reference/qr.md`, `docs/reference/access-words.md`
- `docs/reports/P2-IP/QRT12.md` (create)

## Acceptance
```
ls packages/tl-modules/qr/src/tl_mod_qr/cli.py packages/tl-modules/qr/src/tl_mod_qr/routes.py packages/tl-web/src/tl_web/pages/scan.py packages/tl-core/src/tl_core/qr/types.py dev/demos/P2-QR.sh
uv run tl qr --help
```
Expected: every path and command named in the new pages exists (the report lists the `ls` and the help output's first lines). No `just check` (docs only; the orchestrator runs it at DONE).

## Tests to add
None (docs).

## Escalation triggers
A verb, route or text in the reports differs from what the runbook needs to say (write which); a word in the yaml differs from the S1 report.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines. Commit subjects `P2-QR-T12: ...` with the trailers the dispatch message names; no model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
