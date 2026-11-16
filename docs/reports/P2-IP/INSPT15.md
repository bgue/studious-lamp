# Report — P2-INSP-T15 (dispatch id P2-IP-INSPT15): docs for inspections and checklists

Branch: `p2/insp-t15-docs`   Commit(s): the docs commit and this report (sha in the return message)

## Deviations
- Scope: docs only, as the ticket says. No code, schema, generated or test file changed. Allowed paths only.
- Commit subject is `P2-IP-INSPT15:` (dispatch), not `P2-INSP-T15:` (ticket). Base is `7c6561fa` (dispatch), not `p2/ip-r3`.
- Worktree is `/home/user/wt/ip4/inspt15` (dispatch), not `/home/user/wt/insp/t15` (ticket).
- The trailer names the implementer's own model as the session attribution gives it (Claude Haiku 5.5); the dispatch text said Opus 5.5.
- Documented "as built" gaps that the ticket did not list: the `--answers` export (design section 7), and the TUI filters `o`, `d`, `h`
  and by area (design section 6). Both are in the runbook's and the module page's "not built" lists.
- Design wording "open punch count" is documented as `punch_count` (punch items the result raised), as S2 built it.

## Changed files
- `packages/tl-modules/quality/README.md` — new section "Inspections and checklists (as built, P2-INSP slice 1)"; punch text unchanged.
- `packages/tl-modules/quality/AGENTS.md` — inspection and checklist rules appended.
- `AGENTS.md` — one row appended to "Where things go" (inspections and checklists).
- `docs/modules/quality/README.md` — inspections section; the "Not built yet" first bullet now names the runner and checklist screens.
- `docs/reference/access-words.md` — the six new quality words, copied from `schema/settings/access-words.yaml`.
- `docs/runbooks/inspections.md` (new) — checklists, inspections, terminal, refusals, readiness, agent proposals, generator, demo, not built.
- `docs/reference/inspections.md` (new) — CLI verbs, API routes, MCP tools, command words and states, events, export columns.
- `docs/reports/P2-IP/INSPT15.md` (new) — this report.

## Commands and output
```
$ git branch --show-current ; git log --oneline -1          (worktree)
p2/insp-t15-docs
7c6561fa Merge p2/insp-t14-demo (P2-INSP T14; SQLite all P; Postgres rerun after PERF1; review P, F3 fixed)
$ uv sync --all-packages                                    -> exit 0
$ ls packages/tl-cli/src/tl_cli/insp.py packages/tl-cli/src/tl_cli/checklist.py packages/tl-api/src/tl_api/routes/insp.py \
    packages/tl-mcp/src/tl_mcp/insp_tools.py packages/tl-tui/src/tl_tui/widgets/inspection_log.py dev/demos/P2-INSP.sh
dev/demos/P2-INSP.sh
packages/tl-api/src/tl_api/routes/insp.py
packages/tl-cli/src/tl_cli/checklist.py
packages/tl-cli/src/tl_cli/insp.py
packages/tl-mcp/src/tl_mcp/insp_tools.py
packages/tl-tui/src/tl_tui/widgets/inspection_log.py
$ uv run tl insp --help        (first lines, warning line removed)
 Usage: tl insp [OPTIONS] COMMAND [ARGS]...
 Inspections: plan, schedule, record, verify, reinspect, cancel, ls, show,
$ uv run tl checklist --help   (first lines)
 Usage: tl checklist [OPTIONS] COMMAND [ARGS]...
 Checklists: create, edit, publish, revise, retire, ls, show.
```
By hand: relative links and backticked repo paths in the edited and new pages resolve (`tests/punch_world.py` is package-relative,
as before). The six words match the yaml. No `just check` (docs only, per the ticket).

## Tests added
none (docs).

## Learnings (proposed)
- A ticket's Branch, Worktree and base fields can differ from the dispatch (seen again on this ticket); the dispatch wins, as in
  INSPT05 to INSPT08.
- `uv run tl <group> --help` prints a `UV_NATIVE_TLS` deprecation line on stderr before the help; read the first lines with `2>/dev/null`.

## Open questions / Blocked
- `packages/tl-modules/awp/README.md` line 199 still lists `inspections_planned` as the `checks_na.py` placeholder. It is outside
  this ticket's paths; INSPS3 asked for a follow-up.
- The `--answers` export and the TUI filters (design sections 6 and 7) are not built. Keep them under Later, or open a ticket?
- none blocking.
