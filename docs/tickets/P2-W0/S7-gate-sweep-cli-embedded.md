# P2-W0-RM-S4 — Module roles: the same access function before every module handler call in the CLI and the embedded TUI

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: auth, security, cli, tui
Depends on: RM-S2 (merged: `require_command_access`, D1 to D4, opt-in `holder`)
Branch: `p2/w0-rm-s4`
Approver (permission path): the orchestrator under P2-Q10 (line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece no `tl_mod_*` handler runs from `tl_cli` or `tl_tui/embedded.py` without `require_command_access` (RM-S2, the
**only** access function) being called for that exact command first. The sweep is a committed codemod
(`dev/tools/gate_sweep.py`, stdlib `ast` only, idempotent, run once, kept), not hand edits, plus an AST pin in the acceptance
script that fails if a later change adds an ungated call.

## Brief references
Interface: `docs/build-spec/specs/roles-mvp.md` **§5 rows "CLI", "Embedded TUI", "accept_proposal", "allowed_actions" and §11
R1/R2**, with these RM-S2 results (report `docs/reports/P2-W0/RM-S2.md`, authoritative over §5):
1. **Dev rule lives in core (D2).** `holder_for_actor(conn, actor)` already gives an account-less `user:` actor on a dev ledger
   the `user` role in every module. The CLI and the embedded TUI **pass no dev logic of their own**; they call the core
   function and a `controller` command with no session or no grant is refused, as before.
2. **CLI gate.** In `tl_cli/session.py` add `require_command(uow, command)` (and, only if a site is not inside an open unit
   of work, a `db`-taking twin that opens a read-only one): calls `require_command_access(uow.conn(), command)`, and turns
   `ForbiddenError` into `fail("forbidden: ...")` (exit 1, same style as `require_controller`). Keep `require_controller` and
   `require_admin` defined (admin-only account commands and `test_cli_session.py` still use them). Every site that calls
   `require_controller(db)` before a module handler is replaced by `require_command` placed **after the command object is built
   and before the handler call**; the 57 `require_controller` sites and the ~141 handler calls in 44 files are the scope.
3. **Embedded gate.** Replace `_controller_gate(uow)` on module-command paths (`document_command`, `engineering_command`,
   `correspondence_command`, `_module_command`, `schemareg_command`, and every other `embedded.py` call to a `tl_mod_*` handler,
   about 35) by `_command_gate(uow, cmd)` = `require_command_access(uow.conn(), cmd)` for `self.actor`. This removes the raw
   `spec.access` reads at `embedded.py:1146,1168,1170,1510` (RM-S2 report: a fine word there was not normalised); where a read of
   `.access` remains, use `tl_api.commands.effective_access(spec)`. `_admin_gate` stays for the account administration calls.
4. **Holder wiring (RM-S2 deviation 3).** `accept_proposal`/`accept_or_fail` and `allowed_actions` take an opt-in `holder`. Pass
   `holder_for_actor(conn, actor)` at the in-process callers: `tl_cli/proposal.py` (accept, ~line 230) and `embedded.py`
   (`allowed_actions`, line 476; the embedded client has no proposal accept, confirm by grep). Grep `accept_or_fail|accept_proposal|allowed_actions` under
   `packages/`: the sim and MCP reach these through the API (which already passes the principal's holder) and need no change;
   confirm that by reading and say so in the report (file:line). The account-role check still runs first (AND, orchestrator
   decision D14: account role *and* module word).
5. **What does not change:** reads, ADR-0016, `svc:` actors, workflow `roles` guards, the runner.

## The codemod `dev/tools/gate_sweep.py`
`uv run python dev/tools/gate_sweep.py` rewrites the sites; `--check` exits 0 when nothing is left to change and 1 listing
`file:line` of each ungated call (it is the CI form and the AST pin of the acceptance script reuses its finder). Rules:
- A *module handler call* is a call to a name imported from a `tl_mod_*` module whose name starts with `handle_` or that is a
  `CommandSpec.handler` reference, with a `Command` instance as its second argument; the finder reports `(file, function, line,
  variable)`.
- Placement: immediately before the statement that holds the call (or before the enclosing `with` when the command variable
  is built outside it), reusing the variable. Replace a preceding `require_controller(db)` for the same function instead of
  adding a second gate. Fix imports.
- Idempotent (second run: no diff). A site it cannot place prints `MANUAL file:line reason`, exits 2 and leaves the file
  alone; you place those by hand and list them in the report (expected: under 15).

## Consequential pins (rule 12; update by reading, no pytest, list them)
- `packages/tl-cli/tests/test_cli_controller_gates.py` (counts `require_controller(db)` per file, ~lines 130-165): rewrite to
  count `require_command` at the same sites; keep the file's intent (every controlling CLI path is gated).
- `packages/tl-cli/tests/test_cli_session.py` (`require_controller` itself): unchanged, because the function stays.
- Any other test that enumerates gate calls or relies on a CLI `user` command running with no account on a non-dev ledger:
  update to the new rule and list it. A test that fails for another reason stops the piece (*Blocked*, test id).

## Context (<= 10 files)
- `docs/build-spec/specs/roles-mvp.md` §5, §11; `docs/reports/P2-W0/RM-S2.md` (seam list, D1 to D4)
- `packages/tl-core/src/tl_core/auth/module_roles.py` (`require_command_access`, `holder_for_actor`)
- `packages/tl-cli/src/tl_cli/session.py`, `tl_cli/doc_rendition.py`, `tl_cli/proposal.py`; `packages/tl-tui/src/tl_tui/embedded.py`
may explore: `tl_cli/corr_registry.py`, `tl_cli/comm.py` (most sites), `dev/tools/scan_secrets.py` (house style for a tool)

## Allowed paths
- `dev/tools/gate_sweep.py` (create); `dev/accept/P2-W0/RM-S4.py` (create); `docs/reports/P2-W0/RM-S4.md` (create)
- `packages/tl-cli/src/tl_cli/**` (the gate calls, their imports, and `session.py`; no other change); `packages/tl-cli/tests/test_cli_controller_gates.py` (pin)
- `packages/tl-tui/src/tl_tui/embedded.py` (gate calls, the four `.access` reads, holder wiring, nothing else); `packages/tl-tui/tests/` only the pins found
Not allowed: `tl_core/**`, `tl_api/**`, `tl_mcp/**`, `tl_sim/**`, `schema/**`, any other TUI file, `tl_cli/admin_roles.py` and `tl_cli/main.py`
(RM-S3 creates them in parallel; the codemod must skip a file that has no `tl_mod_*` handler call, so it never touches them).

## Acceptance (run these, once; no pytest, no `just gate`)
```
just check
uv run python dev/tools/gate_sweep.py --check
uv run python dev/accept/P2-W0/RM-S4.py
```
`dev/accept/P2-W0/RM-S4.py` (SQLite temp ledger, exit 0, one `PASS <check>` per check): (1) the AST pin: every `tl_mod_*`
handler call in `tl_cli/**` and in `embedded.py` has a `require_command*`/`_command_gate` call on the same variable earlier in
its function; counts printed per file and in total (handler calls, gated, MANUAL-placed); a deliberately ungated copy of one
function, built in memory, is reported (the pin can fail); (2) through `CliRunner`, per module (documents, correspondence,
schedule, engineering, schemareg, cost where it has a CLI write): a plain `user` account is refused one `controller` command and
runs one `user` command, a `document_controller` account is allowed its derived controller commands in documents,
correspondence and schedule, a `superuser` grant on P1 allows P1 and still refuses P2; `user:dev` with no session on the
dev file runs a `user` command and is refused a `controller` one; (3) the same matrix through `EmbeddedClient` for one command
of each module; (4) proposal accept through `tl proposal accept`: accepter without the module word is refused (proposal stays pending),
with it passes; `allowed_actions` through `EmbeddedClient` offers a controller only what the API would;
(5) `grep` proof that `.access` is no longer read raw in `embedded.py`.

## Tests for the end run (TA writes them; this piece writes none)
`packages/tl-cli/tests/test_cli_module_words.py` (calls the finder of `gate_sweep.py`: zero ungated calls),
`packages/tl-tui/tests/test_embedded_module_words.py` (same rule on `embedded.py`), an updated `test_cli_controller_gates.py`.
Report the guard sites so TA can place mutants: `require_command` body, one removed `require_command` per module, `_command_gate`,
the holder passed at `proposal.py`.

## Report requirements
Standard piece report (<= 60 lines): deviations first; counts (handlers, gated, replaced `require_controller`, MANUAL sites with
file:line); pins updated; which callers of the proposal and action functions got a holder and which need none (file:line);
acceptance output (<= 5 lines per command).

## Escalation triggers
- *Blocked* if: a handler cannot be gated without changing a command's actor or scope; a `user` command regresses on a non-dev
  ledger for a reason other than the missing account; more than 15 MANUAL sites; a gate needs an edit in `tl_core` or `tl_api`.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
