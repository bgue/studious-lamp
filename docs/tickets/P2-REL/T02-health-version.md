# P2-REL-T02 — Server version in `/health`; the TUI warns on a different minor

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: api, tui
Depends on: S2 merged on p2/rel
Branch: `p2/rel-t02-health-version`
Wave 2: no

## Goal
`GET /health` answers `{"status":"ok","version":"0.1.0"}` (the version from package metadata). When the TUI signs in to a
server whose `major.minor` differs from its own, the sign-in screen shows a plain line, `server is 0.2.x, this app is 0.1.x:
not a supported pair`, and still lets the person continue. Interface line for the orchestrator: `/health` adds a field
(additive; regenerate the OpenAPI document with the repository's recipe and commit it).

## Requirements
1. `/health` stays open (no auth) and cheap; the field is a plain string; nothing else is added (no host, no database name).
2. `tl_api.client` gets `health()` returning the parsed body if no method exists; the TUI sign-in reads it once, before the
   prompt, in `RemoteAuthenticator` or `sign_in_first` (one call; a failure to read it shows nothing and never blocks sign-in).
3. A pure function `version_pair_note(server: str | None, app: str) -> str | None` (compares `major.minor`; `None` when equal or the
   server is unknown) with its own tests; the screen only displays what it returns (no logic in the TUI, AGENTS "Never").
4. Existing `/health` pins in tests are updated and listed (rule 12).

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/auth.py` line 169 (`OPEN_PATHS`) and the route that serves `/health` (grep `"/health"`)
- `packages/tl-tui/src/tl_tui/remote.py` (`RemoteAuthenticator`), `packages/tl-tui/src/tl_tui/main.py` (`sign_in_first`, `plain_http_warning`)
- `packages/tl-tui/src/tl_tui/sign_in.py` (where `hint` is shown)
- the OpenAPI drift recipe: `grep -n openapi justfile`
may explore: none

## Allowed paths
- the `/health` route file and its test, the generated OpenAPI document (regenerated only)
- `packages/tl-api/src/tl_api/client/` (one `health` method, only if missing), `packages/tl-tui/src/tl_tui/{remote,main,sign_in}.py`
- `packages/tl-tui/src/tl_tui/version_note.py` (create), `packages/tl-tui/tests/test_version_note.py` (create), `packages/tl-api/tests/test_health_version.py` (create)
- `docs/reports/P2-REL/T02.md`

## Acceptance
```
just check
just gate packages/tl-api/tests packages/tl-tui/tests
```
Expected: `gate: PASS`, `just check` reports no OpenAPI drift.

## Tests to add
`version_pair_note` table (equal, patch differs, minor differs, major differs, None, non-numeric); `/health` JSON; the sign-in
screen shows the line for a mismatched fake server and nothing for a matching one.

## Escalation triggers
Stop and report *Blocked* if the sign-in flow needs a new route, or `/health` is behind auth somewhere.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
