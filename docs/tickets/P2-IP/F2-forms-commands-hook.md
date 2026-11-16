# P2-IP-X4-F2: forms `commands` hook (X4 conformance)

Branch p2/ip-x4-forms-hook, base p2/ip-x4@addf814c.

## Problem
`tests/services/test_module_hooks.py` (declares-commands) fails: forms declares commands but its
`ModuleSpec` has no X4 `commands` hook. Permits is the same and waits for PTW-S2; not touched here.

## Fix (forms only, own package)
- `tl_mod_forms/module.py`: add `commands="tl_mod_forms.module:FORMS_COMMANDS"` (table exists).
  `FormsCommand` already carries `model`, `handler`, `access`; `ApiCommand` alias stays.
- The API table builds from `module_commands()`; forms had no pre-hook line in `tl_api/commands.py`
  or `app.py`, so `prehook_lines.toml` stays empty.
- Delegation: `SubmitForm` is eligible (forms proposal row, access user) in
  `tests/tools/delegation_marks.toml`. The other ten commands stay excluded with a reason in
  `tests/tools/proposable_exclusions.toml` (already present).

## Allowed paths
`packages/tl-modules/forms/**`, `tests/tools/delegation_marks.toml`, this ticket and report.

## Acceptance
Hook, conformance and registry tests green; forms tests; tl-api hook and commands tests; `just check`.
