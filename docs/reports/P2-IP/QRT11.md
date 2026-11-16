# Report — P2-QR-T11 (demo `dev/demos/P2-QR.sh`)

Branch: `p2/qr-t11-demo`   Commit(s): the report commit on this branch (no demo files created)

## Deviations
1. Blocked before any demo file was written: `dev/demos/P2-QR.sh` and `dev/demos/p2_qr_demo.py` are not created (clause 1 cannot be set up with the verbs the ticket names, see Blocked).
2. Worktree is the dispatched `/home/user/wt/ip4/qrt11` (the ticket's `/home/user/wt/qr/t11` path is superseded). Branch is `p2/qr-t11-demo`, base `380e03f7`.
3. Report path is the dispatched `docs/reports/P2-IP/QRT11.md`.

## Changed files
- `docs/reports/P2-IP/QRT11.md` — this report.

## Commands and output
```
$ uv sync --all-packages
Resolved 183 packages in 3ms
Checked 177 packages in 3ms
$ TL_ENV=dev TL_DB=<scratch>/x.db uv run tl init --dev   -> exit 0
$ TL_DB=<scratch>/x.db uv run tl config set api.public_base_url http://127.0.0.1:9999 --company
error: api.public_base_url cannot be set at the company layer; it is set at: nowhere (it is a platform default only)
$ ... tl config set api.public_base_url http://127.0.0.1:9999 --project P123
error: api.public_base_url cannot be set at the project layer; it is set at: nowhere (it is a platform default only)
```
Supporting check (scratch copy, not committed): `schema/settings/platform.yaml` copied to the scratchpad with the default of `api.public_base_url` set to `http://127.0.0.1:8099`, loaded with `TL_SETTINGS_PLATFORM_FILE`, then `tl config get api.public_base_url` printed `http://127.0.0.1:8099`.

Acceptance (`ruff format/check`, `pyright`, `just demo P2-QR`) not run: the files they check do not exist yet.

## Clause surfaces (for the demo once unblocked)
1. Label — CLI (`tl qr label`, file read as in `test_cli_qr.py`).
2. Signed-out and signed-in page — web (`/web/q/...`, sign-in per `P2-WEB1.sh`).
3. Misses — web (404 bytes and headers equal for uma).
4. Rotate and `ls` — CLI, plus web for the old code.
5. Scaffold card — deferred: `packages/tl-modules/` has no `scaffold` module, so no `scan_card` exists.
6. Agents and export — web (401 for the agent token), API (403 guard), CLI (`export` equals `ls`).
7. Resolve — CLI (`tl qr resolve`, code on stdin).
8. Inspection and permit labels — web card (the inspection and permit scan cards), CLI label.

## The one comparison per clause that would fail if the feature broke
1. The file scan for KEY, PROJECT, register id, record id and the 16-character code outside the grouped print.
2. The 303 `Location` of `/web/q/<code>` and `/web/q/<nonsense>`, compared after removing the `next` value.
3. Status, bytes and headers of the five misses for uma, compared byte by byte.
4. The old code's status (404) against the new code's card, and the `ls` rows for both codes.
5. Not applicable (deferred).
6. The 401 on the web path and 403 on the register path for the agent, before any lookup; `export` rows equal `ls` rows field by field.
7. The stdout card text equals the page's banner and lines.
8. The inspection banner by its state and `REQUESTED - not approved` for the permit.

## Tests added
none (the ticket adds a demo, not tests).

## Learnings (proposed)
- `api.public_base_url` is platform-only: `tl config set` refuses it at both company and project layers with "it is set at: nowhere". The only way to give it a value found is a platform file, `TL_SETTINGS_PLATFORM_FILE`. The ticket's "set through the settings CLI" cannot happen as written.

## Open questions / Blocked
Clause 1 (and every later clause that needs a label) requires the base URL to be set, and the ticket names only the settings CLI. Options:
(a) The demo writes a scratch copy of `schema/settings/platform.yaml` with `api.public_base_url` set, and exports `TL_SETTINGS_PLATFORM_FILE` for the label calls only. Unset state is the shipped file. No package or schema change. Needs the supervisor to accept a platform file as the demo's way to set a platform key.
(b) A CLI or dev-seed change that lets a platform key be set (out of this ticket's Allowed paths; escalation trigger).
Which of (a) or (b) should I use? I have not built either.
