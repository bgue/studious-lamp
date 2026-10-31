# P2-W0-OC-S1 — Offline class: the `tl:offline` annotation, its values and the generator

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: schema, codegen
Depends on: — (no roles dependency, plan check F3)
Branch: `p2/w0-oc-s1`
Approver (schema): the orchestrator under P2-Q10; the class values are approved by the owner (answer 5), line in `docs/memory/APPROVALS.md` at merge

## Goal
After this piece every record type carries an offline class (`full | draft_only | none`) declared in the schema, and
`just gen` writes `generated/offline_classes.py` (`OFFLINE_CLASSES`, `OFFLINE_STREAMS`) and
`generated/docs/offline-classes.md`. A record type with no `tl:offline`, an unknown value, or two classes giving one type
different values fails `just gen` with `OfflineClassError` naming the class. Nothing enforces the class yet (OC-S2).

## Brief references
`docs/build-spec/specs/offline-classes.md` **§2, §3 and §4 (the table, approved as written, read in full)**, with
`specs/wave0.md` §2. Decisions that bind this piece:
1. Annotation `tl:offline` documented in `schema/core/annotations.yaml` beside `tl:file_slots` (the file is the vocabulary
   record; add the entry, with a "no generator reads it" correction: `tl_schema.generators.offline` does). Written at class
   level on every class that is a record type, resolved **exactly** as `generators/type_labels.py` resolves record types
   (`tl:record_types` on a module class; the subclass named after the type for a multi-type class such as `Standard`;
   `core.Record`). Copy its resolver; if it needs a shared helper, import the private helper as `type_labels.py` imports
   `_module_of` (pyright comment style as there) rather than editing `type_labels.py`.
2. Non-record streams carry the class with a new tag `tl:stream_type: core.ActivityPost` (core classes only) on the class
   that is the stream's payload/state class; output `OFFLINE_STREAMS`. Streams and classes are those of the table's second
   block in §4 (`core.ActivityPost`, `core.Thread` `full`; `core.Proposal`, `core.Account`, `core.Setting`,
   `core.TypeRegistration` and the integration streams `none`). Pick the carrying class for each from the schema; where a
   stream has no single class, put the tag on its state class and say so in the report. Do not invent record types.
3. The values are §4 **as written**: `core.Record` and `engineering.Tag` `full`; `documents.ReviewCycle` `none`;
   `documents.{Document,Revision,Rendition,Transmittal}` and `correspondence.{Correspondence,TechnicalItem}`
   `draft_only`; every other record type `none`. Include every type in `TYPE_LABELS` (read it; a type missing from §4 is
   *Blocked*, not guessed). Extension types (`type.yaml`) are OC-S2's.
4. Output shape: `OfflineClass = Literal[...]`; `OFFLINE_CLASSES: Final[dict[str, OfflineClass]]` sorted by type;
   `OFFLINE_STREAMS` likewise; deterministic, drift-checked (`just check` runs `--check`). The docs page lists type, label
   (from `TYPE_LABELS`), class, and a one-line meaning of the class (same three sentences for every row of a class).
5. One call added to `GENERATORS` in `tl_schema/generate.py`; no other change there.

## Context (<= 10 files)
- `docs/build-spec/specs/offline-classes.md` §2-§4; `specs/wave0.md` §2
- `packages/tl-schema/src/tl_schema/generators/type_labels.py` (copy the resolution), `generate.py`, `generated/type_labels.py` (the type list)
- `schema/core/annotations.yaml`; `schema/core/*.yaml` and `schema/modules/*/*.yaml` (where the record classes sit; grep `tl:record_types`)
- `packages/tl-schema/tests/test_generate.py` (pinned file list)

## Allowed paths
- `schema/core/annotations.yaml`; `tl:offline` and `tl:stream_type` lines (nothing else) in `schema/core/*.yaml` and `schema/modules/*/*.yaml`
- `packages/tl-schema/src/tl_schema/generators/offline.py` (create), `packages/tl-schema/src/tl_schema/generate.py` (one call)
- `packages/tl-schema/src/tl_schema/generated/**` (only by `just gen`; commit the output, including `offline_classes.py`, `docs/offline-classes.md`)
- pinned lists that change only because two generated files exist: `packages/tl-schema/tests/test_generate.py` and any catalog/doc count pin that `just check` or a grep shows (list each in the report)
- `dev/accept/P2-W0/OC-S1.py` (create), `docs/reports/P2-W0/OC-S1.md` (create)
Not allowed: `tl_core/**`, any `module.py`, `extypes`, `type.yaml` handling, `tl_cli/**`, the sync/merge annotation `tl:merge` (Phase 3).

## Acceptance (run these, once; no pytest, no `just gate`)
```
just gen
just check
uv run python dev/accept/P2-W0/OC-S1.py
```
`dev/accept/P2-W0/OC-S1.py` (exit 0, one `PASS <check>` per check, prints the final table): every key of `TYPE_LABELS` is
in `OFFLINE_CLASSES` and nothing else is; the printed table equals §4's table cell for cell (the expected dict is written
in the script from the spec, not read from the generated module); `OFFLINE_STREAMS` holds the §4 streams with their
classes; output is deterministic (generate twice, compare); using the generator on a temp copy of `schema/core` (copy the
tree to a temp dir, as `generate.outputs(schema_dir)` takes a directory) with one record class's `tl:offline` removed
raises `OfflineClassError` whose message names that class, with an unknown value (`sometimes`) likewise, and with a
multi-type class whose subclass values disagree likewise.

## Tests for the end run (TB writes them; this piece writes none)
`packages/tl-schema/tests/test_offline_classes.py`: every `TYPE_LABELS` type has a class; missing and unknown values raise;
multi-type class resolved by its subclass; output deterministic; the §4 table pinned. Mutants: missing annotation accepted
(fail-open default `full`); unknown value accepted; subclass resolution replaced by the parent class's value. Report
where each guard sits (file:line).

## Report requirements
Standard piece report (<= 60 lines): deviations first; which class carries each stream tag; pinned-list changes;
acceptance output (<= 5 lines per command).

## Escalation triggers
- *Blocked* if: a record type in `TYPE_LABELS` is not in the §4 table; a stream has no class to carry the tag without
  changing a field; the generator needs to touch `type_labels.py`; `just gen` changes any file other than the two new ones
  and the pins above.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
