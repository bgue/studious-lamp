# P2-INT-T02 — CLI `--why`, `--next`, `--toward` (and `--goal-ref`) on write commands

Status: staged (release after S2 merged; the provided test is committed in that round)
Tier: haiku
Review: full
Labels: cli
Depends on: S2 merged
Branch: `p2/int-t02-cli-intent-flags`

## Goal
A person at the shell can give the reason with the action. After this ticket the shared CLI write path accepts four options and sends them as the command body's `intent`; nothing else about any command changes.

## Brief references (pasted)
> ADR-0025 d1: `why` plain text at most 500 characters; `next` zero to 5 items, each `{command, target}` or `{text}`; `toward` `{target, state}` or `{target, condition}`; `goal_ref` at most 64 chars of `a-z0-9-_`. "Soon: CLI `--why`, `--next`, `--toward`."
> Surface text (S2 owns the server checks; the CLI only builds the body and shows the server's code): `--next` repeatable: `command:target` (both given) or `text:<words>`; `--toward target:state` or `target:~condition text`.

## Interfaces
```python
# tl_cli/intent_flags.py (create; pure function, provided test packages/tl-cli/tests/test_intent_flags.py)
def parse_intent_flags(why: str | None, next_items: Sequence[str], toward: str | None, goal_ref: str | None) -> dict[str, Any] | None
# no option given -> None (the body has no `intent` key); `next:` shapes above; a malformed item raises UsageError(f"--next {item!r}: expected command:target or text:<words>")
```
Wiring: one shared option group applied where the CLI builds a write command's request body (find the one function; do NOT edit each command file). If the write path has no single point and more than 3 command files need editing, stop (Escalation).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/` the module that builds and sends a write command body (find with `grep -rn "effective_at\|command_body" packages/tl-cli/src`), `actor_hook.py`
- `docs/tickets/P2-INT/S2-intent-boundary.md` (Interfaces: body field `intent`, error codes)
may explore: `packages/tl-cli/tests/` for a CLI write test pattern.

## Allowed paths
- `packages/tl-cli/src/tl_cli/intent_flags.py` (create), the one shared write-path module found above, `packages/tl-cli/tests/test_intent_flags.py` (provided, create), `packages/tl-cli/tests/test_intent_cli.py` (create), `docs/reference/` CLI page line for the four options, `docs/reports/P2-INT/T02.md` (create)
Consequential pins (rule 12): CLI help snapshots that break only for the new options are updated and listed.

## Acceptance
```
just check
just gate packages/tl-cli/tests
```

## Tests to add
`test_intent_cli.py`: one write command with `--why x --toward WP-1:~released` sends a body with `intent`; without options, no key; server code `intent_invalid` is printed as its fixed text, exit non-zero.

## Report requirements
Standard plus the list of pins updated.

## Escalation triggers
- Stop and report *Blocked* if the write path has no single body-building point, or if a server error text would echo the intent.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
