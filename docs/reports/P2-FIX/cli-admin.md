# P2-FIX-ADMIN: CLI admin commands for a signed-in non-admin

## Finding, checked against trunk 27f6f1ef
Not reproducible. Every CLI call site of an API admin-gated handler is already gated by
`admin_gate(ctx)` (integration layer) or `require_admin` (standards, tags, cost, schema, derive).
`rule.create` has `admin_gate(ctx)` at rule.py:118, before the handler at :125. No source change
was needed; this piece adds the missing tests and a pin.

## The list (API source of truth: `COMMANDS` rows whose `effective_access` is admin or company)
38 handlers. CLI call sites, all gated (function: gate):
- rule create/mode/enable/disable (`_switch`): admin_gate. action define/retire: admin_gate.
- enricher register, enable/disable: admin_gate. endpoint create/enable/disable/mode: admin_gate.
- integration app add/enable/disable: admin_gate. delivery retry: admin_gate.
- standards add-value/close/close-value, tag class define/revise/close, tag create: require_admin.
- standards load (bulk helper, issues RegisterCodeList/Mnemonic/NumberingPattern): require_admin.
- cost import, derive schema register/retire, derive publish (tags: `_require_publisher` ->
  require_admin), derive compensate, schema request/approve/publish/deprecate/retire/adopt,
  waiver approve/revoke: require_admin.
No CLI call site: AdminFlagLink, AdminRetractLink (there is no `tl link admin-flag`), ReviseAction,
ReviseIntegrationApp, ReviseEnricher. Nothing to gate; the pin covers them if one is added.
Company-access twin (AddCodeValue, CloseCodeValue, the only two): require_admin, stricter than the
API (always needs a session). Module words for the rest stay with `require_command`.
Embedded client: only PublishDerivedTags and CompensatePublication are admin handlers there, both
call `_admin_gate`. No gap, no change.

## Dev-ledger finding
The API never lets a dev principal be admin (a dev token has roles ["user"]). The CLI lets a
caller with NO session act as admin only on a dev/test/ci SQLite ledger file (`admin_gate`) and
`require_admin` never does. That is the documented file-owner rule (ADR-0009 sec. 7: the owner can
write the file anyway); a signed-in non-admin is refused everywhere, and Postgres always needs a
session. Left as is.

## Tests added: packages/tl-cli/tests/test_cli_admin_commands.py
- 17 integration-layer commands: signed-in non-admin, TL_ENV=prod: `error: forbidden`, event
  count unchanged. An admin session succeeds (`integration app add`).
- Pin: AST scan of tl_cli; any function naming an admin-gated handler (call or reference, from
  the API table) must call admin_gate/require_admin (or `_require_publisher`).

## Mutants
Sentinel (remove rule create gate): killed. Targeted: endpoint `_switch` gate removed, killed by
the refusal tests and the pin; `admin_gate` non-admin branch removed, killed. 3 of 3 plus sentinel.
