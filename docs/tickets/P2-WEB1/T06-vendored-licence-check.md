# P2-WEB1-T06 — Licence check reads the vendored-files manifest

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tools, licences
Depends on: none (the manifest format is pasted below; S1 creates the real manifest)
Branch: `p2/web1-t06-vendored-licence`

## Goal
`dev/tools/check_licences.py` (part of `just check`) also checks vendored JavaScript. It finds every `VENDORED.toml` under a package's `static/vendor/` directory and
fails when a file listed there is missing, has a different sha256, is missing a manifest field, or carries a licence that `statement_ok` refuses (copyleft or unrecognised).
No manifest in the tree is fine (the check passes). The output for installed Python distributions does not change.

## Brief references (pasted)
> Manifest format (`packages/tl-web/src/tl_web/static/vendor/VENDORED.toml`, one `[[file]]` table per vendored file; `path` is relative to the directory holding the manifest):
> ```toml
> [[file]]
> path = "htmx/htmx.min.js"
> name = "htmx"
> version = "2.0.4"
> licence = "BSD-2-Clause"
> url = "https://registry.npmjs.org/htmx.org/-/htmx.org-2.0.4.tgz"
> sha256 = "<64 hex characters>"
> ```
> Policy: any new JS or Python dependency must be permissive; copyleft is a stop (human gate, `04-gates.md` §2; ADR-0006).

## Interfaces (verbatim from repo at the branch point)
```python
# dev/tools/check_licences.py (existing)
def statement_ok(statement: str, name: str) -> bool: ...   # permissive/MPL/copyleft decision for one licence statement
def problems(dists: Iterable[Dist]) -> list[str]: ...        # one line per refused distribution
def main() -> int:
    lines = problems(collect())
    for line in lines:
        print(line)
    if lines:
        print(f"{len(lines)} licence problem(s); see docs/adr/0006-dependency-licences.md")
        return 1
    print("licences ok")
    return 0
```
New, to write in the same file (stdlib only: `tomllib`, `hashlib`, `pathlib`):
```python
MANIFEST_GLOB = "packages/*/src/*/static/vendor/VENDORED.toml"
REQUIRED = ("path", "name", "version", "licence", "url", "sha256")
def find_manifests(root: Path) -> list[Path]: ...            # sorted(root.glob(MANIFEST_GLOB))
def vendored_problems(manifest: Path) -> list[str]: ...      # lines below, in file order
```
`vendored_problems` line texts (exact; `<name>` is the entry's `name`, or its `path`, or `?` when neither exists):
`vendored <name>: missing field <key>` (one per missing key, then skip that entry's other checks) | `vendored <name>: file not found (<path>)` |
`vendored <name>: sha256 mismatch (<path>)` | `vendored <name>: licence not allowed (<licence>)` (when `statement_ok(licence, name)` is false) |
`vendored <manifest path relative to its package root>: unreadable manifest` (invalid TOML or no `file` array; then nothing else for that manifest).
`main()` prints the Python-distribution lines first, then the vendored lines of every manifest under the repository root (`Path(__file__).resolve().parents[2]`),
counts both in the `"<n> licence problem(s)"` line, and keeps `"licences ok"` for zero problems.

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `dev/tools/check_licences.py`
- `dev/accept/P2-W0/OC-T1.py` (style of an acceptance script: one `PASS <check>` line per check, exit 0)
- `tests/tools/test_check_licences.py` (existing tests; read to keep their expectations: do not edit)
may explore: (none)

## Allowed paths
- `dev/tools/check_licences.py` (modify)
- `dev/accept/P2-WEB1/T06.py` (create)
- `docs/reports/P2-WEB1/T06.md` (create)

## Steps
1. Add the constants and the two functions; call them from `main()` after the Python lines.
2. Write `dev/accept/P2-WEB1/T06.py`: build manifests in a temp directory (never in the repo), call `vendored_problems` and `main` through its helpers, `exit 1` on the first failed check.
   Checks: (a) a good manifest (file written in the temp dir, sha256 computed with `hashlib`, licence `BSD-2-Clause`) gives `[]`; (b) a wrong hash gives exactly one `sha256 mismatch` line;
   (c) a missing file gives `file not found`; (d) licence `GPL-3.0-only` gives `licence not allowed`, `Apache-2.0` and `0BSD` and `MIT` are fine; (e) an entry without `sha256` gives `missing field sha256` and no other line for it;
   (f) invalid TOML gives `unreadable manifest`; (g) `find_manifests` on a temp tree with the glob layout finds the manifest, and finds none in a tree without one;
   (h) `uv run python dev/tools/check_licences.py` on the real repository exits 0 and prints `licences ok` (use `subprocess`).

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
just check
uv run python dev/accept/P2-WEB1/T06.py
```
Expected: `just check` clean; every check prints `PASS`, exit 0. Paste the last 10 lines of each in the report.

## Tests to add
None here. The end run writes `tests/tools/test_check_licences_vendored.py` (copyleft or hash mismatch in a manifest fails).

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus the two pasted outputs and a line saying no pytest was run (deferred). Reports are at most 60 lines.
Do not discuss the commit trailer. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if `just check` demands a change outside Allowed paths other than a consequential pin (rule 12: update it and list it), or if `tests/tools/test_check_licences.py` expectations would change.
- Stop if the real repository run prints a vendored problem (that belongs to S1).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
