# P2-INT-T02 — CLI `--why`, `--next`, `--toward` (and `--goal-ref`) on write commands (record, link)

Status: ready (S2 merged at 0fc06f1; provided test committed r3)
Tier: haiku
Review: full
Labels: cli
Depends on: S2 merged
Branch: `p2/int-t02-cli-intent-flags`

## Goal
A person at the shell can give the reason with the action. After this ticket `tl record create|void` and `tl link add|retract` accept four options, validate them with the one S2 function and store them on the events the command appends; nothing else about any command changes.

## Brief references (pasted)
> ADR-0025 d1: `why` plain text at most 500 characters; `next` zero to 5 items, each `{command, target}` or `{text}`; `toward` `{target, state}` or `{target, condition}`; `goal_ref` at most 64 chars of `a-z0-9-_`. "Soon: CLI `--why`, `--next`, `--toward`."
> Surface text (S2 owns the server checks; the CLI only builds the body and shows the server's code): `--next` repeatable: `command:target` (both given) or `text:<words>`; `--toward target:state` or `target:~condition text`.

## Interfaces
Drift found at r3: the CLI builds no request body. Every write command calls `handle_*(uow, Command(...))` itself (about 440 sites), without the API dispatcher, so neither the S2 check nor the carrier runs there. There is no single write point. Decision D6: the options go on the `record` and `link` write commands only (the demo path); other groups follow in a later ticket. Allowed edits: `record.py` (`create`, `void`), `link.py` (`add`, `retract`) and the new module. More than these two command files: stop.
```python
# tl_cli/intent_flags.py (create; provided test packages/tl-cli/tests/test_intent_flags.py, committed)
def parse_intent_flags(why: str | None, next_items: Sequence[str], toward: str | None, goal_ref: str | None) -> dict[str, Any] | None
# nothing given (empty why counts as none) -> None; result keys why, next, toward, goal_ref as Intent.model_validate takes them.
# --next: "text:<words>" -> {"text"}; "command:target" (split at the first colon, both non-empty) -> {"command","target"}; else click.UsageError(f"--next {item!r}: expected command:target or text:<words>")
# --toward: "target:state" -> {"target","state"}; "target:~condition" -> {"target","condition"}; else click.UsageError(f"--toward {value!r}: expected target:state or target:~condition")

# same module: the write wrapper (the same two calls the API dispatcher makes, tl_api/commands.py run_command)
def run_with_intent(uow: UnitOfWork, command: C, handler: Callable[[UnitOfWork, C], R], intent: dict[str, Any] | None) -> R
# intent None -> handler(uow, command). Else: command = command.model_copy(update={"intent": Intent.model_validate(intent)});
# command = check_intent(command, uow.conn(), viewer_for_actor(uow.conn(), command.actor));  with intent_scope(command.intent): return handler(uow, command)
# IntentInvalid / IntentReferenceUnknown propagate to the group's `_service_errors` and print as `error: <fixed text>`, exit 1.
```
Options (shared `Annotated` aliases in the same module, applied to the four commands): `--why TEXT`, `--next TEXT` (repeatable), `--toward TEXT`, `--goal-ref TEXT`. Help text says intent is recorded with the event and read by nobody to decide anything. Command names for `--next` resolve through `tl_core.intent` (core table plus module index); the CLI registers nothing extra.
`tl events` shows stored events without the viewer redaction the API applies (operator tool, S2 report); this ticket does not change it. Say so in the report and in the `tl events --help` text if that help names fields; otherwise report only.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/record.py`, `link.py` (one command each as the pattern), `tl_core/intent.py` (`check_intent`, `intent_scope`, errors), `tl_core/confidentiality.py` (`viewer_for_actor`)
- `docs/tickets/P2-INT/S2-intent-boundary.md` (error codes), `docs/reports/P2-INT/S2.md`
may explore: `packages/tl-cli/tests/test_cli_link.py` for the CLI write test pattern (`lnk(env, ...)`).

## Allowed paths
- `packages/tl-cli/src/tl_cli/intent_flags.py` (create), `record.py` and `link.py` (option and wrapper lines only), `packages/tl-cli/tests/test_intent_flags.py` (provided, committed), `packages/tl-cli/tests/test_intent_cli.py` (create), `docs/reports/P2-INT/T02.md` (create)
Consequential pins (rule 12): CLI help snapshots that break only for the new options are updated and listed.

## Acceptance
```
just check
just gate packages/tl-cli/tests/test_intent_flags.py packages/tl-cli/tests/test_intent_cli.py packages/tl-cli/tests/test_cli_link.py packages/tl-cli/tests/test_cli_e2e.py packages/tl-cli/tests/test_cli_numbering.py
```

## Tests to add
`test_intent_cli.py`: `record create --why x --toward <key>:~released` appends an event whose `intent` column holds the canonical JSON (ids, not keys); without options the column is NULL; `--toward` naming an unknown key and a key the actor cannot read print the same `error:` text, exit 1, and append nothing; `link add --why` carries it on the link event; a too-long `--why` is refused before any event.

## Report requirements
Standard plus the list of pins updated.

## Escalation triggers
- Stop and report *Blocked* if more than `record.py` and `link.py` need edits, or if an error text would echo the intent.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
