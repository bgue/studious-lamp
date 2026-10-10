# P0-I3-T02b — `tl link` commands

Status: ready
Tier: haiku
Labels: cli
Depends on: P0-I3-T02, T03b, T04 (merged into the base of this branch)
Branch: `p0/i3-t02b-link-cli`

## Goal
`tl link` creates, maintains and lists links from the command line. The group, its options, its helpers (`_fail`, `_service_errors`, `_record`, `_act`), the
`add` and `suggest` commands and the registration in `main.py` exist; `_create`, `list_links` and the five commands `accept`, `decline`, `verify`, `repin`,
`retract`, `flag` in `tl_cli/link.py` raise `NotImplementedError`. A provided test file (13 tests) must pass. (`tl link trace` is added by the supervisor
after the trace query merges; do not write it.)

## Brief references (pasted)
> **7 Links:** typed, directed, first-class links between records, each with a relation, an optional pin to a revision, a lifecycle (suggested, active, stale, broken, retracted) and who or what created them. Links are never deleted; a retraction keeps the history.
> **7.3 Expected links:** a record type may declare links it is expected to have (an NCR is expected to have a supporting record); `list` shows the ones still missing.
> **Build spec:** the CLI contains no business logic. A subcommand parses options, makes one call, prints.

### Specification (the provided test checks it)
`--project ID` means scope `project:<ID>`; the database is `ctx.obj` (set by the root `--db` / `TL_DB`); every command's `source` is `cli`. Records are named by key,
links by the id that `add`, `suggest` and `list` print.
- `_create(ctx, project, from_key, to_key, relation, pin, note, actor, confidence)` (shared by `add`, which passes `confidence=None`, and `suggest`): inside
  `with _service_errors(), open_uow(db) as uow:` find both records with `_record(uow, scope, project, key)`, then build `fields = {"actor": actor, "source": "cli",
  "scope": scope, "from_id": str(source["id"]), "to_id": str(target["id"]), "relation": relation, "pin": pin, "note": note}`. With `confidence is None` call
  `handle_add_link(uow, AddLink(**fields))`, else `handle_suggest_link(uow, SuggestLink(**fields, confidence=confidence))`. After the block print three lines, with
  `event = result.events[0]`: `added <result.stream_id>` (`suggested` for a suggestion), `relation <event.payload['relation']>`, `status active` (`status suggested`).
- `tl link list --project ID KEY [--all]` (`list_links`): inside `with _service_errors(), open_uow(db, readonly=True) as uow:` find the record with `_record`, then
  `views = links_of(uow, str(row["id"]), include_retracted=all_links)` and `missing = missing_expected_links(uow, str(row["id"]))`. Print `key: <key>`; then one line per
  view, fields joined by **two spaces**: `view.direction`, `view.label`, `view.other_key or "—"`, the status (`"declined"` when `view.declined`, else `view.status`),
  `view.pin or "floating"`, `view.link_id`. Then one line per `item` in `missing`: `missing <expectation.display> (rule: <rule>)` where `expectation = item.expectation`
  and `rule = expectation.relation` plus `@<expectation.by_state>` when `by_state` is set.
- The five maintenance commands each call `_act(ctx, project, verb, link_id, run)` where `run` is a `lambda uow, scope: handle_<x>_link(uow, <X>Link(actor=actor,
  source="cli", scope=scope, link_id=link_id, ...))`. `_act` prints `<verb> <link id>` and `version <n>`; do not change it. Verbs and extra fields:
  `accept` -> `accepted`, `note=note` (`AcceptLink`); `decline` -> `declined`, `reason=reason` (`DeclineLink`); `verify` -> `verified`, `note=note` (`VerifyLink`);
  `repin` -> `repinned`, `pin=pin` (`RepinLink`); `retract` -> `retracted`, `reason=reason` (`RetractLink`); `flag` -> `flagged`, `status=cast(Literal["stale", "broken"], status)`,
  `reason=reason` (`FlagLink`; a bad status is rejected by the model and `_service_errors` prints it).
- Failures need no code from you: `_service_errors` prints `error: ...` and exits 1. Do not change the helpers or the options.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- The functions already have their final signatures and option declarations; keep them.
- The stub had its unused imports removed; add back what you use (`links_of`, `missing_expected_links`, the command classes and handlers listed below, `cast`, `Literal`).
- ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Remove the `STUB (P0-I3-T02b)` paragraph from the module docstring when you are done.
- A lambda that builds a pydantic command is fine; keep each one under 100 columns by breaking inside the call.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/link.py (existing stub): app = typer.Typer(...); _DEFAULT_ACTOR = "user:dev"
def _fail(message: str) -> NoReturn
def _service_errors() -> context manager     # service, concurrency and validation errors -> "error: ..." on stderr, exit 1
def _record(uow, scope: str, project: str, key: str) -> dict[str, object]   # the record row (keys id, key, version) or exit 1 "no record with key ..."
def _create(ctx, project, from_key, to_key, relation, pin, note, actor, confidence: float | None) -> None   # TICKET
def list_links(ctx, project, key, all_links: bool = False) -> None                                            # TICKET
def _act(ctx, project: str, verb: str, link_id: str, run: Callable[[UnitOfWork, str], CommandResult]) -> None   # done
def accept / decline / verify / repin / retract / flag (ctx, project, link_id, ..., actor) -> None             # TICKET
```
```python
# existing, import and use
from tl_core.services.link_queries import links_of          # (uow, record_id, *, include_retracted=False) -> list[LinkView]
#   LinkView: .direction ("out"|"in") .label .other_key (str | None) .status .declined (bool) .pin (str | None) .link_id
from tl_core.links.expected import missing_expected_links   # (uow, record_id) -> list[MissingLink]; MissingLink.expectation: .display .relation .by_state (str | None)
from tl_core.services.links import (
    AddLink, SuggestLink, AcceptLink, DeclineLink, VerifyLink, RepinLink, RetractLink, FlagLink,
    handle_add_link, handle_suggest_link, handle_accept_link, handle_decline_link,
    handle_verify_link, handle_repin_link, handle_retract_link, handle_flag_link,
)
# AddLink(Command): from_id, to_id, relation: str | None = None, pin: str | None = None, link_source = "manual", note: str | None = None
# SuggestLink(AddLink): confidence: float | None
# Accept/Verify: link_id, note | Decline/Retract: link_id, reason | Repin: link_id, pin | Flag: link_id, status ("stale"|"broken"), reason
# every handle_* returns CommandResult: .stream_id .version .events[0].payload
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/link.py`
- `packages/tl-cli/src/tl_cli/wf.py` (the same shape of group, finished)
- `docs/tickets/P0-I3/provided/test_cli_link.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/link.py` (edit)
- `packages/tl-cli/tests/test_cli_link.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T02b.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_cli_link.py.txt packages/tl-cli/tests/test_cli_link.py`
2. Implement `_create`, `list_links` and the six maintenance commands; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_link.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_cli_link.py.txt packages/tl-cli/tests/test_cli_link.py
```
Expected: 13 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `main.py`, the services or any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
