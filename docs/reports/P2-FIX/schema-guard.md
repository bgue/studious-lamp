# P2-GUARD: schema-evolution guard

Deviations: baseline lives at `packages/tl-schema/compat/event-schemas.json`, not `schema/compat/`
(AGENTS.md bars `schema/**` and the LinkML loaders read that tree). The schemareg classifier works on
property packages (psets), not JSON Schema, so it was not reused; `tl_schema/compat.py` is new.
Root `conftest.py` changed (collect mode default, session-end violation file).

## What was built
1. `tl_schema.compat`: baseline per event type and schema_version (payload schema from the generated
   catalog, descriptions and titles dropped). `--check` (a `just check` step) fails on removed event
   type, version or property, changed type or format, newly required property, tightened enum,
   pattern, const or bound, newly forbidden extras. Additions pass. `just compat-update` refuses to
   write when the change is not additive. Tests: `packages/tl-schema/tests/test_compat.py` (one
   additive case; 12 breaking kinds, each one line naming event and property).
2. `tl_adapters/_payload_check.py`, called from `BaseUnitOfWork.append` before `append_in`.
   `TL_PAYLOAD_VALIDATION=off|collect|enforce`: code default `off`, test session default `collect`.
   Collect records (event_type, key, reason) with a count and logs once; enforce raises
   `PayloadInvalid`. Types with no payload class are reported, never failed. Class map comes from
   the catalog index (cached). Merged into `.gate/payload-violations.txt` at session end.
   Tests: `packages/tl-adapters/tests/test_payload_check.py`.
3. `packages/tl-core/tests/test_intent_roundtrip.py` (hypothesis): round-trip text identity and
   event-hash stability.

## Core paths changed (for APPROVALS)
- `packages/tl-adapters/src/tl_adapters/_unit.py` (one import, one call in `append`)
- `packages/tl-adapters/src/tl_adapters/_payload_check.py` (new)
- `packages/tl-schema/src/tl_schema/compat.py` (new), `packages/tl-schema/compat/event-schemas.json`
- `conftest.py`, `justfile` (`compat-update`, `compat --check` in `check`)
No handler or event schema changed.

## Collected violations (tl-core tests, awp and materials module tests, tl-adapters tests)
Real violations (payload class exists, payload fails it):
- Link.Added: `link_id` extra_forbidden, 934 appends
- Link.Retracted: `link_id` extra_forbidden, 26 appends
Not seen: `note` on Link.Verified (no test in the run appends it); no `**` splat site hit an event
with a class. Coverage gap: the generated models hold 89 of 252 catalog payload classes; 87 event
types appended in these suites have no class and are listed as "no payload class" in the file.
Product payloads were not fixed here. Closing the gap (generate a class for every event) is a
follow-up before `enforce` can be the default.

## Gates
- `just check` (with NODE_OPTIONS=--max-old-space-size=6144): pass
- `just gate packages/tl-schema/tests/test_compat.py packages/tl-adapters/tests`: 277 passed
- `just gate-pg packages/tl-adapters/tests`: 330 passed
- `just gate packages/tl-core/tests packages/tl-modules/awp packages/tl-modules/materials`: 2041 passed (collect mode)

## Mutation
Sentinel (removed-property check disabled): killed. Targeted 3/3 killed: required-set check
disabled, lower-bound tightening loosened, enum subset check disabled. No survivors.
