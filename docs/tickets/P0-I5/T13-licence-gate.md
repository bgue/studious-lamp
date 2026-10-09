# P0-I5-T13 — Licence gate in `just check`

Status: ready
Tier: haiku
Labels: tooling, tests
Depends on: —
Branch: `p0/i5a-t13-licence-gate`

## Goal
`just check` fails when any installed Python distribution is GPL, LGPL or AGPL, has no declared licence, or is MPL-2.0 without being on the allow-list
(`docs/adr/0006-dependency-licences.md`, decision 3). The script is a small stdlib-only module with a provided test; you write the bodies of six
functions and wire one line into the `check` recipe.

## Brief references (pasted)
> **04 §2 Human gates.** "New dependency with copyleft or unclear licence": approver is a human; recorded in an ADR.
>
> **ADR-0006 decisions.** (1) GPL, LGPL and AGPL dependencies are refused, direct or transitive. (2) MPL-2.0 packages are allowed when they are transitive and
> unmodified; the allow-list is `certifi`, `tqdm`, `fqdn`, `hypothesis` (the owner confirmed this). (3) A licence check becomes part of the gates: a script fails
> `just check` on any GPL, LGPL or AGPL distribution and on a missing licence, and lists MPL-2.0 packages against the allow-list. The workspace's own `tl-*`
> packages are exempt.

## Interfaces (verbatim from the repo at the branch point)
`dev/tools/check_licences.py` is a stub: the constants, `Dist` and the signatures are final, the six bodies raise `NotImplementedError`. Its docstrings are the
specification of each function. The stub had its unused import removed: add `import importlib.metadata as metadata` back when you write `collect()`.
```python
# dev/tools/check_licences.py (the parts you must not change)
MPL_ALLOWED = frozenset({"certifi", "tqdm", "fqdn", "hypothesis"})
EXEMPT_PREFIX = "tl-"
COPYLEFT = re.compile(r"gpl|general public|affero|lesser general", re.IGNORECASE)
MPL = re.compile(r"\bmpl\b|mpl-|mozilla public", re.IGNORECASE)
PERMISSIVE = re.compile(...)   # as in the file
SHORT = 120
class Dist(NamedTuple):
    name: str
    expression: str            # License-Expression header, or ""
    license: str               # License header, or ""
    classifiers: tuple[str, ...]   # the "License :: ..." classifiers

def collect() -> list[Dist]: ...
def term_ok(term: str, name: str) -> bool: ...
def statement_ok(statement: str, name: str) -> bool: ...
def statements(dist: Dist) -> list[str]: ...
def problems(dists: Iterable[Dist]) -> list[str]: ...
def main() -> int: ...
```
```
# justfile: the current `check` recipe (add one line at the end)
check:
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run python -m tl_schema.generate --check
```

## Context (read these, nothing else)
- `AGENTS.md`
- `dev/tools/check_licences.py`
- `docs/tickets/P0-I5/provided/test_check_licences.py.txt`
- `justfile`
- `docs/adr/0006-dependency-licences.md`
may explore: (none)

## Allowed paths
- `dev/tools/check_licences.py` (edit)
- `tests/tools/test_check_licences.py` (create: byte-for-byte copy of the provided file)
- `justfile` (edit: one line in `check`)
- `docs/reports/P0-I5/P0-I5-T13.md` (create: your report; commit it)

## Steps
1. `mkdir -p tests/tools && cp docs/tickets/P0-I5/provided/test_check_licences.py.txt tests/tools/test_check_licences.py`. Do not edit the copy.
2. Write the six bodies from their docstrings; delete the `STUB (P0-I5-T13)` paragraph from the module docstring; add the `importlib.metadata` import.
3. Add `uv run python dev/tools/check_licences.py` as the last line of the `check` recipe.
4. `uv run ruff format dev tests/tools`, run the acceptance commands, write the report, commit.

## Acceptance
```
just check
uv run pytest tests/tools -q
uv run python dev/tools/check_licences.py
git diff --stat p0/i5a -- . ':!docs/reports'
```
Expected: `just check` clean and ends with `licences ok` (do not pipe it); `22 passed`; the third command prints `licences ok` and exits 0; the diff stat lists only the
files in *Allowed paths*. If the third command prints a problem for an installed distribution, do not change the rules or the allow-list: write it under *Blocked*.

## Tests to add
None beyond the provided file (12 test functions, 22 cases).

## Report requirements
Standard report plus the output of `uv run python dev/tools/check_licences.py` and of `just check`.

## Escalation triggers
- The gate reports a real distribution as a problem: *Blocked* with the line it printed.
- A rule in the docstrings contradicts the provided test: *Blocked*; do not change the test.
- You think a dependency is needed: no. It is stdlib only.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
