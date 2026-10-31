# P2-W0-A3 — `dev/relay-lint`: relay block validator

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tooling, tests
Depends on: —
Branch: `p2/w0-t03-relay-lint`

## Goal
`dev/relay-lint [<file>]` (stdin by default) validates a supervisor reply that ends in a Code 92 relay block and prints
one error line per broken rule, or one `OK` line, so a malformed relay is caught before the orchestrator reads it.

## Brief references (pasted)
> Common rules for A1-A3: bash, `set -euo pipefail`, no network, no Python beyond `uv run` of what exists; exit 0 on
> success, 1 on a finding, 2 on bad usage; every output line <= 160 characters.
> A3 `dev/relay-lint [<file>]` (stdin by default; <= 10 lines of output). Input: a supervisor reply or a file containing
> one. Checks, in order, printing one `E<n> <line no> <reason>` per failure: (1) exactly one `=== RELAY ===` ...
> `=== END ===` block, and it is the last thing in the text; (2) prose before the block <= 8 lines; (3) the first line
> inside the block matches `^(19|88|2) [A-Z0-9-]+ r[0-9]+ base@[0-9a-f]{7,} ck[01] g[01-] st@[0-9a-f]{7,} C[0-9]$`;
> (4) with `19`, at least one item line `^[A-Za-z0-9-]+ docs/tickets/\S+ \S+ [tp] [lf]$` and every item path exists; with
> `88` or `2`, no item lines; (5) exactly one line each of `95 `, `9 `, `4 `, `REPORT `, `NOTE `, in that order, each
> <= 160 characters; with `88`, `REPORT` names an existing file; (6) the line before `=== END ===` is `30`; (7) no model
> name (opus, sonnet, haiku, gpt, claude) outside the block's `NOTE` line. Exit 0 and print
> `OK <state> <INC> r<n> <n items>` when clean (`<n items>` = `<n> items`).
> Deviation from the original brief (supervisor decision): the item id class includes `-` because wave-0 ids are
> `RM-S1`, `W0-B1`.

## Interfaces
A clean relay block (the lines between the markers; the ticket path must exist in the repo):
```
=== RELAY ===
19 P2-W0 r1 base@0a69e0a ck0 g- st@8c87aab C0
T01 docs/tickets/P2-W0/T01-state-sh.md p2/w0-t01-state-sh t l
95 none
9 none
4 none
REPORT none
NOTE acc: just check
30
=== END ===
```
The same block is in `docs/tickets/P2-W0/provided/relay-ok.txt` (expected: `OK 19 P2-W0 r1 1 items`); a broken one
(no `30` line) is in `provided/relay-bad.txt` (expected: an `E6` line, exit 1). These two files are fixed; do not edit them.

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `docs/tickets/P2-W0/provided/relay-ok.txt`, `docs/tickets/P2-W0/provided/relay-bad.txt`
- `dev/gate.sh` (house style for a bash tool)
- `tests/tools/test_no_sqlite_imports.py` (house style for a tests/tools test)
may explore: (none)

## Allowed paths
- `dev/relay-lint` (create, mode 755, no extension)
- `tests/tools/test_relay_lint.py` (create)
- `docs/reports/P2-W0/A3.md` (create)

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
just check
dev/relay-lint docs/tickets/P2-W0/provided/relay-ok.txt; echo "exit $?"     # OK 19 P2-W0 r1 1 items, exit 0
dev/relay-lint docs/tickets/P2-W0/provided/relay-bad.txt; echo "exit $?"    # an E6 line, exit 1
dev/relay-lint < docs/tickets/P2-W0/provided/relay-ok.txt                   # stdin form, same OK line
```
Expected: as commented. Paste each output in the report.

## Tests to add
- `tests/tools/test_relay_lint.py`: runs the script (via `subprocess`, from the repo root) on three clean blocks (the 19, 88
  and 2 shapes; the 19 block uses a real existing ticket path, the 88 block's `REPORT` names an existing file such as
  `docs/reports/P2-W0/A3.md` created in the test's `tmp_path` working directory or an existing repo file) and six broken
  variants, one per rule 1-6 plus rule 7 (a model name in prose): pins the exact `E<n> <line> <reason>` text and exit codes.
  Reasons are short fixed phrases chosen by the implementer and pinned by the test. The test file is written, not run.

## Report requirements
Standard report plus the pasted smoke outputs and a line saying the test file was not run (deferred).

## Escalation triggers
- Stop and report *Blocked* if a rule cannot be checked without a dependency, or the two provided files do not give the
  stated results with the brief's rules (report which rule disagrees).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
