# P2-FORMS-INTAKE S7c — Intake commands: issue, revoke, accept (through the seam), reject; and the code functions

kind: piece
review: full
branch: p2/forms-s7c-intake-commands
worktree: /home/user/wt/forms/s7c
Depends on: S2, S3 (seam `tl_core/services/nested.py`, `FORMS_COMMANDS`), CR1 (intake rows) merged on `p2/ip` (@8878427d). The builder starts with `git merge p2/ip`.
Gated: security (code hashes; the accept path runs a command with a stranger's text as input; owner approves, APPROVALS line), core interface (the new
frozen file `tl_core/qr/codes.py`, D15). Labels: core, module, security. Heavy runs: at most 2 at once.

## Why
ADR-0032 decisions 3, 5, 7, 8, 9, 11; forms-eval §8.3 (S7c); plan README items I00 and S7c. Tables, events, workflows, words and settings are S2's; the seam is S3's;
the intake rows of `confidentiality.py` are CR1's (an item is hidden through its code, a code through its `context_id`; a code with no context is its own subject and
no source classes it, so the controller words guard those reads). S6 (public route) and the signed-in queue (I03) are written over the commands fixed here.

## Decisions this spec makes (record in the report and in the module `AGENTS.md`)
- **D15 the code functions are written here, not lifted.** I00 assumed QR S2 had written them; QR S2 is not started. This piece creates the frozen pure module
  `packages/tl-core/src/tl_core/qr/codes.py`, imports only `hashlib`, `secrets`, `re`:
  ```python
  ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"        # 32 symbols: no I, O, 0, 1
  CODE_LENGTH = 16                                      # 80 random bits
  def new_code() -> str                                 # 16 symbols from ALPHABET, `secrets.choice`; never logged
  def normalise_code(text: str) -> str | None           # strip spaces and hyphens, upper-case; None unless exactly 16 ALPHABET symbols
  def code_hash(code: str) -> str                       # sha256 hexdigest of the normalised code, 64 lower-case hex; ValueError on a non-code
  def grouped(code: str) -> str                         # "7KQ2-M9XA-4TTC-P0HV" form (four groups of four)
  ```
  QR S2 imports these and does not redefine them (the orchestrator tells the QR supervisor). `forms` imports `tl_core.qr.codes`, never `tl_mod_qr`.
- **D16 the server never sees the code.** `IssueIntakeCode` takes `code_hash` (64 lower-case hex, made by the caller with `new_code()` + `code_hash()`), not a code; the
  poster printer (I01, CLI) prints `grouped(code)` once. A caller can therefore choose a weak code; the issuer already holds `forms.intake.issue` (a controller word) and a
  code only opens a staging door, so this is accepted and listed in the report as a note for the wave's security review. The hash is unique (`code_hash` unique key): a second
  issue of the same hash is refused with the fixed `MSG_CODE_TAKEN` (no existing-row detail).
- **D17 accept takes the controller's completed command.** `AcceptIntakeItem` carries `command_type` and `command_args`: the controller (or a UI that prefilled them from
  the staged answers) edits and completes the target command. The handler never builds the command from the stored body. Accepted text reaches the typed event only through
  `command_args`. The staged body is read once, for `on_behalf_of_claim` (`claim_name`, `claim_company` of the body, each ≤ 80 characters, cleaned; `claim_phone` is never copied).
- **D18 body removal.** Accept deletes the item's `forms_intake_body` row and appends `IntakeItem.Purged` in the same unit (ADR-0032 decision 11: accepted text lives in the
  typed event). Reject keeps the body for the retention window (S6's purge job removes it).

## Goal
1. `tl_core/qr/codes.py` and `packages/tl-core/tests/test_qr_codes.py` (D15). 2. Four commands in `tl_mod_forms/commands.py` with handlers in `handlers/intake.py`, rows in `FORMS_COMMANDS`
(copy S3's style: `extra="forbid"`, `clean_text`, `expected_version` where a record changes, one unit each):
| Command | Word (access) | Does |
|---|---|---|
| `IssueIntakeCode` | `forms.intake.issue` (controller) | project scope; `code_hash`; `template_id` (a Published template with `intake == "public"`; version, `content_hash` are read from it and pinned); optional `context_id` (a record the issuer may read: `require_subject`; its project must equal the scope; `context_type` is read from it, never given); `heading` 1 to 60 characters, `clean_text`, no control or bidi characters (public text); `controller_role` 1 to 64; `expires_on` ≥ today and ≤ today + `forms.intake.code_max_days` (settings resolver); `create_module_record(key=None)` + `IntakeCode.Issued` (state `Active`) |
| `RevokeIntakeCode` | `forms.intake.issue` | `reason` 1 to 300; Active only; `IntakeCode.Revoked` + the `revoke` transition; a code whose context the actor cannot read answers `MSG_UNKNOWN` |
| `AcceptIntakeItem` | `forms.intake.review` (controller) | Pending only; the item's code context readable (`require_visible`, hidden = `MSG_UNKNOWN`); `command_type` must be in the template's `accepts_as` AND a module proposable (the seam refuses anything else, D8); runs `run_nested_command(uow, command_type, command_args, actor=<controller>, scope=item scope, source=f"intake:{code_id}", causation_id=<Received event id>, holder=<controller's holder>)` so the controller needs their own word for it; then `IntakeItem.Accepted {accepted_as, on_behalf_of_claim, cause_event_id}` + the `accept` transition + body delete + `IntakeItem.Purged`, all in the caller's unit; a refusal rolls everything back and the item stays Pending |
| `RejectIntakeItem` | `forms.intake.review` | Pending only; `reason` one of `spam`, `duplicate`, `not_ours`, `unclear` (enum `IntakeRejectReason`); `IntakeItem.Rejected` + the `reject` transition |
Hidden-looks-missing: an id the actor may not read (item or code through its context), an absent id and a wrong project give the one `MSG_UNKNOWN`, checked before any state or argument.
Messages are fixed texts that never carry a body, a claim, a code or a hash. `command_args` values never appear in an error text (the S3 `MSG_ARGS` rule: the seam already hides them).
3. Registration: `module.py` rows and `command_words`; none is `PROPOSABLE` (a public submission is never proposed by an agent): four exclusion lines in `tests/tools/proposable_exclusions.toml`
(`person acts directly`). Offline: none (`IntakeCode` and `IntakeItem` are class `none`; the commands are central).
4. Docs: module `README.md` and `AGENTS.md` (the four commands, D15 to D18, the messages table).

## Allowed paths
- `packages/tl-core/src/tl_core/qr/codes.py` (create); `packages/tl-core/tests/test_qr_codes.py` (create)
- `packages/tl-modules/forms/src/tl_mod_forms/{commands.py,errors.py,guards.py,module.py,names.py}`, `.../handlers/intake.py` (create), `.../handlers/common.py` (edit only to share a loader)
- `packages/tl-modules/forms/{README.md,AGENTS.md}`; `packages/tl-modules/forms/tests/**` (create the files below; `test_module_spec.py` and `test_exclusions.py` are edited: 11 commands become 15)
- `tests/tools/proposable_exclusions.toml` (four lines)
- Pinned lists, each named in the report with old and new count, only where they fail because the commands exist (candidates: `tests/services/test_modules.py`, `packages/tl-api/tests/test_auth_review.py`, a command-count pin)
- `docs/reports/P2-FORMS/S7c.md` (create)
Not allowed: `schema/**`, `tl_core/confidentiality.py`, `tl_core/services/nested.py`, `tl_core/services/proposals.py`, `tl_core/modules.py`, any other module, `tl_api`, `tl_cli`, `tl_mcp`, `tl_tui`, `tl_web`,
`forms_intake_body` writes other than the one delete above (the insert is S6's). A change in `tl_core` beyond `qr/codes.py` is an escalation.

## Tests to add
Lint-clean where they land (`ruff format`, `ruff check`, strict `pyright`; a wrong-typed call carries `# pyright: ignore[...]`). Statement-count assertions ignore `BEGIN`, `COMMIT`, `ROLLBACK`.
Use `forms_world.py` (access word first, then the handler as that viewer). A test needs a staged item: insert a `Received` event as `svc:intake` and a body row directly (S6 does not exist yet; helper in `forms_world.py`).
- `test_qr_codes.py` (core): alphabet size 32 with no `I O 0 1`; `new_code` has 16 symbols and 1000 draws are distinct; `normalise_code` accepts spaces, hyphens, lower case, refuses 15 or 17 symbols, a symbol outside
  the alphabet and non-text; `code_hash` is 64 hex, equals `hashlib.sha256` of the normalised code, equal for `7kq2-m9xa-4ttc-p0hv`-style input and the plain code; `grouped` round-trips through `normalise_code`.
- `test_intake_code_commands.py`: issue (row Active, hash stored, no field holds a code; heading 61 characters, a control character and a bidi mark refused; expiry past, today and today + max days; max + 1 refused;
  an unpublished, a retired, a non-public and a bound template refused; a context in another project refused; a hidden context answers `MSG_UNKNOWN` as an absent one; a duplicate hash gives `MSG_CODE_TAKEN`);
  revoke (Active only; a revoked code cannot be revoked; the row shows `revoked_by`); words: a plain user holds neither word.
- `test_intake_item_commands.py`: accept as `SubmitForm` for a general template (the submission is made by the controller as actor, source `intake:<code id>`, cause = the Received event; the
  `Accepted` event carries the claim name and company, never the phone; the body row is gone; `Purged` appended; item state Accepted); a refusal inside the nested command (an invalid answer) leaves the item Pending,
  the body row present and no event appended; `command_type` outside `accepts_as`, a core command type and an unknown name refused with fixed text; `command_args` naming `actor` or `source` cannot impersonate;
  the controller lacking the nested command's word is refused (the seam holder rule); accept twice refused; reject (each reason; unknown reason refused; body kept); an item whose code context is hidden answers
  `MSG_UNKNOWN` to accept and reject, byte-identical to an absent id.
- `test_intake_security.py`: marker strings placed in the body, the claim and `command_args` never appear in any exception text, any event other than the typed command's events and `Accepted` claim, or `repr`
  of a result; hostile claim values (control characters, 10 000 characters, bidi marks) are cleaned or bounded; `claim_phone` never reaches an event.
- `test_module_spec.py`, `test_exclusions.py`: 15 commands, every one a row or an exclusion, `PROPOSABLE` still the one row.
- The five-reader walk of the queue is I06; the public route is S6. Say in the report which tests change with them.

## Gate
`just check` (`NODE_OPTIONS=--max-old-space-size=6144`); then one run at a time: 1. `just gate packages/tl-core/tests/test_qr_codes.py`; 2. `just gate packages/tl-modules/forms/tests` (split into two runs if
it nears 10 minutes: the gate runner kills a run over about 10 minutes; name the two halves in the report); 3. pinned lists you touched. `just gate-pg packages/tl-modules/forms/tests/test_intake_item_commands.py
packages/tl-modules/forms/tests/test_intake_code_commands.py`.

## Mutation cap
One sentinel plus at most 5 targeted: the accept runs the nested command with `holder=None` and the controller word of the target is not required; `command_type` not checked against `accepts_as`; the claim phone copied
into `Accepted`; the body row not deleted on accept; the hidden-context check removed from reject. 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines at `docs/reports/P2-FORMS/S7c.md`; first line deviations or none. List: the final command table with messages, the `codes.py` signatures, every pinned file with old and new
count, D15 to D18 as applied, the note on D16 for the security review. Commit `P2-FORMS-S7c: ...` with the session trailers; no model names in committed text.
