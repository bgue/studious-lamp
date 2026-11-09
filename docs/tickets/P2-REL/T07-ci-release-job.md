# P2-REL-T07 — CI job `release-smoke` on Linux and macOS

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: ci
Depends on: T05 merged on p2/rel (the owner may cut this ticket)
Branch: `p2/rel-t07-ci`
Wave 2: no

## Goal
`.github/workflows/ci.yml` gets a job `release-smoke` (matrix `ubuntu-latest`, `macos-latest`; Python 3.12; `astral-sh/setup-uv` as the
other jobs): `just release-build`, `just release-starter`, `dev/release/smoke.sh dist/release-<version>`. The Postgres step runs on the Linux
leg only (service container as in `check-and-test`). Triggers: `push` to main and the nightly schedule only, not every PR. This is what makes
the macOS claim in "supported" testable.

## Requirements
Follow the existing job's header comments and `permissions`. GitHub Actions cannot run here: parse the YAML with `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` and say in the report that the job was not executed. `just` may be missing on the macOS runner: install it with the action or step the existing jobs use, copied, not invented.

## Context (read these, nothing else)
- `.github/workflows/ci.yml` (all), `dev/release/smoke.sh` (usage line)
may explore: none

## Allowed paths
- `.github/workflows/ci.yml`
- `docs/reports/P2-REL/T07.md`

## Acceptance
```
just check
```
Expected: exit 0 and the YAML parse prints nothing; report marks the job "not executed here".

## Escalation triggers
Stop and report *Blocked* if the other jobs show no way to install `just` on macOS.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
