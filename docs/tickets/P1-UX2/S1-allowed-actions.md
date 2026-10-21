# P1-UX2-S1 — Allowed-actions query, and file access on the client interface

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: core, api, tui, tests, docs
Depends on: none
Branch: `p1/ux2-s1-allowed-actions`

## Goal
"Which actions may this viewer take on record X now" is answered by the module that owns the record type, through
one additive core hook, one additive API route and one client method (embedded and remote). The same piece adds the two module command runners the TUI lacks (documents, tags) and gives the
client interface the two file reads the preview needs. Nothing about command semantics, events or stored data changes;
CLI, MCP and every existing API response stay byte-identical.

## Brief references (pasted, abridged)
> SCOPE §2: answered by the module (state machine + role and class rules already in the commands), exposed through
> the client interface (embedded and remote) and an additive API route. A refusal from the command is still shown by
> the screen. A record the viewer may not read answers exactly like a missing record. First types: RFIs and other
> technical items, commercial notices, correspondence items, documents/revisions (issue, supersede, void, transmittal
> where the viewer may), tags.
> ADR-0016 §4/§5: a hidden record is absent on every read path; reads default to the lowest viewer; a new route that can
> carry record text needs the five-reader walking test. AGENTS: authorization is closed for agents; a new route is
> denied until allowed. SCOPE §4: remote mode downloads through the existing file routes; hash and confidentiality
> unchanged.

## Interfaces
```python
# tl_core/actions.py (new)
Level = Literal["user", "controller", "admin"]
Holds = Callable[[Level], bool]            # the same decision the API authorizer / embedded gates make
class ActionOffer(BaseModel): command: str; label: str      # label is plain words ("Answer", "Close", "Issue")
class RecordActions(BaseModel): record_id: str; state: str | None; actions: list[ActionOffer]
ActionsHook = Callable[[Connection, str, Holds], list[ActionOffer]]   # (conn, record_id, holds)
def allowed_actions(uow, record_id: str, *, actor: str, holds: Holds) -> RecordActions
    # 1 visibility first (confidentiality.is_hidden / require_visible): hidden or missing -> RecordNotFoundError, same text
    # 2 an agent actor (agent:*) gets actions=[] (agents propose, they never change a record)
    # 3 the record's module hook by record type; a type with no hook gets []
# tl_core/modules.py: ModuleSpec gains   actions: Mapping[str, ActionsHook] = field(default_factory=dict)
#   validated in __post_init__ like generic_commands (record type must belong to the module)

# tl_api: GET /records/{record_id}/actions   operation_id get_record_actions   response RecordActions
#   reader access; builds holds from the principal exactly as routes/proposals.holds_access does; hidden/missing -> 404 record_not_found
#   ApiClient.allowed_actions(record_id) in tl_api/client/records.py

# tl_tui.client.ClientInterface (additive)
def allowed_actions(self, record_id: str) -> RecordActions
def list_record_files(self, record_id: str) -> list[FileInfo]       # current attachments the viewer may read (tl_core.files.queries.FileInfo)
def document_command(self, name: str, cmd: Command) -> CommandResult      # like correspondence_command: the module's own command table,
def engineering_command(self, name: str, cmd: Command) -> CommandResult    # access word enforced (controller/admin gate), actor checked, own_writes noted
    # embedded: the module's API_COMMANDS rows; remote: POST /commands/<Name>. The TUI offers an action only for names these accept.
def fetch_file(self, file_id: str, dest_dir: Path) -> Path
    # writes dest_dir/<sanitised filename> (mode 0600, never outside dest_dir, no overwrite: add a numeric suffix),
    # verifies size and sha256 against FileInfo BEFORE returning (mismatch: delete the partial file, raise),
    # embedded: FileService.open_file under the viewer; remote: ApiClient.download_to via the existing file route.
    # A hidden or missing record's file raises the same not-found error for both.
```
Module hooks (each a pure function over the module's own registry rows and `holds`; the table of command -> record
types -> states -> level lives in the module, ONE source also read by the handlers' `require_state` calls so the two
cannot drift; handlers change only the state arguments they pass):
- correspondence: correspondence items, technical items (RFI: submit, return, issue, answer, review answer, reissue, close,
  escalate), commercial items (all controller-level, `controller_only`), plus void/close/triage/record-response on items.
- documents: documents and revisions (issue revision, supersede revision/document, void document/revision, create
  transmittal; issue transmittal is a controller act) and transmittals (issue, close, void by state).
- engineering: tags (reclassify, rename, merge where the commands exist).
Labels are plain words, owned by the module. Commands that need no record state (register, create) are not offers.

## Context (≤ 10 files)
- `packages/tl-core/src/tl_core/modules.py` (ModuleSpec, GENERIC_COMMANDS, require_generic)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/{module.py,commands.py,names.py,guards.py,handlers/common.py}`
- `packages/tl-modules/documents/src/tl_mod_documents/{module.py,commands.py,guards.py}`, `engineering/.../{module.py,commands.py}`
- `packages/tl-api/src/tl_api/{commands.py,routes/proposals.py,routes/records.py,routes/files.py}`, `tl_api/client/{records.py,files.py}`
- `packages/tl-tui/src/tl_tui/{client.py,embedded.py,remote.py}`, `packages/tl-tui/tests/fakes.py`
- `packages/tl-api/tests/test_confidentiality_walk.py`
may explore: `packages/tl-core/src/tl_core/files/{service.py,queries.py}`, `docs/adr/0010-module-record-storage.md`

## Allowed paths
- `packages/tl-core/src/tl_core/actions.py` (create), `packages/tl-core/src/tl_core/modules.py`
- `packages/tl-modules/correspondence/src/**`, `packages/tl-modules/documents/src/**`, `packages/tl-modules/engineering/src/**` (hooks, state constants shared with handlers; no change to command behaviour)
- `packages/tl-modules/{correspondence,documents,engineering}/tests/**`, `packages/tl-core/tests/**`, `tests/services/test_modules.py`
- `packages/tl-api/src/tl_api/routes/actions.py` (create), `routes/__init__.py`, `app.py`, `client/records.py`, `client/files.py`
- `packages/tl-api/tests/**`, `docs/reference/openapi.json` (regenerated, the only change: the new route and `RecordActions`, `ActionOffer`)
- `packages/tl-tui/src/tl_tui/{client.py,embedded.py,remote.py}`, `packages/tl-tui/tests/fakes*.py`, `packages/tl-tui/tests/test_embedded_*.py`, `test_remote_client.py`, `test_fakes.py` (new files allowed: `test_embedded_actions.py`, `test_remote_actions.py`)
- `docs/adr/0010-module-record-storage.md` (addendum: the `actions` hook and its rules, ≤ 20 lines)
- `docs/reports/P1-UX2/S1.md` (create)

Consequential pins (rule 12): an OpenAPI snapshot or a client-method list test that breaks only because the new route
or methods exist is updated here and listed in the report. Anything else outside these paths stops.

## Steps
1. `tl_core/actions.py` and `ModuleSpec.actions` with the visibility-first rule and the agent rule; unit tests with a fake module.
2. The three module hooks with their single-source state/level tables; refactor the handlers' `require_state` arguments to read them.
3. Route, `ApiClient.allowed_actions`, openapi regen, walking-test entry (five readers: user, controller, admin, agent, anonymous/hidden-class owner).
4. Client interface: `allowed_actions`, `list_record_files`, `fetch_file` on embedded, remote, and every fake (default: no actions, no files; settable).
5. ADR-0010 addendum, report.

## Acceptance (run these, once)
```
just check
just gate packages/tl-core packages/tl-modules/correspondence packages/tl-modules/documents packages/tl-modules/engineering packages/tl-api packages/tl-tui tests/services/test_modules.py tests/services/test_module_guards.py | tee .gate/summary.txt
just gate-pg packages/tl-modules/correspondence packages/tl-modules/documents packages/tl-api/tests/test_confidentiality_walk.py packages/tl-tui/tests/test_embedded_real_services.py
```
Expected: gate PASS on both adapters; `just check` clean (openapi drift test included). Do not run the whole suite.

## Tests to add
- `packages/tl-core/tests/test_actions.py` (new): hidden id and missing id give the identical error; an agent gets `[]`; a type with no hook gets `[]`; hook not called for a hidden record (spy).
- `packages/tl-modules/correspondence/tests/test_actions.py` (new): for an RFI in each state (Draft, Internal review, Awaiting response, Answered, Rejected, Accepted, Closed, Void) and viewers user, controller, admin: the offered set equals the set of commands the handlers do not refuse on state or access grounds (drive Answer, Close, Issue, Escalate, Submit, Reissue for real); an Answer is offered to an answerer in Awaiting response and not in Draft; commercial items offer nothing to a plain user and the controller set to a controller; a privileged item not named to the viewer answers not-found.
- `packages/tl-modules/documents/tests/test_actions.py` (new): draft revision offers issue to a controller only; issued current revision offers supersede; void document offers nothing; transmittal draft vs issued.
- `packages/tl-modules/engineering/tests/test_actions.py` (new): tag actions by state and role.
- `packages/tl-api/tests/test_api_actions.py` (new): route returns the same body for hidden and missing (status, JSON, header set); an agent token gets `[]`; unauthenticated 401.
- `packages/tl-api/tests/test_confidentiality_walk.py`: the new route exercised as five readers (no secret word of a hidden item in any answer; route classified).
- `packages/tl-tui/tests/test_embedded_actions.py`, `test_remote_actions.py` (new): `document_command` / `engineering_command` refuse a name that is not in the module's table and an access the viewer lacks (same errors as `correspondence_command`); `allowed_actions` embedded and remote agree for the same record; `fetch_file` writes mode 0600 in `dest_dir`, rejects a hostile name (`../x`, absolute, leading `-`, NUL), verifies the hash (a tampered store byte raises and leaves no file), and a hidden record's file raises the not-found error.

## Mutation (builder, own worktree, 3 lines in the report)
Sentinel plus at most 5 targeted mutants: (1) skip the visibility check in `allowed_actions`; (2) agent branch removed; (3) widen Answer's state set to include Draft; (4) `holds("controller")` replaced by `holds("user")` for Issue or any commercial command; (5) skip the sha256 check in `fetch_file`. Each must be killed by a test above.

## Report requirements
`docs/reports/P1-UX2/S1.md` ≤ 60 lines: deviations first, consequential pins, commands run with ≤ 5 decisive lines each, the state/level table location, candidate learnings.

## Escalation triggers
- A command's access word or state rule cannot be expressed without changing the command's behaviour: stop, list it.
- `ModuleSpec` change would break an existing module spec or the module-loader tests beyond adding the field.
- File service unavailable in embedded mode: do not invent a store; raise the typed "files not available" error and say so.
