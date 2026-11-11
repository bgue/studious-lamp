# P2-PUNCH-T08 — Demo `dev/demos/P2-PUNCH.sh`: seven clauses, SQLite then Postgres

Status: staged (last code ticket: needs T02, T03, T04, T05, T06, T07 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: demo, tests
Depends on: T02, T03, T04, T05, T06, T07
Branch: `p2/punch-t08-demo`
Worktree: harness-created under `/home/user/wt/punch/t08` (from `p2/punch` head)

## Goal
`just demo P2-PUNCH` runs the seven clauses of `docs/tickets/P2-PUNCH/README.md` "Demo clauses" once on SQLite and once on Postgres, one `PASS clause N: ...` line each. **A PASS line is printed only after a real check returned success** (a command's exit code and an output comparison, or a driver assertion); a miss prints `DEMO FAILED` and exits non-zero; there is no `echo PASS` on a path that checked nothing. Pattern: `dev/demos/P2-I3.sh` and `p2_i3_demo.py` (header, backends, driver modes, TUI through the palette, MCP session) and `dev/demos/P2-I2.sh` (helpers `tl`, `as`, `expect`, `refuse`, `clause`, `run_backend`, the cleanup trap). State changes only through real commands; no projection write anywhere.

## Clauses and their exact verbs (the README table is the spec of record; use these, never re-derive an argument)
Setup by commands: project `P123`; `sue` holds the module superuser role on `quality` (`tl admin roles grant sue --project P123 --module quality --role superuser --reason demo`, as `P2-I3.sh` line 116 does for materials); `uma` and `rob` plain users; `dora` the document controller; one IWP, one tag and one document made as `P2-I2.sh`, `P1-I1.sh` and `P1-I2.sh` make theirs (read the verbs there; the IWP number is read back from `tl awp iwp ls`, never assumed).
1. Raise to verify: `tl punch raise --subject "Gasket missing on F12" --area A1 --system 47-01 --due 2026-11-20 --category A --assignee user:rob --from <IWPNUMBER>` as uma prints `raised P123-PUN-0001  version` (compare the prefix); `tl punch ls --state Open` lists the key; `tl punch clear P123-PUN-0001 --note "Gasket fitted"` as rob; `tl punch verify P123-PUN-0001` as rob is refused (`the person who cleared a punch item may not verify it`), as uma is `error: forbidden`, as sue prints `verified`; `tl punch show P123-PUN-0001` contains `state  Verified`, `cleared  user:rob` and `verified  user:sue`.
2. Reopen, void: a second item is raised, cleared, and `tl punch reopen P123-PUN-0002 --reason "Wrong size"` as sue; `show` has `state  Open` and `reopened  1  Wrong size`; `tl punch reopen` without `--reason` exits 2; a third is voided with `tl punch void P123-PUN-0003 --reason Duplicate` and `tl punch clear P123-PUN-0003 --note x` prints `a void punch item accepts no further change`; `clear` with `--expected-version 1` on a newer item is refused.
3. From any record: three items raised `--from` the IWP number, the tag number and the document number show `raised from  <that key>`; `tl punch ls --from <key>` lists only its items; `tl punch raise --subject x --from NOPE-1` prints `error: no record NOPE-1` and `tl punch ls` count is unchanged; `tl link list <key>` shows the `raised_against` link (read `packages/tl-cli/src/tl_cli/link.py` lines 185-236 for its options).
4. Numbering: two background loops of ten `tl punch raise` each, started together; afterwards `tl punch ls --limit 500` shows every key from `-0001` to `-<n>` exactly once, `n` counted by the script itself (not read from the output).
5. Hidden source: as dora `tl corr receive --project P123 --subject "Legal letter"` (read `corr.py` lines 234-292 for the options; a `--body` suffices), `tl corr class set <NUMBER> --project P123 --to restricted --reason Legal` (`corr_registry.py` lines 383-420; confirm the group path with `tl corr class --help`), then `tl punch raise --subject "Letter follow-up" --from <NUMBER>` as dora; as uma `tl punch show <key>` prints exactly the text that `tl punch show P123-PUN-9999` prints (compare the two byte for byte), `tl punch ls` lacks the key and its `punch items: <n>` equals the count of data lines; the driver reads the API (404, same text) and MCP (`get_punch_item` error, same text, list lacks it) as uma and as an agent; sue and dora see it in `ls`.
6. One state over API, TUI, MCP (driver, as `p2_i3_demo.py` modes): `ApiClient.get_punch_item` equals the fields `tl punch show` prints for P123-PUN-0001; the TUI at 170x44 reached by the palette id `punch` (never `action_*`) shows the key and `Verified`; MCP `list_punch_items` and `get_punch_item` agree; an agent calls `propose_punch_item` (`from_key` the IWP number): the proposal is pending and no new `tl punch ls` row appears, then `uma` accepts it (the way `p2_i3_demo.py` accepts `propose_reservation`) and the next key (`-<n+1>`, counted as in clause 4) exists with `raised by  user:uma`; `mcp.clear_punch_item` and `mcp.verify_punch_item` are not in `MCP_ACTIONS`; a person without `quality.view` is refused by `tl punch ls`, by the API list route (403) and by the MCP list tool.
7. Generator: `just demo-project <fresh db> --sections core,engineering,awp,constraints,quality` (the recipe, not the module directly: it sets `TL_ENV=dev`; read `docs/runbooks/demo-project.md` section 1), stdout has a `quality:` line with records and events and no `skipped`; `tl punch ls --state S` is non-empty for each of Open, Cleared, Verified, Void; `tl punch ls --overdue` is non-empty; the demo password and accounts are those of the runbook. SQLite only for this clause (the generator is SQLite; say so in the header).

## Context (read these, nothing else)
- `docs/tickets/P2-PUNCH/README.md` (demo clauses), `dev/demos/P2-I3.sh`, `dev/demos/p2_i3_demo.py` (abridged: header and one mode of each kind), `dev/demos/P2-I2.sh` (helpers)
- `docs/reports/P2-PUNCH/{T02,T03,T04,T05,T06,T07}.md` (command lines, palette id, route names, tool names)
may explore: `dev/accept/P2-PUNCH/`, `packages/tl-modules/quality/tests/punch_world.py`

## Allowed paths
- `dev/demos/P2-PUNCH.sh` (create, executable), `dev/demos/p2_punch_demo.py` (create), `docs/reports/P2-PUNCH/T08.md` (create)

## Acceptance
```
just check
just demo P2-PUNCH
```
Expected: seven `PASS clause N` lines on SQLite and six on Postgres (clause 7 is SQLite only), no `DEMO FAILED`, exit 0, no leftover files or databases. Run the demo once; Postgres down means `ge` and stop (do not skip the backend). No pytest, no `just gate`. To prove the checks are real, the report names, for each clause, the one comparison that would fail if the feature broke (not a mutation run).

## Escalation triggers
- A clause cannot pass without a change in `packages/`, `schema/` or `dev/seed` (name the clause and the missing verb or text); a verb above differs from the merged CLI (the merged CLI wins: report the difference as the first line); a restricted correspondence item cannot be made with the verbs named; the demo needs more than the two files.

## Report requirements
`docs/reports/P2-PUNCH/T08.md` <= 60 lines: the PASS lines of each backend (<= 5 decisive lines each), one line per clause naming its surface (CLI, API, TUI palette, MCP, generator). Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-PUNCH-T08: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
