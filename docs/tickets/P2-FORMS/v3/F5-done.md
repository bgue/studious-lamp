# V3-F5 · forms docs, runbook, tour shots, highlights
kind: ticket · review: lite · branch `p2/v3-f5-done` · worktree `/home/user/wt/v3p/f5` · base `p2/v3-forms`.
Process: `docs/build-spec/process-v3.md` section 2. Load the `throughline-docs` rules from
`.claude/skills/throughline-docs/SKILL.md` (module READMEs, runbooks) and `tui-layout` only to describe screens.

## Build
1. `docs/runbooks/forms.md` (style of `docs/runbooks/inspections.md`): publish a template; fill from the CLI
   (`tl form fill`, `--resume`), the terminal app (Forms log, runner), the web page (`/web/forms?project=P`) and a
   scan card ("Open record"); the review queue (accept, refuse; the submitter cannot accept their own); bound forms
   (`tl form for|record`, inspections and permits); agents (five MCP tools, proposals only, never drafts);
   signed-in intake (`tl intake code issue|revoke|ls`, `tl intake ls|show|accept|reject|purge`, Intake log);
   `tl report form-submissions|form-templates`. A "Known limits" section: hidden records leave key gaps
   (ADR-0016, D41); the `/web/` 64 KiB body cap; the public intake link `/i/<code>` is not built (owner gate);
   privileged forms are visible to their author only (D40). Add its line to `docs/runbooks/README.md`.
2. `packages/tl-modules/forms/README.md`: bring "what it does" and the surfaces list up to date with the above
   (link the runbook; no duplication).
3. Tour: add to `dev/tour/phase2.py` (same method, `tourkit.py`, frozen clock, leak check) the shots: forms log,
   a submission's details, the runner screen mid-fill, the Intake log, and a `tl report form-submissions` CLI shot.
   Run `just tour 2` and commit the new SVGs under `docs/reports/tour/phase-2/`; regenerate the pack index the
   tour writes. Do not change existing shots' content (if a re-render changes an old SVG byte-wise only through
   the clock or ids, keep the old file).
4. Highlights: add the forms log and the runner shot to `dev/tour/highlights.py` (next numbers) and a short
   section to `docs/reports/HIGHLIGHTS-TOUR.md` (headings match file names); run `just tour highlights`.

## Rules
Docs and tour only: no code under `packages/*/src`, no tests changed except the tour's own if it has any. No model
names. Plain English in the runbook.

## Gate
`uv sync --frozen --all-packages`; `uv run ruff check dev/tour`; `uv run pyright dev/tour/phase2.py
dev/tour/highlights.py`; both tour runs exit 0 with the leak check passing. Hold a heavy lock
(`flock /tmp/claude-0/tl-heavy.lock` or `.2.lock`) for each tour run. Report `docs/reports/P2-FORMS/V3-F5.md`,
at most 10 lines. Prefix `V3-F5:`.
