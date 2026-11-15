# P2-X2-T05 — Demo driver `dev/demos/P2-X2.sh`

Status: staged (dispatch after T02 and T04 are merged)
Tier: haiku
kind: ticket
review: full
Labels: demo
Depends on: T02, T04
Branch: `p2/x2-t05-demo`
Worktree: `/home/user/wt/x2/t05`

## Goal
`just demo P2-X2` runs the six demo clauses on SQLite and Postgres, one `PASS clause N: ...` line each, printed only after its check succeeded; exits non-zero with `DEMO FAILED` otherwise.
Copy the shape of `dev/demos/P2-X1.sh` and `dev/demos/p2_x1_demo.py` (ledger, people, agent token to a file, API on a free loopback port, `driver CLAUSE`, throw-away Postgres, trap cleanup).
The admin acts go through the `tl` CLI (clauses 2, 4, 5); the agent's filings and the five-reader read go through the small Python driver.

## Brief references (pasted)
> P2-X2 demo (`just demo P2-X2`, both adapters): 1. An agent without the module `user` word on the scope files: refused, the same as a scope that does not exist. 2. With the word it files; accept still needs the
> command's own word; a pilot agent that lacks the grant is refused until an admin runs `GrantModuleRole` (`tl admin roles grant`). 3. A project pending-queue cap (setting `ai.agents.max_pending_per_project`)
> is reached: the next filing is refused with a fixed text that shows no counts. 4. `tl agent stop`: new filings refused, pending ones show as held, accept refused. 5. `tl agent resume` lifts both; the ledger
> shows `Agent.Stopped` then `Agent.Resumed`, nothing rewritten. 6. Held count and stopped list, read as five kinds of reader, name no hidden record and count none (140, 141).

## Interfaces (verbatim shapes)
- CLI: `tl admin roles grant NAME --project P1 --module <m> --role user --reason TEXT`; `tl config set ai.agents.max_pending_per_project 2 --project P1 --reason TEXT`
  (`--project`, `--company`, `--reason`, `--accept-risk` are its options; the key is `risk: advanced`, so `--reason` is required);
  `tl agent stop NAME [--reason TEXT]` prints `stopped agent:NAME`; `tl agent resume NAME` prints `resumed agent:NAME`; `tl agent stopped [--json]` prints `agent:NAME  since ...  by ...  held N  reason`.
- Refusal texts: the fixed cap text `this review queue is full; ask a reviewer to clear it, then file again`; the stop text and the filing refusal are the services' own: the driver compares, it does not hard-code them
  (clause 1 compares the no-word refusal with the missing-scope refusal; clause 4 reads the stop text from the refused filing and checks it names no count).
- Ledger reads in the driver: `SELECT type FROM events WHERE type IN ('Agent.Stopped','Agent.Resumed') ORDER BY seq` (use the adapter-neutral helpers the X1 driver uses; read its `title_rows`).

## Steps
1. `dev/demos/P2-X2.sh`: header comment listing the six clauses as `P2-X1.sh` does (<= 170 lines). Reuse its `quiet`, `tl`, `step`, `fail`, `clause`, `driver`, `as`, `run_backend` helpers by copy.
   People: `demo` admin, `amy` (plain user), agent `triage`; token to a file, never printed.
2. `dev/demos/p2_x2_demo.py` (<= 250 lines; subcommands `clause1` ... `clause6`, `main(argv)`): in-process MCP server for the agent (as `mcp_server` in `p2_x1_demo.py`), proposals filed through the MCP
   tool; five readers for clause 6 built as in T01's walk (`viewer_for_actor`), one privileged record carried by one pending proposal. Each clause prints `ok ...` lines and exits 1 with `miss ...` on failure.
3. The shell sequence per backend: init; people; token; serve; clause 1 (driver; the agent has no grant); clause 2 (`tl admin roles grant triage ...` then driver: files; the accept by a person without the word still refused);
   clause 3 (`tl config set` to 2, driver files until refused, compares the text with the fixed text and asserts no digit); clause 4 (`tl agent stop triage`, driver: new filing refused, `tl agent stopped` shows `held N`
   with N equal to the pending count, accept refused); clause 5 (`tl agent resume triage`, driver: files again, accept works, ledger types in order `Agent.Stopped`, `Agent.Resumed`, no event rewritten:
   the hash chain verifies with the existing verify call the X1 driver or `tl` offers; if none exists in the X1 driver, count events before and after and assert only appends); clause 6 (driver, five readers).
4. Do not edit the `justfile` (`just demo <id>` already runs `dev/demos/<id>.sh`). Consequential pin: if a test lists the demo scripts, update it and list it in the report.

## Context (read these, nothing else)
- `dev/demos/P2-X1.sh`, `dev/demos/p2_x1_demo.py` (lines 1-135, 167-190, 413-421)
- `packages/tl-cli/src/tl_cli/agent_stop.py` (the three commands) and `docs/tickets/P2-X2/README.md` (demo)
- `packages/tl-api/tests/test_api_agent_stop.py` (the five-reader seed)
may explore: `dev/demos/p1_i0_demo.py` (`pg-create`, `pg-drop`)

## Allowed paths
- `dev/demos/P2-X2.sh` (create, executable), `dev/demos/p2_x2_demo.py` (create)
- `docs/reports/P2-X2/T05.md` (create)

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
TL_DEMO_BACKENDS=sqlite just demo P2-X2
TL_DEMO_BACKENDS=postgres just demo P2-X2
```
Expected: six `PASS clause N:` lines per backend and `P2-X2 demo OK on: <backend>`; nothing left behind (no temp ledger, no server process, no Postgres database).

## Report requirements
Standard report plus: the demo output (<= 12 lines per backend: the six PASS lines and the last line); for each clause the one check that would fail if its guard were removed.

## Escalation triggers
Stop and write *Blocked* if a clause needs a source change; if a CLI command named above differs; if Postgres is unreachable (a failure, not a skip: report it); if the run leaves a process or database behind.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
