# Report — P2-QR-T12 (docs: QR codes at the workface)

Branch: `p2/qr-t12-docs`   Commit(s): the single docs commit on this branch (sha in the return value)

## Deviations
1. Report path is `docs/reports/P2-IP/QRT12.md` (from the dispatch), not the ticket's `docs/reports/P2-QR/`.
2. The Brief's `packages/tl-web/src/tl_web/pages/scan_limit.py` does not exist. The file is `packages/tl-web/src/tl_web/scan_limit.py`; the docs use that path.
3. The Brief lists an `issue` verb. The CLI has no `tl qr issue`: `tl qr label` issues the code, `tl qr rotate` replaces it. The docs describe the built verbs only.
4. The ticket depends on "demo merged". QRT11 reports `just demo P2-QR` exit 1 (Postgres clause 7). The runbook says so and does not claim a pass.

## Changed files
- `AGENTS.md` — one QR row appended to "Where things go" (module, schema, contract, CLI, API, web, demo, runbook).
- `docs/reference/access-words.md` — three rows, `qr.view` (read), `qr.issue` (user), `qr.revoke` (controller), from `schema/settings/access-words.yaml`; they match the S1 report.
- `packages/tl-modules/qr/README.md` — rewritten as built (words, surfaces, code map, tests, not built).
- `packages/tl-modules/qr/AGENTS.md` — access words and rules added; no rule removed.
- `docs/modules/qr/README.md`, `docs/reference/qr.md`, `docs/runbooks/qr-labels.md` — created.
- `docs/reports/P2-IP/QRT12.md` — this report.

## Commands and output
```
$ uv sync --all-packages     (ok; no new dependency)
$ ls packages/tl-modules/qr/src/tl_mod_qr/cli.py packages/tl-modules/qr/src/tl_mod_qr/routes.py packages/tl-web/src/tl_web/pages/scan.py packages/tl-core/src/tl_core/qr/types.py dev/demos/P2-QR.sh
dev/demos/P2-QR.sh
packages/tl-core/src/tl_core/qr/types.py
packages/tl-modules/qr/src/tl_mod_qr/cli.py
packages/tl-modules/qr/src/tl_mod_qr/routes.py
packages/tl-web/src/tl_web/pages/scan.py
$ uv run tl qr --help
 Usage: tl qr [OPTIONS] COMMAND [ARGS]...
 Commands: label, rotate, revoke, ls, export, resolve
$ link check (relative links in the four module, reference and runbook pages)
(no missing targets)
$ grep for model names in the new and rewritten pages: none added
```

## Tests added
None (docs only).

## Learnings (proposed)
- Brief verb and path names drift from the code (`issue` vs `label`; `pages/scan_limit.py` vs `tl_web/scan_limit.py`). Write runbooks from `tl <group> --help` and an `ls` of every named path, not from the brief.
- A platform-only setting (`api.public_base_url`) has no documented operator path to a value. Spec and runbook both need one.

## Open questions / Blocked
1. Operator procedure for `api.public_base_url`: `tl config set` refuses it, and the shipped platform file is not an operator path. Runbook step 1 states the gap and does not guess. Needs an owner decision.
2. Is a `tl qr issue` verb intended? The docs assume none.
3. `just demo P2-QR` fails on Postgres (QRT11 open question 1). Not resolved here.
4. The exact install command for the `labels` extra (`segno`) is not verified; the runbook names the extra only.
5. The follow-up slice for the not-built items is not in `docs/build-spec/DEFERRED.md` (no QR entry at base 7c6561fa).
6. No T01 report exists on this base. `packages/tl-modules/qr/src/tl_mod_qr/views.py` still has a docstring that says "stub: T01 fills them", but its functions are implemented. Docs describe them as built. Outside Allowed paths, so not edited.

Blocked: none. Items 1 and 2 need an owner or orchestrator decision before the runbook is final.
