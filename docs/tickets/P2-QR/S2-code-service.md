# P2-QR-S2 — Code service, the three commands with hooks, the resolver, `label_fields`, the subject row

kind: piece
review: full
branch: p2/qr-s2-code-service
worktree: /home/user/wt/qr/s2
Base: `p2/ip` with `p2/x4` merged (`p2/ip-x4`, made by the orchestrator). Merge note: **waits for X4 on trunk**. Order: first of three S2s (owns the `test_forms_rows.py` edit).
Read first: `docs/tickets/P2-IP/S2-common.md` (hooks, marks, decided, pins, traps, escalation). Gated: access-worded commands, `confidentiality.py` subject part, the code
generator and hash (APPROVALS lines at merge). Labels: core, access, confidentiality, security.

## Why
`docs/build-spec/specs/qr-workface.md` §2, §5-§7 and ADR-0030. S1 froze the schema, the settings, the words and the card contract (`tl_core/qr/{types,registry}.py`). Nothing issues, revokes or
resolves a code yet. T01, T06 and T07 and the scan page (S3) are written against the names this piece freezes.

## Goal
1. **Code and hash** `tl_mod_qr/codes.py`: `new_code() -> str` (16 characters of Crockford base32 `0123456789ABCDEFGHJKMNPQRSTVWXYZ`, 80 bits from `secrets`), `normalise(text) -> str | None`
   (strip spaces and dashes, upper case, `None` unless the 16 characters match the alphabet), `hash_code(code) -> str` (SHA-256 hex of the normalised code), `display(code) -> str` (four groups with `-`).
   The code is never stored, logged, put in an event, an error text, a repr or an exception: the one place it exists is the return value of the issue service.
2. **Commands** `tl_mod_qr/commands.py`, models with the base envelope, `extra="forbid"`, texts cleaned with `tl_core.text`; handlers in `tl_mod_qr/handlers/`; rows in `tl_mod_qr/module.py` `COMMANDS`:
   | Command | Word (table word) | Mark | Rule |
   |---|---|---|---|
   | `IssueScanCode` | `qr.issue` (user) | `excluded:access` | fields `target_id`, `label_text` (<= 40, optional), `size` (`tag`, `card`, `sheet`; default `tag`), `expires_on` (date, optional, not past). Refused with the fixed message `set api.public_base_url first` while the setting is empty (`tl_core.settings.resolver.value_of`). Target must be a record the actor can read and whose type has a registered scan card provider; a hidden, missing, other-project or card-less target answers one text (`no record with that id`). Refused at `qr.codes_per_record_max` live codes (fixed message, no count). Appends `ScanCode.Issued` with the hash only; key `none` (no numbering) |
   | `RevokeScanCode` | `qr.revoke` (controller) | `excluded:reserved` | fields `code_id` (the register id, never the code), `reason` (1..300). Already revoked is a fixed message. Appends `ScanCode.Revoked` |
   | `RotateScanCode` | `qr.issue` (user) | `excluded:access` | fields `code_id`, `reason`; one unit of work: revoke the old row with `replaced_by_id` set, issue a new code for the same target, label, size, expiry; the actor needs the target's read right, not the revoke word |
   Exclusions file: three entries (`IssueScanCode`, `RotateScanCode`: "a label is a bearer path to site status; a person prints it"; `RevokeScanCode`: "act: revoking is the controller's decision").
   `command_words` carries the three. `proposable=()` stays.
3. **Issue service (the secret leaves once)** `tl_mod_qr/service.py`: `issue(uow, cmd) -> IssuedCode(code, result)` and `rotate(uow, cmd) -> IssuedCode`. The handlers in `COMMANDS` call them and drop the code (a
   `POST /commands/IssueScanCode` issues a code nobody sees: harmless, listed in the report); the CLI (T07) and the web form (later) call the service and show the code once. State in the report how the
   handler and the service avoid two code paths (the handler is the service minus the return).
4. **Resolver** `tl_mod_qr/resolve.py`: `resolve(conn, code: str, viewer: Viewer, now: datetime) -> ScanCard | None`, **one exit for every miss**: malformed (no query at all), unknown, revoked, expired, hidden
   target (card `None`), viewer without the provider's `view_word`, no provider installed. Order: normalise, hash lookup (the first statement, before any other work), state and expiry, provider lookup
   (`tl_core.qr.registry.load_scan_cards`), view word, `provider.card(conn, target_id, viewer, now)`. A provider that raises is a miss and writes nothing. The default viewer is the lowest clearance everywhere
   (`confidentiality.LOWEST`), never widened. It never writes.
5. **`label_fields(target, viewer)`** `tl_mod_qr/labels.py` (the existing renderer file; add the function, change nothing else): returns `LabelFields(key: str | None, text: str | None)`: the record's key and
   the typed text for a record at the lowest class, both `None` above it or when the viewer cannot read it. One rule; every label surface calls it. Find the class read in `tl_core/confidentiality.py`; do not add a core function.
6. **Surfaces stubs and hooks** `tl_mod_qr/{routes,tools,cli}.py` per the common rules (`router`, `register_tools`, `qr_app`); `module.py` `spec()` gains `commands="tl_mod_qr.module:COMMANDS"`,
   `read_routers=("tl_mod_qr.routes:router",)`, `tools=("tl_mod_qr.tools:register_tools",)`, `cli_groups=("tl_mod_qr.cli:qr_app",)`. `pyproject.toml`: `fastapi`, `mcp`, `typer` (common rules: no `tl-api`, `tl-mcp`, `tl-cli`).
7. **Errors** `tl_mod_qr/errors.py`: subclasses of core error classes with fixed messages (common rules).
8. **Subject row** in `tl_core/confidentiality.py`: append `("qr.ScanCode", "cur_qr_scan_code", "id", "target_id")` to `SUBJECT_LINKS` after the forms rows, with a comment (a code is hidden when its target is;
   a code whose target is a permit or an inspection follows that record's own subject on the second hop, deeper stops, `_HOPS` unchanged). Test file `tests/confidentiality/test_qr_rows.py`: a code for a restricted
   record is absent for the five readers of the forms pattern (nobody, agent, plain user, cleared, admin per class) in `ScanCode` reads, counts and the activity feed; present for the cleared; a code for
   a punch item raised from a restricted record is hidden on the second hop; a chain of three stops at two hops (the record reached on the last hop governs); the join-budget test still passes.
   **This piece also edits `tests/confidentiality/test_forms_rows.py`**: the two assertions that pin `SUBJECT_LINKS[:6]` and `SUBJECT_LINKS[6:]` become `[:6]` and `[6:9]` (the forms rows) so later rows append without touching it.
9. **Provided test of T01** (plan-check F8): write `docs/tickets/P2-QR/provided/T01_test_views.py` for `tl_mod_qr/views.py` before this piece ends, lint-clean at `packages/tl-modules/qr/tests/test_views.py`
   (ruff format, ruff check, pyright run there). Interfaces it pins (T01 is written against them): `codes_for_record(conn, record_id, *, viewer=LOWEST) -> list[CodeRow]` (newest first, at most 100),
   `code_counts(conn, *, viewer=LOWEST) -> dict[str, int]` (keys `live`, `revoked`, `expired`), `export_rows(rows, fmt: Literal["csv", "jsonl"]) -> str`; `CodeRow` holds id, label_text, size, issued_by,
   issued_at, expires_on, state, revoked_at, replaced_by_id and **never the code or its hash**; the hidden filter runs before LIMIT and before counting; a hidden record gives `[]` and zero counts. `views.py` itself
   is a stub in this piece (names raise `NotImplementedError`), so the provided test is red until T01.

## Provided tests (copy byte-identical; they need only the hooks)
`docs/tickets/P2-IP/provided/S2_ip_rules.py` to `tests/services/ip_rules.py`; `S2_test_qr_rules.py` to `tests/services/test_qr_s2_rules.py`. Own tests (names; behaviour in parentheses):
`packages/tl-modules/qr/tests/`: `test_codes.py` (alphabet, length, 10 000 distinct, normalise round-trip and refusals, hash equals SHA-256, display groups), `test_commands.py` (issue refused without the base, with it ok;
cap; hidden target and card-less target give one text and write nothing; revoke; rotate old miss, new hit; no event, error text or log line holds the code: scan the events table, the exception texts and `caplog`),
`test_resolve.py` (the five misses compare equal as values; statement counter: a malformed code runs zero statements, a hit's first statement is the `code_hash` lookup; a raising provider is a miss; `view_word` missing is a miss),
`test_label_fields.py`, `test_module_spec.py` (updated: three commands, hooks present, refs start with `tl_mod_qr`). Fake provider and fixtures: `packages/tl-modules/qr/tests/conftest.py` (extend; no entry-point install).

## Allowed paths
- `packages/tl-modules/qr/**` (source, tests, `pyproject.toml`, README and AGENTS.md lines for the new files)
- `packages/tl-core/src/tl_core/confidentiality.py` (the one tuple and its comment), `tests/confidentiality/{test_qr_rows.py,test_forms_rows.py}` (the two pin lines only)
- `tests/services/{ip_rules.py,test_qr_s2_rules.py}`, `tests/tools/{proposable_exclusions.toml}` (append), `docs/tickets/P2-QR/provided/T01_test_views.py`
- the three baseline pins and `uv.lock` of the common rules, `docs/reports/P2-QR/S2.md`, `dev/accept/P2-QR/S2.py` (SQLite, one `PASS <check>` line per check, final `S2 ok`)
Read-only: everything else (schema, `tl_core/qr/**`, `tl_web`, `tl_api`, other modules).

## Acceptance (once each, one at a time)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-modules/qr/tests
just gate tests/services/test_qr_s2_rules.py tests/services/test_module_conformance.py tests/services/test_module_hooks.py tests/tools/test_registry_by_hooks.py
just gate tests/confidentiality/test_qr_rows.py tests/confidentiality/test_forms_rows.py
just gate packages/tl-cli/tests/test_module_cli_groups.py packages/tl-mcp/tests/test_module_tool_hooks.py
just gate packages/tl-api/tests/test_module_hooks_api.py
just gate-pg packages/tl-modules/qr/tests tests/confidentiality/test_qr_rows.py
uv run python dev/accept/P2-QR/S2.py
```

## Mutation (sentinel and at most 5, in this worktree, 3 lines in the report)
Sentinel: `resolve` returns the card for a revoked code. Targets: lookup after the provider call (statement-order test); `view_word` check skipped; the cap off by one; the `ScanCode` row removed from `SUBJECT_LINKS`; rotate leaves the old code live.

## Report
`docs/reports/P2-QR/S2.md` (<= 60 lines): deviations first; the code path decision (item 3); pins changed with old and new counts; marks and exclusions chosen; gate output (<= 5 lines per command); mutation 3 lines;
final signatures the tickets need (`IssuedCode`, `LabelFields`, `CodeRow`, `COMMANDS`). Builder return <= 15 lines. Commit `P2-QR-S2: ...`.
