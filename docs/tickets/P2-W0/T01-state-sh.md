# P2-W0-A1 — `dev/state.sh`: one-call increment state

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tooling, tests
Depends on: —
Branch: `p2/w0-t01-state-sh`

## Goal
`bash dev/state.sh <INC> [<base>]` prints an increment's STATE.md header, board, recent commits, open worktrees,
unmerged ticket branches and NEXT list in at most 40 lines, so a supervisor or the orchestrator reads one short
output instead of making a dozen calls. A test file pins the output on a fixture git repository.

## Brief references (pasted)
> Common rules for A1-A3: bash, `set -euo pipefail`, no network, no Python beyond `uv run` of what exists; exit 0 on
> success, 1 on a finding, 2 on bad usage; every output line <= 160 characters.
> A1 `dev/state.sh <INC> [<base>]` (<= 40 lines of output). Inputs: increment id; optional base ref (default: the
> `base=` field of `docs/tickets/<INC>/STATE.md`, else the trunk). Reads: STATE.md, `git log --oneline <base>..HEAD` of
> the increment branch, `git worktree list`, `git branch --list '<branch>-*'`. Output, in order, each section opened by
> a line holding only its name: (1) the STATE.md header line verbatim (line 1, no section name line);
> (2) `BOARD` lines verbatim (the lines under `## BOARD`), at most 15 (`+n more` when cut); (3) `LOG` commits since base,
> at most 10, `<sha7> <subject cut to 60>`; (4) `WT` open worktrees under the worktree root whose branch starts with the
> increment branch, `<path> <branch> <head sha7> <clean|dirty>`; (5) `HEADS` ticket branches not merged into the
> increment branch, `<branch> <sha7>`; (6) `NEXT` lines verbatim (under `## NEXT`). A missing STATE.md prints
> `STATE none` and exits 1. Total <= 40 lines.
> Decisions (supervisor, this ticket only): the increment branch is the INC id lower-cased with its first `-` replaced
> by `/` (`P2-W0` -> `p2/w0`); the worktree root is `${WT_ROOT:-/home/user/wt}` (so the test can use a temp dir);
> the base ref in the STATE.md header is the token after `base=` and may be a sha or a branch name.

## Interfaces
STATE.md header line shape (line 1): `# P2-W0 STATE  r=1 base=abc1234 C=C0 ck=0 gate=n/a wt=/home/user/wt/p2-w0`
followed by `## BOARD`, `## DEC`, `## SEC`, `## OPEN`, `## NEXT`, `## REFS`, `## TRAPS` sections.

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `docs/tickets/P2-W0/STATE.md` (the real file the smoke command reads)
- `dev/gate.sh` (house style for a bash tool)
- `tests/tools/test_no_sqlite_imports.py` (house style for a tests/tools test)
may explore: (none)

## Allowed paths
- `dev/state.sh` (create, mode 755)
- `tests/tools/test_state.py` (create)
- `docs/reports/P2-W0/A1.md` (create)

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
just check
bash dev/state.sh P2-W0 | wc -l          # <= 40
bash dev/state.sh P2-W0 | head -1        # equals line 1 of docs/tickets/P2-W0/STATE.md
bash dev/state.sh NOPE; echo "exit $?"   # prints "STATE none", exit 1
```
Expected: `just check` clean; the three smoke outputs as described. Paste each output in the report.

## Tests to add
- `tests/tools/test_state.py`: builds in `tmp_path` a fixture repo (git init, 3 commits on branch `p9/x1`, a STATE.md at
  `docs/tickets/P9-X1/STATE.md` with a header, 2 board lines, 1 NEXT line, `base=` set to the first commit, two ticket
  branches `p9/x1-t01-a` and `p9/x1-t02-b` where only one is merged, one `git worktree add` under a temp `WT_ROOT`),
  runs `bash dev/state.sh P9-X1` there with `WT_ROOT` set, and pins the whole output (shas taken from `git rev-parse
  --short=7`). Also: missing STATE.md -> `STATE none`, exit 1; more than 15 board lines -> `+n more`; output <= 40 lines.
  The test file is written, not run.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus the pasted smoke outputs and a line saying the test file was not run (deferred).

## Escalation triggers
- Stop and report *Blocked* if the STATE.md format cannot be parsed with bash/sed/awk alone, or a smoke output exceeds 40 lines.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
