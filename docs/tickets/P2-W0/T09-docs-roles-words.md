# P2-W0-T09 (DOC-1) — Docs for module roles and access words

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: RM-S1 to RM-S4, W0-B1 (merged)
Branch: `p2/w0-t09-docs-roles-words`

## Goal
An admin can read how module roles work (grant, list, effective view, what derives from the account role, what a grant never gives), and
a module author can read the table of access words and which role-table word each needs.

Do not discuss the commit trailer in the report; no model names anywhere in committed files.

## Brief references (pasted, abridged)
- Roles: `viewer` holds `read`; `user` holds `read, user`; `superuser` holds `read, user, controller`. An agent may only be granted `viewer`
  or `user` (agents still only propose). `admin` and `company` are platform words and cannot be granted. Only an admin grants or revokes.
- Derivation when no explicit grant applies: account role `user` gives module role `user` in every module; `document_controller` gives
  `user` everywhere and `superuser` in `documents`, `correspondence` and `schedule`.
- Precedence (roles-mvp §4): an explicit grant for that project and module replaces the derived role; scope `company` reads company
  grants only for a module that declares `company_roles` (materials in Phase 2; others answer 422 `no_company_roles`).
- A superuser grant gives **no** restricted read (ADR-0016 unchanged); module roles do not filter reads. Grant events are hidden from
  `GET /events` for non-admins.
- A proposal is accepted only if the accepter holds the account role **and** the module word (AND).
- CLI (all admin-only): `tl admin roles grant <user> --project P1 --module documents --role superuser --reason "..."`,
  `tl admin roles revoke <user> --project P1 --module documents --role superuser --reason "..."`, `tl admin roles ls [--project] [--module] [--user] [--json]`,
  `tl admin roles effective <user> --project P1`. TUI: accounts screen (`F10`), key `m` opens the module roles log. API: `POST
  /admin/accounts/{id}/module-roles`, `POST .../module-roles/revoke`, `GET /admin/module-roles`, `GET /admin/accounts/{id}/effective-roles?project`,
  `GET /auth/me/roles?project` (any signed-in account).
- Access words as data: `schema/settings/access-words.yaml` maps a fine word (for example `awp.cwp.release`) to `read`, `user` or `controller`;
  an unknown table word or a repeated word stops start-up (`AccessWordError`); `ModuleSpec.command_words` holds the table word or a fine
  word; the API reads the fine word once, in `command_index()`.
- Errors: `unknown_role` 422, `unknown_module` 422, `no_such_grant` 404, `no_company_roles` 422.

## Context (read these, nothing else)
- `docs/runbooks/accounts-and-access.md` (add a section; its "Before you start" roles bullet gains one sentence pointing at it)
- `schema/settings/access-words.yaml` and `schema/settings/module-roles.yaml` (the source of the new reference table)
- `docs/templates/runbook.md`
- `docs/reports/P2-W0/RM-S3.md` (routes table only)
may explore: (none)

## Allowed paths
- `docs/runbooks/accounts-and-access.md` (modify: a new section "Module roles" with numbered steps for grant, list, effective, revoke, and
  "what it does not change")
- `docs/reference/access-words.md` (create: purpose line; table `word | needs | module` for every row of `access-words.yaml`, grouped
  `awp.*` then `materials.*`; the three table words; how a module author uses a fine word; link to the yaml as the single source)
- `docs/reports/P2-W0/T09.md` (create)

## Rules (throughline-docs)
Purpose in the first sentence; one idea per sentence; tables for parallel facts; commands in fenced blocks, copy-pasteable from the repo
root; ISO dates; link instead of duplicating; no secrets. Keep the runbook's existing template headings; do not change other sections.

## Acceptance
```
just check
grep -c '^  [a-z]*\.[a-z.]*:' schema/settings/access-words.yaml    # N words
grep -c '^| `' docs/reference/access-words.md                       # N rows in the new table (header and separator excluded)
```
Expected: `just check` clean; the two counts agree; every command in the runbook section exists in `uv run tl admin roles --help`.

## Tests to add
None (docs).

## Report requirements
Standard report (`docs/templates/haiku-report.md`): the two counts, the `--help` check, files changed. Deviations first.

## Escalation triggers
- A command or route above is not in the tree, or the yaml and this ticket disagree (report which, do not guess).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
