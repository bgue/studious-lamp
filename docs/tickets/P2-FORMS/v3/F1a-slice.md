# V3-F1a · Forms slice: generator, read routes, `tl form`, demo clauses 1–3, 5, 7, 8
kind: piece · review: full · branch `p2/v3-f1a-slice` · worktree `/home/user/wt/v3p/f1a` · base `p2/v3-forms`
(after V3-P0, P1, P2 are merged) · Process: `docs/build-spec/process-v3.md` (section 2; this is the demo-first unit).

## Goal
A person can publish a general form template, fill and submit it, and a controller can review it, on the full
demo project, through the CLI and the API, and the demo script proves it. Already on the base: the engine
(`tl_core/forms`: rules, JSON Schema projection, runner model), the `forms` schema and commands (S2, S3), the
confidentiality rows (CR1), the views (`tl_mod_forms/views.py`, T03), the SurveyJS projection (B1).

## Build
1. **Generator section** (old T09, `docs/tickets/P2-FORMS/T09-demo-generator.md` as reference): general
   templates (toolbox talk, job hazard assessment, pre-use check) and submissions in several states, one
   confidential submission, one draft, in `dev/seed/demo_project/forms.py`; registered as section `forms`; pins.
2. **Read routes** (old T04 rows in `README.md`): `GET /forms/templates`, `/forms/templates/{key}/versions/{n}`
   with `?as=jsonschema|surveyjs` and an ETag, `/forms/for/{key}`, `/forms/submissions[/{key}]`, through the
   forms module's own `read_routers` hook (X4 hooks are on the base). API client methods.
3. **CLI** (old T05): `tl form ls|show|fill|drafts|submit|review` through the forms `cli_groups` hook;
   `--answer q1=yes`, `--answers-file`; plain output like the other module CLIs.
4. **Shared files, owned by this unit for the pilot**: every forms and intake method on the TUI client protocol
   (`tl_tui/client.py`) and the embedded client (`embedded.py`), stubs raising `NotImplementedError` where a later
   unit fills them (runner screen, MCP, intake); the forms hook rows; the `MCP_ACTIONS` lines later units need,
   left closed. Later units F1b, F2, F3, F4 only fill these in.
5. **`tl report forms`** registration if V3-P0 left it out (P0 covers form submissions). Also make
   `packages/tl-modules/awp/tests/test_proposable_exclusions.py` green: it is red on the base with a stale exclusion
   that names form commands; fix the exclusion list, never the test's rule.
6. **Walk**: the five-reader walk over every route and CLI read this unit adds (`tests/confidentiality/` pattern,
   `twin_channels.py`); hidden == missing byte comparison; a draft visible only to its author; a submission of a privileged
   template visible only to its author, even to an admin or a restricted-level controller (owner Q7, 2026-11-17).
7. **Demo** `dev/demos/P2-FORMS.sh` + `dev/demos/p2_forms_demo.py` (pattern: `P2-PTW.sh` / `p2_ptw_demo.py`),
   on the full demo project built by the generator, SQLite then Postgres (`TL_DEMO_BACKENDS`). Clauses:
   1 publish a template (CLI) and read it back as JSON Schema and SurveyJS (API); 2 fill and submit from the CLI,
   number allocated at submit; 3 fill through the runner model (driver, `tl_core/forms/runner.py`) and submit;
   5 a controller other than the submitter accepts; the submitter's own review is refused (exact text);
   7 a hidden submission answers as a missing one on every forms read (CLI, API) — byte comparison;
   8 a draft is invisible to every reader but its author. Each clause prints its wall time; any forms list read
   over 1 s fails the clause. `PASS clause N` only after a real comparison.

## Rules
You may change forms fixtures, the forms generator section and the forms demo without asking. Do not edit
`confidentiality.py` or another module's handlers. Speed budget: `just gate tests/perf` must stay green.

## Gate
`just gate-changed` (from V3-P2) then `TL_DEMO_BACKENDS=sqlite just demo P2-FORMS`; one Postgres demo run, report
result and time. Report `docs/reports/P2-FORMS/V3-F1a.md`, at most 15 lines. Subject prefix `V3-F1a:`.
