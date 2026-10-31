# Report — P2-W0-OC-S1

Branch: `p2/w0-oc-s1`   Commit(s): see `git log p2/w0-oc-s1` (subject `OC-S1: ...`)

## Deviations
One against the *Blocked* trigger "`just gen` changes any file other than the two new ones and the pins": `just gen` also
rewrote `generated/models.py`. The pydantic generator embeds each core class's annotations (`linkml_meta`), so the
required `tl:offline` / `tl:stream_type` tags on `core.Record` and the 14 core stream classes appear there (annotation
metadata only; no field, type or DDL change; module classes are not in `models.py`). No spec step avoids it; committed as
generated. Supervisor to confirm. Streams not in §4's list: see Open questions.

## Changed files
- `schema/core/annotations.yaml` — documents `tl:offline` and `tl:stream_type` (with the "no generator reads it" correction)
- `schema/core/{record,feed,threads,proposals,auth,settings,extension,integration}.yaml` — tag lines only
- `schema/modules/*/*.yaml` (24 files) — `tl:offline` line after `tl:record_types`; `standard.yaml` on the three subclasses
- `packages/tl-schema/src/tl_schema/generators/offline.py` — new generator, `OfflineClassError`
- `packages/tl-schema/src/tl_schema/generate.py` — import + one `GENERATORS` entry
- `packages/tl-schema/src/tl_schema/generated/{offline_classes.py,docs/offline-classes.md,models.py}` — by `just gen`
- `packages/tl-schema/tests/test_generate.py` — pinned key set gains the two new files (only pin change; no catalog/doc count pin found by grep)
- `dev/accept/P2-W0/OC-S1.py` — acceptance script

## Stream tags (class carrying `tl:stream_type`)
`core.ActivityPost` -> `ActivityPost` (full); `core.Thread` -> `ThreadRow` (full, the cur_thread state class);
`core.Proposal` -> `ProposalRow`; `core.Account` -> `Account`; `core.Setting` -> `SettingChangeRow` (cur_setting; no
`Setting` class exists, `SettingDefinition` is not stream state); `core.TypeRegistration` -> `TypeRegistrationRow`;
integration: `IntegrationApp`, `ActionDefinition`, `ActionInvocation`, `Rule`, `InboundEndpoint`, `Enricher`,
`EnrichmentValue`, `WebhookSubscription` (each its own state class). All `none` except the first two.

## Design notes
- Resolution copies `type_labels.py` (source class = the class, or the subclass named after the type). A parent that also
  declares a value must agree with the subclass; a subclass lacking it is "missing" (error names the subclass).
- Extra guards (not in spec): `tl:offline` on a class that is neither record-type source nor stream class; `tl:stream_type`
  on a module class or not `core.<Name>`; stream tag without `tl:offline`. All raise `OfflineClassError`.
- Guard sites in `generators/offline.py`: unknown value `_value`; missing `_record_value` (`if not declared`); disagreement
  `_agree`; subclass resolution `_record_value` (`source = ...`). Line numbers: `grep -n` the names (file will move).

## Commands and output
```
$ just gen            -> wrote 641 files (+offline_classes.py, docs/offline-classes.md; models.py annotation metadata)
$ just check          -> 0 errors, 0 warnings; generated files are up to date (641 files); licences ok
$ uv run python dev/accept/P2-W0/OC-S1.py
PASS every TYPE_LABELS type has a class and nothing else
PASS record table equals the spec table cell for cell
PASS OFFLINE_STREAMS holds the spec streams
PASS ... deterministic / missing / unknown / multi-type / stream-without-class (8 PASS in all, table printed, exit 0)
```
No pytest, no `just gate` (owner policy for this increment).

## Tests added
none (end run, `packages/tl-schema/tests/test_offline_classes.py`, per the piece spec)

## Learnings (proposed)
Tagging a core class changes `generated/models.py` (pydantic embeds annotations); a schema piece that tags core classes
should list `models.py` among its expected generated changes.

## Open questions / Blocked
- `core.InboundDelivery` (stream type in `integration/streams.py`) is not in §4's integration list, so it is untagged and not
  in `OFFLINE_STREAMS`. Add as `none` in a follow-up if wanted (OC-S2's `stream_class` returns `none` for unknown streams anyway).
- Not Blocked otherwise.
