# P2-W0-A2 — `dev/review-pack.sh`: one-call review pack

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tooling, tests
Depends on: —
Branch: `p2/w0-t02-review-pack`

## Goal
`bash dev/review-pack.sh <base> <branch> [<ticket path>]` prints, in at most 60 lines, what a reviewer needs from a
branch: diffstat, changed symbols, paths outside the ticket's Allowed paths, tests present or missing, commit format
and the last gate line, so the reviewer reads one output instead of the whole diff.

## Brief references (pasted)
> Common rules for A1-A3: bash, `set -euo pipefail`, no network, no Python beyond `uv run` of what exists; exit 0 on
> success, 1 on a finding, 2 on bad usage; every output line <= 160 characters.
> A2 `dev/review-pack.sh <base> <branch> [<ticket path>]` (<= 60 lines). Inputs: base ref, branch, optional ticket or
> piece spec path (default: found from the branch name, see decision below). Output, each section opened by a line holding
> only its name, in order: (1) `DIFFSTAT` of `git diff --stat <base>...<branch>`, at most 20 lines; (2) `SYMBOLS`
> changed Python symbols: `def`/`class` names added, removed or whose body changed, `<file>:<name> <+|-|~>`, at most 20;
> (3) `PATHS` every changed path not matched by the ticket's *Allowed paths* globs (`OK` when none; the report path
> `docs/reports/<INC>/<id>.md` is always allowed); (4) `TESTS` for every path under *Tests to add*: `present|missing`,
> and for every file under `docs/tickets/<INC>/provided/` named in the ticket: `cmp same|differs <target>`;
> (5) `COMMITS` `<sha7> <subject>` since base, with `BAD-MSG` on any subject not matching `^<id>: ` and `MODEL-NAME` on
> any body line outside the trailer (`Co-Authored-By:` and `Claude-Session:` lines) that names a model (a word such as
> opus, sonnet, haiku, claude, gpt); (6) `GATE` the last line of `.gate/summary.txt` on the branch's worktree
> (`gate: PASS|FAIL`), or `g-`. Exit 1 if any PATHS, missing TESTS, `differs`, `BAD-MSG` or `MODEL-NAME` line was printed.
> Decisions (supervisor, this ticket only): a ticket path is optional; when absent it is looked up as
> `docs/tickets/<INC>/<ID>-*.md` where INC is the branch's first path part and the part before the first `-` of its
> second part, upper-cased and joined with `-` (`p2/w0-t01-x` -> `P2-W0`), and ID is the next token upper-cased (`T01`);
> not found prints `TICKET none` under PATHS and TESTS and those sections are skipped without failing. The `<id>` for
> `BAD-MSG` is the first token after `# ` on the ticket's first line (`P2-W0-A1`); with no ticket, skip BAD-MSG. Allowed paths = the backticked
> paths/globs in bullets under the ticket's `## Allowed paths` heading; Tests to add = backticked paths in bullets under
> `## Tests to add`; a provided-test mapping is a bullet containing two backticked paths joined by `->` (`provided` file
> `->` target). The worktree for GATE is found with `git worktree list` by branch; none -> `g-`.

## Interfaces
Ticket sections it parses: `## Allowed paths`, `## Tests to add` (see `docs/templates/haiku-ticket.md`).

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`, `docs/templates/haiku-ticket.md`
- `docs/tickets/P2-W0/T01-state-sh.md` (a real ticket the smoke command reads)
- `dev/gate.sh` (house style for a bash tool)
- `tests/tools/test_no_sqlite_imports.py` (house style for a tests/tools test)
may explore: (none)

## Allowed paths
- `dev/review-pack.sh` (create, mode 755)
- `tests/tools/test_review_pack.py` (create)
- `docs/reports/P2-W0/A2.md` (create)

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
just check
bash dev/review-pack.sh HEAD~1 HEAD docs/tickets/P2-W0/T01-state-sh.md | wc -l    # <= 60
bash dev/review-pack.sh HEAD~1 HEAD docs/tickets/P2-W0/T01-state-sh.md | grep -c '^[A-Z]*$'   # 6 section names
```
Expected: `just check` clean; at most 60 lines; six section-name lines. Exit 1 is allowed for the smoke runs (the last commit
is not that ticket's work); paste each output.

## Tests to add
- `tests/tools/test_review_pack.py`: builds a fixture repo in `tmp_path` (base commit; a branch `p9/x1-t01-a` with a ticket
  file `docs/tickets/P9-X1/T01-a.md` (first line `# P9-X1-T01 — a`) declaring Allowed paths `src/a.py` and Tests to add `tests/test_a.py` plus a mapping
  `docs/tickets/P9-X1/provided/test_a.py` -> `tests/test_a.py`; one commit that changes `src/a.py`, an out-of-boundary
  `src/b.py`, and a `tests/test_a.py` that differs from the provided copy; one commit subject without the ticket's `# P9-X1-T01` id as prefix),
  runs the script and pins the exact output and exit 1: `PATHS` names `src/b.py`; `TESTS` shows `differs`; `COMMITS` shows
  `BAD-MSG`. A clean fixture prints `OK` under PATHS and exits 0. The test file is written, not run.

## Report requirements
Standard report plus the pasted smoke outputs and a line saying the test file was not run (deferred).

## Escalation triggers
- Stop and report *Blocked* if SYMBOLS cannot be produced with git, grep and awk alone (no new dependency); a simple
  `git diff -U0` function-name heuristic over `def`/`class` lines is acceptable and should be named in the report.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
