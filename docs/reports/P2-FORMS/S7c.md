# P2-FORMS S7c report: intake commands and the code functions

Deviations: (1) `IssueIntakeCode` appends `Record.Created` with `key: null` directly, not `create_module_record(key=None)`: a code takes no number, so that call would fail on a missing numbering pattern (the way `SaveFormDraft` does it). (2) `AcceptIntakeItem` returns the move and `Purged` events only, not `Accepted` (it holds the claim; the spec bars the claim from a result's repr). (3) `names.py` gains `T_REVOKE`, `T_REJECT`. (4) `forms_world.py` gains intake helpers and `hidden_record(to_class)`. (5) Pre-existing failure left alone (not my path): `packages/tl-modules/awp/tests/test_proposable_exclusions.py` fails on S3's forms exclusion names, also with my toml lines reverted.

## Commands (`FORMS_COMMANDS`: 11 to 15, none PROPOSABLE)
| Command | Word | Fixed texts |
|---|---|---|
| IssueIntakeCode | forms.intake.issue | MSG_UNKNOWN (context, template id), MSG_NOT_PUBLISHED, MSG_NOT_INTAKE, MSG_EXPIRY, MSG_CODE_TAKEN, MSG_PROJECT |
| RevokeIntakeCode | forms.intake.issue | MSG_UNKNOWN, `FormStateError` (state name only), MSG_STALE |
| AcceptIntakeItem | forms.intake.review | MSG_UNKNOWN, state, MSG_STALE, MSG_NOT_ACCEPTED_AS; seam texts (`MSG_NOT_NESTABLE`, `MSG_ARGS`, `MSG_ACCESS`) |
| RejectIntakeItem | forms.intake.review | MSG_UNKNOWN, state, MSG_STALE |
Order: project scope, then id (hidden, absent, other project, other type: `MSG_UNKNOWN`), then state, version, arguments.

## `tl_core/qr/codes.py` (frozen, imports `hashlib`, `secrets`, `re`)
`ALPHABET` (32), `CODE_LENGTH = 16`, `new_code() -> str`, `normalise_code(text) -> str | None`, `code_hash(code) -> str` (ValueError, no input text), `grouped(code) -> str`.

## D15 to D18 as applied
D15 as specified; QR S2 must import it. D16 the command takes `code_hash` (pattern `^[0-9a-f]{64}$`). D17 the nested command is the controller's `command_args`; the seam gets `actor`, item scope, source `intake:<code id>`, cause = the `Received` event id, and `holder_for_actor` of the controller. The body is read once for `{name, company}` from the answers `claim_name`, `claim_company` (control and bidi removed, trimmed, 80 characters); phone never read; a body that is not `{"answers": [...]}` gives a null claim. `cause_event_id` is the first event of the nested result. D18 delete plus `Purged` in the same unit; reject keeps the body.

## Pinned lists
`tests/tools/proposable_exclusions.toml`: 4 lines added (forms names 10 to 14 excluded). `test_module_spec.py`: 11 to 15 commands; `test_exclusions.py`: 10 to 14. `tests/services/test_modules.py` and `packages/tl-api/tests/test_auth_review.py`: no change needed (52 passed).

## Note for the security review (D16, F-S7c)
A caller can hash a weak, chosen code; the issuer holds `forms.intake.issue` and a code opens a staging door only. Per-address and per-code limits (S6) are the defence. A malformed `code_hash` is refused by pydantic, whose own text may echo the input hash (a hash, not a code). Accept runs a stranger-influenced item only through the controller's own `command_args`; a controller with no word for the nested command is refused inside the unit.

## Gate
check: ruff, format, generate, compat, openapi check and compat, licences pass. Whole-repo pyright was killed twice (exit 247, memory with other builders live); pyright over forms and the qr files: 0 errors.
1 test_qr_codes 22 passed. 2 forms/tests 177 passed (one run, 178 s). 3 pinned lists 52 passed. 4 gate-pg item and code commands 92 passed (554 s). `gate: PASS`.

## Mutation
sentinel P (CODE_LENGTH 15 killed by test_qr_codes), 5/5 killed, +0: holder None (killed by the no-word controller test); accepts_as check off (outside-accepts_as test); phone copied (accept test); body not deleted (accept test); visibility check off (hidden item and hidden code tests).

## Tests that change later
S6 replaces `stage_item`/`stage_code` in `forms_world.py` with the real service. I06 adds the five-reader walk of the queue; I03 the queue views.

## Candidate learnings
`hidden_record()` restricted is readable by an admin: a test that needs a controller-hidden context uses `privileged`. `create_module_record(key=None)` needs a numbering pattern.
