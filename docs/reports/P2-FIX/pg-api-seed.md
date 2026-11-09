# P2-FIX: Postgres parity of the hidden-world seed

## Cause
`seed_hidden_world` (tl_mod_correspondence/confseed.py) seeds documents through `DocumentsWorld`,
whose commands run as `user:u`. No account `u` exists. `holder_for_actor` gives an account-less
`user:` actor the `user` role in every module only on a SQLite dev/test ledger (`dev_ledger`, the
owner's decision D2); on Postgres such an actor holds nothing, so `AttachFile` is refused with
"AttachFile needs the user access word for documents". The product rule is deliberate; the seed
relied on a SQLite-only shortcut. Every `[postgres]` case that used the seed errored in setup.

## Fix
Test seed only. `seed_hidden_world` now calls `_ensure_documents_actor`: on a non-SQLite ledger,
if no account `u` exists, it creates one (person, role `user`, throwaway password). SQLite is
unchanged. No product code, schema, event or core interface changed.

## Gates
- just check: pass
- just gate-pg packages/tl-api/tests/test_api_actions.py: 18 passed
- just gate-pg test_confidentiality_walk, test_api_derivation_reads, test_api_document_controller,
  test_schema_forms: 109 passed
- just gate-pg test_api_documents_reads, test_api_documents, test_api_addable, test_api_page1,
  test_client_derivation: 50 passed
- just gate-pg packages/tl-adapters/tests: 309 passed
- just gate packages/tl-modules/correspondence/tests packages/tl-web/tests (sqlite): 1394 passed
