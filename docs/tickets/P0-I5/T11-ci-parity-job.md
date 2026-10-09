# P0-I5-T11 — CI job that runs the parity suite against a Postgres service container

Status: ready
Tier: haiku
Labels: ci, tests
Depends on: —
Branch: `p0/i5a-t11-ci-parity-job`

## Goal
Every pull request runs `just test-parity` against a real PostgreSQL 16 service container, so the Postgres adapter is gated in CI and not only on a
developer machine (`docs/build-spec/04-gates.md` §1: parity is a merge gate when `packages/tl-adapters/**` or `tl_core/ledger/**` changed). A second
test file checks the workflow file so the job cannot be deleted by accident.

## Brief references (pasted)
> **04 §1 CI gates.** Parity (SQLite + Postgres): `just test-parity`; blocks merge when `packages/tl-adapters/**` or `tl_core/ledger/**` changed;
> nightly otherwise. Owner when red: supervisor.
>
> **ADR-0002 §3.** Postgres parity runs against the native cluster locally. Connection string via `TL_PG_URL`, default
> `postgresql://postgres:postgres@localhost:5432/tl_test`. CI uses a service container.
>
> **How `just test-parity` behaves (already implemented).** It runs `just dev up`, exports `TL_REQUIRE_POSTGRES=1` (an unreachable Postgres is a
> failure, never a skip) and `TL_PG_URL` (default above), then `pytest -m "parity or requires_postgres" --adapters sqlite,postgres`.
> The pytest fixtures create a throw-away database on that server per test session and a schema per test.

## Interfaces (verbatim from the repo at the branch point)
```yaml
# .github/workflows/ci.yml (current content; keep the existing job exactly as it is)
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  check-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: extractions/setup-just@v2
      - run: uv sync --all-packages
      - run: just check
      - run: just test
```
```
# the job to add under `jobs:` (second job, same indentation as check-and-test)
  parity:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: tl_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      TL_PG_URL: postgresql://postgres:postgres@localhost:5432/tl_test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: extractions/setup-just@v2
      - run: uv sync --all-packages
      - run: just test-parity
```

## Context (read these, nothing else)
- `AGENTS.md`
- `.github/workflows/ci.yml`
- `justfile`
may explore: (none)

## Allowed paths
- `.github/workflows/ci.yml` (edit)
- `tests/ci/test_ci_workflow.py` (create)
- `docs/reports/P0-I5/P0-I5-T11.md` (create: your report; commit it)

## Steps
1. Add the `parity` job exactly as pasted. Do not change `check-and-test`, the triggers, or the action versions.
2. Write `tests/ci/test_ci_workflow.py` (see *Tests to add*).
3. Run the acceptance commands, write the report, commit.

## Acceptance
```
just check
uv run pytest tests/ci -q
uv run python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/ci.yml')); print(sorted(d['jobs']))"
```
Expected: `just check` clean; `3 passed` (or the number of tests you wrote, at least 3); the last command prints `['check-and-test', 'parity']`.

## Tests to add
`tests/ci/test_ci_workflow.py` (use `yaml.safe_load`; the path is `Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"`; annotate everything):
1. `test_the_parity_job_exists_and_runs_the_parity_recipe`: job `parity` has a step whose `run` is exactly `just test-parity`.
2. `test_the_parity_job_has_a_postgres_16_service_and_the_url`: `services.postgres.image == "postgres:16"`, the job `env` has `TL_PG_URL` starting with
   `postgresql://` and ending with `/tl_test`, and `POSTGRES_DB` is `tl_test`.
3. `test_the_existing_job_still_checks_and_tests`: `check-and-test` still has the steps `just check` and `just test`.
Note: PyYAML parses the key `on:` as the boolean `True`; do not assert on the trigger block.

## Report requirements
Standard report plus the output of the three acceptance commands.

## Escalation triggers
- `yaml` cannot be imported in the test: write *Blocked*; do not add a dependency.
- You think the job needs more than the pasted lines (a different Postgres image, extra services): write *Blocked*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
