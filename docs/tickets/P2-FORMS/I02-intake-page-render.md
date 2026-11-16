# P2-FORMS-I02 — Plain page of a public intake form (pure render)

Status: ready
Tier: haiku
Kind: ticket
Review: full  (public text surface: escaping is the whole job)
Labels: module, tests
Depends on: S2 merged (module `forms`), no other
Branch: `p2/forms-i02-intake-page`
Worktree: harness-created under `/home/user/wt/forms/i02` (from `p2/ip` head)

## Goal
`tl_mod_forms.intake_page` builds the five HTML documents of `/i/<code>` as strings: the form, the thank-you, and three fixed pages (not found, sheet
full, try later). It is pure (no request, database or clock). S6 mounts it; it changes no route.

## Brief references (pasted, ADR-0032 decisions 1, 4, 9, 10, 12, 13, abridged)
Write-only page: title, a heading the issuer typed, the fields, nothing about any record, no prefilled value, no autocomplete; after a submit one fixed
page with a receipt word. One neutral page for every dead code (the same bytes). The page "works with no script": no script, no link, no third-party
resource, no inline style, one own stylesheet. Hidden honeypot field. Staged text is hostile: escaped on every surface. A sign-on says one line: it is attendance
only, confirmed by a person, not a sign-in. Fields are format 2 intake fields: kinds `text`, `choice`, `number` only; ids `^[a-z][a-z0-9_]{0,31}$`.

## Interfaces (names fixed by the provided test)
```python
# packages/tl-modules/forms/src/tl_mod_forms/intake_page.py  (create; stdlib `html.escape`, typing, collections.abc only)
def render_form(*, title: str, heading: str, fields: Sequence[Mapping[str, Any]], purpose: str, form_key: str,
                error_ids: Sequence[str] = (), values: Mapping[str, Any] | None = None) -> str
def render_thanks(receipt: str, purpose: str) -> str      # purpose "request" or "sign_on"
def render_not_found() -> str                            # no argument: constant
def render_full() -> str                                  # constant
def render_busy() -> str                                  # constant
```
Rules the test pins: every document starts `<!doctype html>`, has `lang`, charset, viewport, `robots noindex`, `referrer no-referrer` metas and exactly one
`<link rel="stylesheet" href="/web/static/intake.css">`; the form is `<form method="post" action="">`; one control per field named `f_<id>` (`<input
type="text" maxlength="280">`, `<select>` with `<option>` per choice, `<input type="number" min max step="any">`), `required` when the field is, `aria-invalid="true"` for ids in
`error_ids`, `value` from `values` only for a field of the list; a hidden `k` input with `form_key`; a honeypot `<input type="text" name="website" tabindex="-1"
autocomplete="off">` in a `<p class="hp" aria-hidden="true">`; label, help and unit shown; the `purpose` line (`request`: "This sends a request to the site
team. You will not get a reply here."; `sign_on`: "This is not a sign-in. It records that you say you are present; a supervisor confirms it."), also on the thank-you
page. Every dynamic string goes through `html.escape(..., quote=True)`. No `<script`, `<a `, `<iframe`, ` style=`, `on...=` attribute, `javascript:` or any URL but the stylesheet.
The three fixed pages differ from each other and name no record, code or setting.

## Context (read these, nothing else)
- `docs/tickets/P2-FORMS/provided/I02_test_intake_page.py` (the test)
- `packages/tl-modules/forms/src/tl_mod_forms/names.py` (no import needed; style only)
- `packages/tl-core/src/tl_core/forms/types.py` (`INTAKE_TEXT_MAX`, `RESERVED_CLAIM_IDS`; read, do not import)
may explore: none

## Allowed paths
- `packages/tl-modules/forms/src/tl_mod_forms/intake_page.py` (create)
- `packages/tl-modules/forms/tests/test_intake_page.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-FORMS/I02.md` (create)

## Acceptance
```
just check
just gate packages/tl-modules/forms/tests/test_intake_page.py
cmp docs/tickets/P2-FORMS/provided/I02_test_intake_page.py packages/tl-modules/forms/tests/test_intake_page.py
```
Expected: 6 passed, `just check` clean, `cmp` silent.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report; `101` and `100` phrases.

## Escalation triggers
- The test needs a wording the ADR does not allow, or a second stylesheet: stop with `122`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
