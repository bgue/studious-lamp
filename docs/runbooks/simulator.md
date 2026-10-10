# Runbook — run, reset and check a simulated project

Purpose: play a seeded simulated team against the dev API, see what it did, and recover when a run stops. Brief: §29.5.

## When to use
- You want a live, moving project in the dev ledger (`just seed`, a demo, load or TUI testing).
- `tl sim assert` fails, or `tl sim advance` says a step did not finish.

## Before you start
- Access needed: a ledger (`uv run tl init`), the API running (`just serve`, or `uv run tl serve`) and write access to the token file (`TL_TOKENS`, default `./dev/data/tokens.json`).
- Safe to run during business hours: yes, on a dev ledger only. A simulation writes into its own scope `project:sim-<run>` and never into a real project; the API refuses the simulated-time header for any other scope.

## Steps
1. Start a project. The run id is printed (`r` and six hex digits derived from the scenario name and seed, so the same scenario gives the same id).
   ```
   uv run tl sim create north-unit-small
   uv run tl sim advance --days 5
   ```
   Expected: `played <date>` per working day, then `ground truth +<n> (<total> lines)`.
2. Seed a ready-made project instead (starts a temporary API if none answers):
   ```
   just seed xs        # 3 working days; s is 10, m is 30
   ```
3. Add the agent: a scenario with `actors: {assistant: {proposals_per_day: 1}, approver: {accept_rate: 0.7}}` has `agent:sim-assistant` propose valve-to-document links over MCP (it needs `TL_DB`, or `tl --db`, because the MCP server opens the ledger file) and `user:sim-approver` work the queue. Leave the approver out and a person decides: `uv run tl proposal ls --project sim-<run>`, then `uv run tl proposal accept <id> --actor user:sim-approver`.
4. Inject an event for the next day: `uv run tl sim inject material_late --arg item="6in flange" --arg days=21`.
5. Check the suite against what the team intended:
   ```
   uv run tl sim status
   uv run tl sim assert
   ```
   Expected: `ok: <n> checks`. On `FAILED` each line names the intent, the key and the field that differs.
6. Look at it: `uv run tl feed ls --project sim-<run>` and the TUI on the same ledger.

## Verify
- `tl sim status` shows the same `digest` for a second run of the same scenario on an empty ledger (the ground truth is byte-identical).
- `tl sim assert` is green after every `advance`.

## Roll back
- A run cannot be undone: events are immutable. Start another with `--run-id`, or delete the ledger (`./dev/data/tl.db`) and `./dev/data/sim/<run>` together. Deleting only the run directory leaves records in the ledger that no log names.
- "step ... did not finish": a step died after some of its writes, so the log may miss events the suite has. The run refuses to go on. Create a new run with `--run-id`.
- `error: run '<id>' already exists`: pick another `--run-id`, or remove `./dev/data/sim/<id>` when you also reset the ledger.
- `cannot reach the server`: start the API (`just serve`) or set `TL_API_URL`.
- 401 after a restart of the token file: `run.json` holds the actor tokens (mode 0600). If the token file was replaced, create a new run.
- `sim_assert` fails with `unexpected_record`, `event_source` or `event_actor`: someone other than the simulator wrote in `project:sim-<run>`; that is the check working.

## Related
- `packages/tl-sim/README.md`, `docs/tickets/P0-I6/README-C.md` (decisions C1 to C9), ADR-0005 (dev identities), `docs/runbooks/api-and-mcp-dev.md`.
