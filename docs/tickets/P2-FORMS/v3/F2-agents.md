# V3-F2 · Forms for agents (MCP) and draft resume (demo clause 4, MCP leg of clause 7)
kind: piece · review: full · branch `p2/v3-f2-agents` · worktree `/home/user/wt/v3p/f2` · base `p2/v3-forms` (F1a, F1b,
F1s merged). Process: `docs/build-spec/process-v3.md` section 2. Old tickets T06, T08, T10 (README rows) are the reference.

## Goal
An agent can list published templates, read one (as JSON Schema), list and read the submissions its viewer may see,
and propose a submission that a person confirms; a person can save a draft, leave, resume it in `tl form fill --resume`
or the runner screen, and submit it.

## Build
1. MCP tools in `tl_mod_forms/tools.py` (pattern: `tl_mod_permits/tools.py` and its `PERMIT_MCP_ACTIONS`):
   `list_form_templates`, `get_form` (`as=jsonschema` default), `list_form_submissions`, `get_form_submission`,
   `propose_form_submission` (the `PROPOSABLE` row from S3; a proposal, never a direct submit). A `FORMS_MCP_ACTIONS`
   set ORed into `MCP_ACTIONS` as the others are. Agents get the forms reads through these tools only: replace F1a's
   closed `forms.read` pin in `packages/tl-api/tests/test_auth_review.py` with the narrowest opening that serves the
   tools (say which in the report). Drafts are never listed or read by an agent (an agent is never an author).
2. Draft resume: `tl form fill TEMPLATE --resume [DRAFT]` (latest own draft when none named) and the runner screen
   opening a draft (F1b's screen; pre-filled answers, same steps). `SaveFormDraft` / `DiscardFormDraft` exist (S3);
   the `forms.draft_saves_max` bound is respected and its refusal text shown as is.
3. Walk: the MCP tools for the five readers plus an agent (`tests/confidentiality/` pattern, F1a's
   `test_forms_walk.py`): a hidden, privileged (D40) or draft submission answers exactly like a missing key on every tool
   (byte comparison of the tool result); a proposal for a hidden template or record is refused like a missing one.
   Resume: another person's draft key answers as missing on `--resume` and in the runner.
4. Demo `dev/demos/p2_forms_demo.py`: clause 4 (save a draft from the CLI, resume, submit; the number appears only at
   submit) and an MCP leg in clause 7 (the hidden key and a missing key give byte-equal tool results). Fix the
   `P2-FORMS.sh` header comment and final echo to list every clause the script runs. Earlier clauses stay green.

## Rules
No edit of `confidentiality.py`, no schema change, no new event. `bound.record` (F1s) is not exposed as an MCP tool in
this unit. No paid model calls: tools are tested through the MCP test harness, never a model.

## Gate
After creating the worktree run `uv sync --frozen --all-packages` (new entry points are only seen after a sync).
`just gate-changed` (if it stops at the deferred `test_check_wheels` pin, run its later steps by hand and say so), then
`TL_DEMO_BACKENDS=sqlite just demo P2-FORMS`. Report `docs/reports/P2-FORMS/V3-F2.md`, at most 15 lines. Prefix `V3-F2:`.
