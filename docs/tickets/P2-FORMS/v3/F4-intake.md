# V3-F4 · Intake, signed-in only: codes, queue, accept/reject/purge, terminal log (demo clause 10)
kind: piece · review: full + security · branch `p2/v3-f4-intake` · worktree `/home/user/wt/v3p/f4` · base
`p2/v3-forms` (after F2 merges; F3 may still be open). Process: `docs/build-spec/process-v3.md` section 2.
References (excerpts, read as needed): `I01-intake-code-cli.md`, `I03-intake-queue-views.md` (views merged as
`tl_mod_forms/intake_views.py`), README rows I03r, I04, I05; commands from S7c are on the base.

## Goal
A controller issues and revokes intake codes, sees the intake queue, opens an item, accepts it (as the record the item
proposes, through S7c's commands), rejects it, purges what is due, from the CLI, the signed-in API and the terminal app.
The public route `/i/<code>` stays out (S6, owner gate Q9): items for the demo are staged through the existing S7c test
path or a dev-only helper, never a new public route.

## Build
1. `tl intake code issue|revoke|ls` (I01: the CLI makes the code with `new_code`, sends only the hash, prints the code
   once; never stored or logged in clear) and `tl intake ls|show|accept|reject|purge` (I04), in forms' `cli_groups`.
2. Signed-in routes under `/forms/intake/` over `intake_views` (I03r) on forms' `read_routers`; client methods: fill
   F1a's `NotImplementedError` stubs on `tl_tui/client.py`, `embedded.py` and the API client (signatures unchanged).
3. Terminal "Intake" log beside the proposal queue (I05; `tui-layout`), through those client methods.
4. Walk: five readers plus an agent on every new route, CLI read and TUI read: hidden == missing byte comparison; **no
   code hash, salt, raw code or intake body in any read, error, log line, report or webhook** (grep the outputs in the
   test); agents refused like the other forms reads.
5. Demo clause 10: issue a code (printed once), stage one item, accept it into the record it proposes and read that
   record back; reject a second; purge; `tl intake code ls` shows no secret. `PASS clause 10` after the read-backs.

## Rules
No edit of `confidentiality.py`, no schema change, no new event, no public route, no change to S7c handler logic.
Agents get no intake tool. Owner gate S6 untouched.

## Gate
`uv sync --frozen --all-packages` after creating the worktree. `just gate-changed` (if it stops at the deferred
`test_check_wheels` pin, run its later steps by hand and say so); `TL_DEMO_BACKENDS=sqlite just demo P2-FORMS`.
Report `docs/reports/P2-FORMS/V3-F4.md`, at most 15 lines. Prefix `V3-F4:`.
