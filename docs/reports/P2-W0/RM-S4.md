# Report — P2-W0-RM-S4 (module roles: the same access function before every module handler call in the CLI and the embedded TUI)

Branch: `p2/w0-rm-s4`   Commit(s): see `git log p2/w0..p2/w0-rm-s4` (code, acceptance pin, then this report)

## Deviations
1. **No pytest, no `just gate`, no mutants run by the suite** (owner policy of the spec). Pins updated by reading; two risky ones are named below.
2. **Finder also takes two non-`handle_*` entry points** (`EXTRA_HANDLERS`: `sweep_clocks`, `ingest_email`): the CLI calls them with a command as 2nd argument and they are the handlers of `SweepClocks` / `IngestEmail`. `ingest_email`'s command is declared by no module (no-op gate, as before). The bulk helpers `apply_plan` (`doc_import.py`, `tag_import.py`) and `load_standards` (`standards.py`) take no command, so the handler rule skips them; they get a pre-flight (7 below, orchestrator decision F1).
3. **Gate sits on the handler's own unit of work** (`require_command(uow, command)`), so the `db`-taking twin was not needed and not written.
4. **Kept `require_controller(db)` (8 sites)**, because no module handler runs there: reads (`comm.py` 113, 140, 492 `ls/show/export`, `corr_registry.py:494` clearance ls) or a gate that depends on an option (`doc_import.py:73` `--apply`, `corr_report.py:76` export class, `derive_publish.py:56` publisher role, `corr.py:582` void of a received item). The handler under them is also gated (AND).
5. **Kept `require_admin(db)` and `self._admin_gate(uow)`** before admin-word module handlers (`derive_publish`, `schema_*`, `cost`, `standards*`, `tag record`; embedded `publish_derived_tags`, `compensate_publication`): the module gate follows (AND, D14). Only `require_controller` / `_controller_gate` were replaced.
6. Embedded `_command_gate` resolves the holder for `self.actor` (not `cmd.actor`), as the spec says; `_own_command` still checks the command's actor.

7. **Pre-flight for the bulk helpers (F1).** `session.require_commands(uow, classes, *, actor, scope)` calls `require_command` on a `model_construct` probe of each class (the access function reads class name, actor, scope only). Tuples, read from the helpers in `tl_mod_*`: `doc_import._APPLY_PLAN_COMMANDS = (RegisterDocument,)`; `tag_import._APPLY_PLAN_COMMANDS = (RecordTag, ReclassifyTag, UpdateRecord, SetPsetValues)` (the last two are core, no module word, kept so a later declaration is covered); `standards._LOAD_STANDARDS_COMMANDS = (RegisterCodeList, AddCodeValue, RegisterMnemonic, RegisterNumberingPattern, DefineTagClass)`, scope `company`. Placed before the helper call, after the old `require_admin`/`require_controller` (AND, D14). No `tl_mod_*` edit. `gate_sweep.py` owns the rule (`find_helper_calls`, `--check` lists an ungated helper call; the sweep does not place it).

## Counts
Handler calls 125 (CLI 109 in 24 files, embedded 16), gated 125, MANUAL 0 (sweep placed all; the 3 table commands `spec.handler` in embedded included). `require_controller(db)` calls 40 -> 8 (32 replaced, one in `corr_clock.py`). The codemod hoists an inline command to `command` / `command_N` before the statement; no site needed hand placement. By hand: removal of `_controller_gate` in four embedded `with` blocks and of the three `spec.access` blocks (`correspondence_command`, `_module_command`, `schemareg_command`); `_command_gate`; holder wiring.

## Changed files
- `dev/tools/gate_sweep.py` (new codemod, `--check`, helper rule), `dev/accept/P2-W0/RM-S4.py` (new acceptance)
- `packages/tl-cli/src/tl_cli/session.py` — `require_command(uow, command)`; 24 command modules — gate calls and imports; `proposal.py` — holder at accept
- `packages/tl-tui/src/tl_tui/embedded.py` — `_command_gate`, 16 gates, holder in `allowed_actions`; no raw `.access` left (the 4 reads are gone)
- `session.py` also `require_commands`; `doc_import.py`, `tag_import.py`, `standards.py` — tuple and pre-flight
- pins: `tl-cli/tests/test_cli_controller_gates.py`; `tl-tui/tests/test_embedded_{actions,derivation,controller_gate}.py` (match text only)

## Pins updated (by reading)
- `test_cli_controller_gates.py`: count test now pins `require_command(` per file (24 files) and the 8 kept `require_controller(db)`; refusal text is the module word (`ROLE_GATE` kept for `doc import --apply`); `made` now opens review cycle `P123-RC-1` and drafts `P123-TRN-0001` because the gate runs after the lookup; the no-session test now expects `error: forbidden` (dev actor holds `user` only). **Unrun, risky:** the key `P123-RC-1` and `--number P123-TRN-0001` are assumed.
- `test_cli_session.py`: unchanged (functions stay). TUI tests that match the old text: three files above. Fakes keep the old text.
- Refusal text only (F2, F3; module word `access word for <module>` where the module gate fires, the old text kept where `require_controller` still fires first): `test_cli_corr.py` (`GATE`, new `ROLE_GATE`/`ROLE_GATED` = `clearance ls`, `report register`), `test_cli_domains.py` (`GATE`, `ROLE_GATE` for `comm ls/show/export`), `xercli_support.py` (`GATE`, used by `test_cli_xer.py`). F3 grep of the changed substrings over `tl-cli/tests` and `tl-tui/tests`: no further hit (admin-role texts unchanged; TUI fakes keep the old text).
- **Unrun, risky:** `test_cli_corr.py::SITES` (and `test_cli_domains.py` `comm` loop) call made-up ids (`P123-COR-0001`, `P123-EW-0001`, party `ACME`, clause `CT-1`); sites that look the record up before the gate (`issue`, `supersede`, `party contact-*`/`retire`, `clause retire`, `class set`, `comm update/submit/...`) now answer `no item`/`no party` before `forbidden`. Not fixed (text-only brief); TA or the orchestrator should seed those records.
- Intended change: an account-less actor on a Postgres ledger is now refused on gated `user` commands (the dev fallback is SQLite dev/test/ci only, D2). Tests relying on it need a session there.

## Proposal and action callers
Holder passed: `tl_cli/proposal.py:228,238` (`holder_for_actor`), `embedded.py:477-483` (`allowed_actions`). Embedded has no proposal accept (grep). Need none: API `routes/proposals.py:143-152`, `routes/actions.py:46-52` (already `holder_for_principal`); MCP and sim go through the API (`tl_sim/client.py:357`; `grep` finds no MCP or sim call of `accept_or_fail`/`allowed_actions`).

## Commands and output
```
$ just check
All checks passed! | 0 errors, 0 warnings | generated files are up to date (641) | licences ok
$ uv run python dev/tools/gate_sweep.py --check
0 ungated module handler call(s)
$ uv run python dev/accept/P2-W0/RM-S4.py      # exit 0, 9 PASS
total: 125 handler calls, 125 gated, 0 MANUAL-placed
PASS AST pin ... | PASS CLI x4 | PASS embedded | PASS proposal accept | PASS allowed_actions | PASS embedded.py reads no raw .access
```
Bulk pre-flight (attempt 2): `gate_sweep.py --check` prints `0 ungated module handler or bulk helper call(s)`; acceptance adds 2 PASS lines (pin over the 3 helper calls with the tuple equal to the Command classes the helper modules build; `require_commands` refuses a plain user `RecordTag`, passes `ReclassifyTag`) and the 3 in-memory removals are reported. Real mutant: deleting the `standards.py` pre-flight fails the script and `--check`.
Mutants (on the acceptance script, committed tree restored each time): sentinel `require_command` body no-op killed; `_command_gate` no-op killed; `holder=holder` at `proposal.py` removed killed (needs the P2 viewer grant added for that); `holder=` in `allowed_actions` removed killed (P2 documents viewer grant added); one removed `require_command` (`xer define`) killed by the AST pin. 5/5.

## Guard sites for TA
`session.py` `require_command` body; one removed `require_command` per module (documents `doc.py void`, correspondence `corr_clock.py sweep`, schedule `xer.py define`, engineering `tag.py create`, schemareg `schema_pkg.py draft`, cost `cost.py import`); `embedded.py` `_command_gate`; `proposal.py` holder. Tests to write: `test_cli_module_words.py`, `test_embedded_module_words.py` (finder: `gate_sweep.find_calls`).

## Learnings (proposed)
- A gate that needs the built command runs after the record lookup; a test that refuses a user on a made-up record id must now create it.

## Notes for TA
- The helper pin (like the handler pin) accepts a gate in a sibling branch or loop of the same function: "earlier" is source position, not dominance. TA should place a mutant that moves a gate into a non-executing branch if that matters.

## Open questions / Blocked
1. `test_cli_corr.py::SITES` and the `comm` loop in `test_cli_domains.py` need seeded records (see Pins updated). Who seeds them?
