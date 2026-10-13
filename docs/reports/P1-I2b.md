# Report — P1-I2b (Document controller role)

Branch `p1/i2b`. Plan: `docs/tickets/P1-I2b/README.md`. Decision: `docs/adr/0013-document-controller-role.md`. Runbooks: `docs/runbooks/accounts-and-access.md`, `docs/runbooks/documents.md`.

## Outcome
Objective met: yes. Phase 1 has a third role, `document_controller`. An admin grants it (`tl admin user roles NAME --add document_controller`, the accounts screen key `c`, or `PUT /admin/accounts/{id}/roles`); a person who holds it issues, supersedes and voids, registers signed copies, issues transmittals, records and overrides review answers and applies a DMS import without being an admin. The admin keeps every right. The controller has no `admin.*` action, cannot recover links or touch the engineering registry, and cannot change a role (her own included). An agent account can never hold the role and stays propose-only.

Demo path verified: `just demo P1-I2b` passes its seven clauses on SQLite and on Postgres, and `just demo P1-I2` still passes. Not verified on a fresh clone; the demos and gates ran on the `p1/i2b` worktree.

No implementer ticket was relayed: the pieces share one rule (who may call what) and are a few dozen lines plus tests each, all in auth code that stays supervisor-tier.

## Tickets
None (see the plan). Supervisor commits `P1-I2b-S1` to `S12`; the plan lists them.

## Gates
| Gate | Result |
|---|---|
| `just check` | clean on the final tree (ruff, format, pyright 0 errors, codegen drift, OpenAPI drift, licences). The S9 tests had three over-long lines that the first check after S9 found; fixed in S10 |
| `just test` | **Final head e0dfc63 (after the review fixes of S11): 7253 passed, 1 skipped, 16 deselected, 0 failed (42 min).** Earlier, on the tree of S8: 7232 passed, 3 failed: three tests of the documents module matched the old refusal wording ("registered by an admin", "only an admin can close it"). Fixed in S9 (test strings only); the whole `packages/tl-modules` suite (653) passes after the fix, and the three files again after the line-length fix of S10. The three were found only by the full run (L-P1-I2b-2) |
| `just test-tui` | 798 passed, 34 snapshots (six snapshots updated for the new hint line and the form box) |
| `just test-parity` (run alone, last) | no failure. The run (alone, 2-hour limit) was stopped by that limit at 89% (about 3960 of 4429 tests passed, none failed); the 19 test files from `tests/services/test_module_guards.py` to the end (630 tests, a few of them repeats of the first run) were then run alone with the same markers and `--adapters sqlite,postgres`: 630 passed. The full run takes more than two hours here |
| `just demo P1-I2b` on SQLite and Postgres | 7 of 7 clauses PASS on each (rerun on e0dfc63) |
| `just demo P1-I2` on SQLite and Postgres | 9 of 9 clauses PASS on each (rerun on e0dfc63) (its three `expect` lines changed to the new refusal text) |

## Security review
For the orchestrator's fresh-context review (commits that change roles, the authorizer, access levels or CLI gates):

| Commit | What it changes |
|---|---|
| `df5af6d` S1 | ADR-0013 (design), ADR-0009 addendum, ADR-0008 decision 3 note, ADR-0011 status |
| `c8a6491` S2 | `types.py` (`Role`, `ROLES`, `Principal.is_controller`, `CONTROL_ACTION_PREFIX`), `provider.py` (`RoleAuthorizer`), `accounts.py` (role rules by kind), `queries.py` |
| `bd05848` S3 | `tl_api/commands.py` (`controller` access, `action_for`, `controller_actions`), `app.py` (default authorizer), documents `commands.py`, admin route role sizes |
| `736880c` S4 | `tl_cli/session.py` (`require_controller`), the eleven call sites, `admin_user.py` (`--add`, `--remove`) |
| `cfcfb70` S5 | `tl_tui/embedded.py` (`_controller_gate`, `issue_transmittal`), the accounts screen and form, the composer key |
| `716105b` S6 | the HTTP matrix tests (no source change) |

Points worth a reviewer's time:
- A `control.*` action is an admin's unless the exact action is in the authorizer's list; the default list is empty and `create_app` fills it from the typed command table. A typo, a hand-written name and a listed non-`control.*` name open nothing (tests in `tests/auth/test_document_controller.py` and `test_commands.py`).
- `Principal.is_controller` and `_may_control` refuse an agent first, whatever its roles.
- `require_controller` checks the session's principal, as `require_admin` does; in a dev setup `--actor` still names anyone on a ledger file (ADR-0009 section 7, unchanged).
- The embedded TUI client re-checks the account (active, the actor's own string, one of the two roles, not an agent) before `issue_transmittal`; the remote client leaves the decision to the server.
- `tl doc import --apply` moved from admin to controller; `tl tag import --apply`, `RecordTag`, the registry and link recovery stayed admin (ADR-0013 section 3).

## Review follow-up (S11)
The fresh-context review of b5b761c passed with four LOW findings, all fixed in `e0dfc63` with tests: (1) tests for the embedded `_controller_gate` (`test_embedded_controller_gate.py`: admin, controller, controller alone, sim controller allowed; user, no account, disabled, agent, folded actor strings refused); (2) `issue_transmittal` refuses a command whose actor is not the client's; (3) `action_for` raises `ValueError` for an unknown `access` value; (4) `accounts.set_roles` takes `expected_roles` and refuses a stale list with 409 `account_state` (API body, admin client, TUI clients and accounts screen pass it), and `tl admin user roles --add/--remove` read the roles inside the write unit of work. ADR-0011 and ADR-0009 tidied; learning L-P1-I2b-6. Parity was not rerun, as agreed (changes are outside the adapters).

## Decisions
- **ADR-0013** records them: three roles stored alphabetically; the ten commands and `tl doc import --apply` are the controller's; tag import, `RecordTag`, `AdminFlagLink`, `AdminRetractLink`, the standards commands and all `admin.*` stay the admin's; `document_controller` may stand alone (it then has every `user` right); a `sim` account may hold it, an `agent` account never; only an admin grants it.
- The explicit list is derived from the typed table (`controller_actions()`), not written by hand in `tl_core`, so core stays module-agnostic and a new `controller` command is open to the role from its declaration.

## Deviations from plan
- **The simulator does not issue.** The request asked for a seeded simulated controller or an issuing step for the registrar. Simulated people sign in with dev tokens, which carry the `user` role only by design (ADR-0009 section 9); a controller identity would need either roles read from an account for a dev token (an ADR-0009 change and a new privilege path from the token file) or a session sign-in for one identity in the connector. Both are an orchestrator or owner call, so the registrar still registers and drafts only (its docstring now says why) and the demo exercises the role with real accounts. Filed as a follow-up in ADR-0013.
- `tl admin user roles` gained `--add` and `--remove` (the request wrote `--add document_controller`); `--role` (replace) still works and the two are exclusive.
- The TUI got one new key, `Ctrl+T` in the transmittal composer (draft and issue), because the register had no controlling action to offer a controller. `r` on the accounts screen now keeps the other roles when it toggles admin.
- The two matrix tests of `test_api_documents.py` moved to `test_api_document_controller.py`, which runs on both adapters; `test_api_documents.py` keeps the access pin.
- Three module tests were fixed after the full run (S9).

## Escalations and decisions
None needed. The owner request is recorded in ADR-0013 and `docs/reports/APPROVALS.md` (two lines: the role design, and the documentation-only schema change).

## Learnings
L-P1-I2b-1 to L-P1-I2b-6 appended (6: a role toggle needs `expected_roles`, and a gate must compare `cmd.actor`): a list that opens a privilege must fail closed (explicit set from the typed table); the CLI refusal tests only refuse on SQLite and a refusal text is pinned in tests and demos (grep before changing it; the full run found three module tests); a one-row TUI hint line cuts text silently, `snapshot_report.html` is tracked and rewritten by snapshot runs, `Ctrl+I` is Tab; `document_controller` was already a Phase 0 simulated person's name; the role list is stored alphabetically so `ROLES` is too.

## Docs
- Created: `docs/adr/0013-document-controller-role.md`, `docs/tickets/P1-I2b/README.md`, this report.
- Updated: ADR-0008 (decision 3 note), ADR-0009 (addendum and the privilege row), ADR-0011 (status: superseded in part, opening of the decision); `docs/runbooks/accounts-and-access.md`, `docs/runbooks/documents.md`, `docs/modules/documents/README.md`; READMEs of `tl-api`, `tl-core`, `tl-cli`, `tl-tui`, `tl-sim` and the documents module, and `AGENTS.md` of `tl-cli` and the documents module; `docs/reference/openapi.json` (generated); `docs/reports/APPROVALS.md`; `docs/memory/LEARNINGS.md`.
- Not updated, for the orchestrator: the Showcase item 3 of `docs/reports/P1-I2.md` and its follow-up line about a document-controller role (both predate this increment), and `docs/reports/STATUS.md`.

## Follow-ups filed
- Let the simulator issue: decide how a simulated person gets the role (dev-token roles from the account, or a session for one identity); then an issuing step for the registrar (needs a PDF upload and `IssueRevision`).
- A project-level assignment of the role (SSO increment, ADR-0013 known limits).
- Separation of duties (a controller issuing what she drafted) is not enforced; the events name the actor.

## Showcase
Three things to show a document-control person. State: the demo ledger after clause 1 of `dev/demos/P1-I2b.sh` (standards and the document pattern loaded; `ISO-1234` with a draft revision A that has a PDF; accounts `demo` (admin), `amy` (user) and `dora` (user)). Build it by running the commands of clause 1 against a dev ledger (`tl init --dev`, `tl login demo`, add `amy` and `dora`).

1. **Granting the document controller role.**
   - Where: `uv run tl admin user roles dora --add document_controller --reason "takes over document control"`, or the TUI accounts screen (`F10`, highlight `dora`, `c`); then `uv run tl admin user show dora`.
   - Standard activity: giving a colleague the right to issue drawings and send transmittals.
   - Novel approach: it is a role of its own, not "make her an admin": the grant is an event with the admin and the reason, it takes effect on her open session at once, and taking it away (`--remove`) closes the same commands again.
   - Unique value: the person who controls the documents does not also hold the keys to accounts, tokens and the engineering registry.
2. **Issuing without an admin.**
   - Where: as `dora` (`tl login dora`): `uv run tl doc rev issue ISO-1234 A --project P123 --status IFC`, then `tl transmittal create ... --revision ISO-1234@A` (anyone drafts) and `tl transmittal issue P123-TRN-0001 --project P123`. As `amy` the same commands answer `error: forbidden: this command needs the document_controller or admin role`. In the TUI: `F7`, `t`, `Ctrl+T` draws up and issues in one step.
   - Standard activity: a document controller issues a revision for construction and sends the transmittal.
   - Novel approach: drafting is anyone's work, issuing is the controller's act, and the ledger names the person who did it (`user:dora`), not an admin acting for her.
   - Unique value: a provable answer to "who issued this revision, and were they allowed to".
3. **The controller stops where document control stops.**
   - Where: as `dora`: `uv run tl admin user ls`, `tl admin user roles dora --add admin` and `tl admin token ls` are all `forbidden`; over HTTP `GET /admin/accounts` is 403 `forbidden`; an agent token gets `agent_must_propose` on every controlling command. Clause 5 of `just demo P1-I2b` prints the whole matrix.
   - Standard activity: least privilege for a role that handles controlled records.
   - Novel approach: the allow-list is typed and explicit (`control.command.<Name>`), an unlisted name is an admin's, and no agent can hold the role.
   - Unique value: a mistake in a list or a name closes a door instead of opening one.

## Cost notes
Not tracked per call. No implementer or reviewer runs; the supervisor built, tested and documented every piece. The full `just test` took 46 minutes alone on the 4-core container.
