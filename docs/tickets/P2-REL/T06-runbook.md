# P2-REL-T06 — Runbook `terminal-release.md` and the links to it

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: T05 merged on p2/rel; wave 2 merged on the trunk
Branch: `p2/rel-t06-runbook`
Wave 2: **yes**

## Goal
`docs/runbooks/terminal-release.md` lets a person install, try, deploy and connect with no checkout. Plain English; the shape of
`docs/templates/runbook.md`; every step has an "Expected" line copied from a real run of T05's smoke script or the commands in it,
not invented. Load the `throughline-docs` skill first.

## Sections (each short; commands in code blocks)
1. **What is supported** (copy the table of `docs/tickets/P2-REL/README.md`, owner's answer to R-1 if it changed; the "Not supported" row stays).
2. **Install**: `uv tool install tl-cli --find-links <release dir or URL>`; verify with `--version` and `SHA256SUMS`; upgrade (`uv tool upgrade`); uninstall; Python 3.12 note; WSL2 note.
3. **Try it on the demo project**: the starter bundle, `START.txt`, loopback, `tl serve` + `tl-tui --remote`, the demo account, "never on a shared host", reset = unpack again.
4. **A real server** (deployer): Postgres 16 database, `tl init`, `tl admin bootstrap`, `TL_ENV=prod`, `TL_OBJECT_SECRET`, `TL_DB` in the environment (never the URL on a command line), bind and proxy (`TL_TRUSTED_PROXY_HEADER`, a TLS proxy the deployer runs: one generic example in prose, no vendor config), rate limit and TLS duties from ADR-0009 section "deployment duties" (cite it), first account per person (`tl admin user add`), disable `demo`, back up (`docs/runbooks/sqlite-backup-and-litestream.md`, `pgbackrest-restore.md` pointers).
5. **Connect as a user**: `tl-tui --remote https://...`, sign-in screen, what the version warning means (T02), `TL_REMOTE`, `TL_PROJECT`, session lifetime 12 h, sign-out, forgotten password (an admin resets it).
6. **The CLI is an operator tool** (Q-REL2): needs the ledger; where to run it; `tl login` signs in to a ledger, not a server.
7. **Troubleshooting**: cannot reach the server; plain-http refusal and `TL_ALLOW_PLAIN_HTTP=1` (dev only); locked out; terminal too small or no colour; mismatch warning; `error: not signed in`.
8. **Release checklist for whoever cuts it**: `set_version.sh`, `just release-build`, `check_wheels.py`, `just release-starter`, `smoke.sh`, one person on a named terminal and on WSL2, publish the directory and sums.

## Context (read these, nothing else)
- `docs/tickets/P2-REL/README.md`, `docs/tickets/P2-REL/S2-real-server-mode.md` (requirements 1–5), `docs/runbooks/accounts-and-access.md`, `docs/runbooks/tui-dev.md` steps 5 and following, `docs/runbooks/demo-project.md` section 2
- `dev/release/smoke.sh`, `dev/release/starter.sh` (the real commands and outputs)
- `docs/templates/runbook.md`, `docs/runbooks/README.md`
may explore: none

## Allowed paths
- `docs/runbooks/terminal-release.md` (create), `docs/runbooks/README.md` (one index row), `docs/runbooks/tui-dev.md` (one pointer line), `README.md` (one line), `packages/tl-tui/README.md` and `packages/tl-cli/README.md` (one line each: install and `--version`)
- `docs/reports/P2-REL/T06.md`

## Acceptance
```
just check
```
Expected: exit 0 (links and lint); `grep -c "Expected" docs/runbooks/terminal-release.md` is at least 8. The report lists every command taken from a real run and any that you could not verify (those are marked `(unverified)` in the runbook).

## Escalation triggers
Stop and report *Blocked* if a command in the smoke script does not behave as the runbook needs, or the owner's R-1 answer contradicts the table.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
