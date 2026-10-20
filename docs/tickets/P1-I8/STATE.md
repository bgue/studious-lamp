# P1-I8 supervisor state (hand-over)  base=see Base  ck=1 (pieces)  gate=pass (shards named below)

Read first: `AGENTS.md`, `docs/memory/LEARNINGS.md` (L-P1-I8-1 to 12), `FANOUT.md`, `README.md` (the board) in this folder.
Worktree `/home/user/wt/p1-i8`, branch `p1/i8`. Protocol: ADR-0004 relay (one `=== RELAY ===` block per turn, then `SubagentHandback`).

## Base and gates
- Base: the merge of trunk fdb2eff (P1-I6) into p1/i8, commit 10a8414 (see `git log -1`); batch 3 (T05a2 c09a578, T07b c45de16) merged at 0609333 and 62a7142.
- After the trunk merge: `ruff check`, `ruff format --check`, `pyright`, `generate --check`, `openapi --check` and `check_licences` are clean (run the pieces, `just check` itself takes minutes).
- Shards after the merge, all passed: tl-schema + contract + services + webhooks + schema + ci 1225; api (commands, proposals, auth review, error table, effective time, schemareg, both walking tests) 517 after the legacy error rows were added (a55 fix: `tl_api/errors.py` `_legacy_rows`); cli (gov, load, lake, schema package) + legacy + document silver 93 (sqlite); tl-tui was still running when this was written.
- Not yet run: the whole `tl-cli` suite (about 2 hours), the demo, the parity run of the whole tree.

## Board (README.md has the same table)
| Piece | Status |
|---|---|
| S1 classify, S2 schemareg, S4 lake silver, S5 plumbing, S6 legacy framework | done and committed; fixes F1 to F8 below |
| T03 impact, T08 lake marts | merged (07c7bb7, 3fb9c0a) |
| T05a1, T07a | merged (38049fa, 31e272f) |
| T05a2, T07b | merged (0609333, 62a7142) |
| T05a3 waivers CLI | reference written and green (10 cases); stub, wiring, ticket, mutation sentinel still to do |
| T05b conformance dashboard | not started |
| T05a4 crosswalk, export-git, import-git | not started |
| T04a, T04b workbench TUI | not started |
| T09 demo `just demo P1-I8` | not started |
| T10 | the orchestrator's |

## Decisions (FANOUT D1 to D12, one line each)
D1 packages are the constrained `PackageDoc` YAML, classified by `classify_packages` and `classify_linkml`. D2 roles: draft/revise/analyse/submit/ask-waiver any signed-in person; send back, approve, publish, deprecate, retire, adopt, approve/revoke waiver admin. D3 ledger packages join the directory ones; unpinned project uses the highest directory version. D4 submit refuses breaking/forbidden; publish needs the approved classification; adopting a non-additive version needs the impact digest; retire refused while pinned. D5 waivers reach the evaluator through the effective schema; at most 366 days. D6 a load run is a record `legacy.LoadRun`; files in four slots. D7 loaders reuse the tag and document imports; create-only; compensation by recorded ids. D8 bronze is a copy in the lake. D9 every `tl load` command is the administrator's; a run has a class (F1). D10 silver and marts are built from what the lowest reader may read. D11 security review list. D12 not built: `tl schema promote`, MCP schema tools (follow-ups for the report).
Other decisions: the reconciliation report is a file of the run, not a document; an equipment list loader replaces the line list (no line class in the standards); the diff of an analysed version with no text is a first version; the base keeps its full width in `classify`; an empty snapshot is never the snapshot before in the history mart; a dotted pset name is matched by its longest name; `--include-confidential` is required for every bronze copy of an internal run.

## Security review at 9928c45 (changes requested) and fixes
| Finding | Fix commit | Open |
|---|---|---|
| F1 HIGH run files and ids readable by all | 66b4fbf, 18ef13c (LoadRun is a ConfidentialSource; class stored on open; walking tests API and MCP) | coordinator re-check |
| F2 HIGH YAML alias bomb in a package | a555198 (`tl_schema/plain_yaml.py`, single-value defaults, no values in messages, trial compile outside the provider lock) | the trial still runs inside the write transaction of the handler (bounded by the node cap); not moved out |
| F3 MEDIUM forged effective time | a555198 (`common.scoped/check_clock/today_in`, `EffectiveTimeError`, `tl_core.util.SIM_SCOPE`) | core-engine sign-off for `tl_api/effective.py`, `tl_core/util.py` |
| F4 MEDIUM bronze ignores class | 66b4fbf | none |
| F5 MEDIUM package waivers skip the rules | 66b4fbf (expiry at submit; `waiver_added` needs review and is not auto-adoptable) | none |
| F6 MEDIUM impact names to every reader | 66b4fbf (`redact_names`; stored report has counts; admins see names via API, CLI, TUI client) | none |
| F7 accepted, F9 note for any future export | none | F9: names in an export |
| F8 report document | 66b4fbf (FANOUT D9 corrected) | none |
Core-engine pieces waiting for the orchestrator's sign-off: the readable-set rule (`tl_lake/sync.py`, 3d007e5), reserved `legacy:` and `load:` prefixes (`tl_core/services/reserved.py`, c65c7ab), the F3 files above, `Provider.trial` outside the lock (`tl_core/schema_provider.py`).

## Next actions, in order
1. Wait for the story of the shards in the relay; fix anything red.
2. T05a3: copy `refs/t05a3/*` into place (`schema_waiver.py` as stub with STEPS, `wiring.patch.txt` applies to `schema.py`, test as provided file `provided/t05a3-...`), run the test on the reference then the stub, one sentinel mutant, write the ticket with `refs/tools/mkticket.py.txt` (specs import `COMMON_LEARNINGS` from `t05a1_spec.py.txt`; paths inside them point at the old scratchpad: fix them). Commit as S7c.
3. T05b dashboard (report function `tl_mod_schemareg/dashboard.py` counting `cur_core_record.conformance` by type and stale `effective_schema_hash`, active waivers with days left, drift; CLI `tl schema conformance --project P [--json]`; read as the current viewer). Reference, stub, provided tests, ticket.
4. T05a4 (`tl schema crosswalk`, `export-git DIR`, `import-git DIR`), then T04a and T04b (one `SchemaWorkbenchScreen` in `tl_tui/widgets/schema_screen.py`, pure text in `schema_text.py`, pilot assertions not snapshots; keymap: P1-I6 took Ctrl+G; the client methods and fakes exist from S5), then T09 (`dev/demos/P1-I8.sh`, `just demo P1-I8`).
5. Dispatch in pairs with disjoint Allowed paths; merge on pass; remove worktrees.
6. Gates: full `tl-cli` suite, parity (`--adapters sqlite,postgres`) of touched directories, `just demo P1-I8` on both adapters, READMEs and AGENTS of touched packages, runbooks, learnings, board, `docs/reports/P1-I8.md` with Showcase (commands from the demo) and follow-ups (promote, MCP schema tools, report document, line list class, dashboard limits, roles, F2 trial in transaction, F9).
7. DONE relay with SECURITY_REVIEW of everything after 9928c45.

## Staged references and tools
- `docs/tickets/P1-I8/refs/t05a3/` (waiver CLI reference, its test, the wiring patch) and `refs/tools/` (`mut.py.txt` mutation driver: `python mut.py FILE SPEC.json 'test command'`, SPEC is a list of `[old, new]`; `mkticket.py.txt`; the T05a1 and T05a2 spec files).
- `docs/tickets/P1-I8/provided/` holds the provided tests of the merged tickets.
- Reference of each merged ticket is its merged code.

## Environment traps
- One heavy pytest at a time, `--basetemp=/tmp/pt-p1i8-<name>`, remove only that directory; never touch `/tmp/pytest-of-root`. One pytest session over several large packages was OOM-killed: run per package. `tl-api` alone is 13 minutes, `tl-modules` 24, `tl-tui` 8.
- A command with `bash -c '... rm -rf ...'` is refused by the safety check: write a script file and run it with `nohup`. Foreground `sleep` is blocked: wait with `timeout N bash -c 'until [ -f done ]; do sleep 5; done'`.
- A shell `pkill -f pytest` by another agent can kill your run (exit 144/137): rerun.
- After editing a `pyproject.toml` entry point run `uv sync --all-packages` or the installed loaders do not change.
- The MCP test `test_apply_is_refused_when_the_generated_directory_leaves_the_repository` errors at teardown when the tree has uncommitted files.
- Registering a restricted document and reading a restricted run needs a viewer of level 1 (`cf.use_viewer(...)`); tests default to the lowest.
- P123 has a project package that pins a company version; use P999 for pin tests.
- Never edit, checkout or commit in `/home/user/studious-lamp`.
