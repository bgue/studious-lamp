# ADR-0010 — Module records: one envelope row, one typed side table, discovered through entry points

Status: proposed
Date: 2026-10-12
Deciders: P1-I1 supervisor (proposal); the orchestrator accepts or changes it before P1-I2 builds on it
Brief sections: §5.4, §6.2, §7, §9 (M2), §25.2, §27.2, §29.8

## Context
P1-I1 builds the first module (`engineering`: the standards registry, `Tag`, `TagClass`). Every Phase 1 and later module
follows the same storage and plug-in rules, so the first one sets them.

Brief §5.4 says each entity type has a table `cur_<module>_<class>` with the envelope columns, the typed columns of its
slots and the pset JSON. `tl new record-type` scaffolds exactly that (a class that is a `RecordEnvelope` with
`tl:current_state`, and a handler that appends `<Class>.Created` to a stream of its own).

Phase 0 built everything else on one table, `cur_core_record`, which holds the envelope of every record: links check
that both ends are rows of it, the pset service reads and rewrites its `psets_json` and `conformance`, the workflow
service reads and rewrites `status`, the query language compiles over it and `cur_pset_values`, the feed and the
webhook outbox name records by its ids. Extension types (P0-I8) were added to it by keeping their instances there.
A module record kept out of that table would get none of these services.

Nothing in `tl_core` could learn about a module: `default_registry()` lists projectors by hand, the generators read
`schema/core` only, and the event catalog reads `schema/core/events.yaml` only.

## Decision
1. **A module record is a row of `cur_core_record` and a row of the module's own table.** Its stream is created by
   `Record.Created` (the envelope: `record_type`, key, title, description), followed in the same append by the module's
   `*.Defined` event, which carries the typed fields. The module's table holds `id`, `scope` and the typed columns, not
   the envelope; readers join on `id`. The tables are generated from the module's LinkML classes (`tl:current_state`);
   the module's projectors write them, and also move the envelope row's `version`, `last_seq`, `updated_at` and, when an
   event carries them, `conformance` and `effective_schema_hash`.
2. **Module record types are created by module commands.** `CreateRecord` keeps refusing a type it does not know;
   `tl_core.services.records.create_module_record` is the shared helper the module commands use.
3. **A module reaches the platform through one entry point.** The group `throughline.modules` names a function that
   returns a `tl_core.modules.ModuleSpec`: the record types, a factory for the projectors, and two optional hooks
   (`bound_psets`, `numbering_patterns`). `default_registry()` registers the projectors after the core ones and before
   the outbox. A module that is installed and does not load is an error at first use, never a silent gap.
4. **Generators read modules.** `schema/modules/<m>/module.yaml` is the root of a module's LinkML. DDL is generated
   from the classes the module itself defines; the event catalog takes the module's `tl:event_type` classes together
   with the core ones, under the same `tl.core.` CloudEvents prefix. Pydantic models and JSON Schema are generated for
   the core root only until a module needs them.
5. **A record class can bind property sets.** `ModuleSpec.bound_psets` names the psets a record's class adds to it.
   `EffectiveSchema.psets_for`, `validate_psets`, `record_json_schema`, `form_metadata` and `evaluate` take the bound
   names; a bound pset applies whatever its `applies_to` says, is always engaged, and a bound pset with no values is a
   `class_required` issue at the pset's enforcement. The effective schema and its hash do not change; the events that
   evaluate conformance carry the bound names.

## Consequences
- Contracts changed: `ModuleSpec` and `create_module_record` are new core interfaces (`03-repo-and-toolchain.md` §7 is
  untouched). `validate_psets`, `record_json_schema`, `form_metadata`, `evaluate` and the `form_metadata` service gain an
  optional trailing argument. `RecordFacts` gains `bound`. `numbering_for(conn)` joins the file patterns with the
  patterns modules hold in the ledger; record creation and key detection in posts call it instead of `get_numbering()`.
- Brief §5.4 differs: the typed table has no envelope columns. A generated wide view per type (`v_<module>_<class>`)
  can present the joined row; it is not built in P1-I1.
- Every later module repeats the same steps: `tl new module`, LinkML classes with `tl:current_state` and
  `tl:record_types`, projectors that call `touch_record`, a `module.py` with `spec()`, an entry point.
- Gates affected: `schema/modules/**` and the `schema/core/annotations.yaml` note (`tl:record_types`) are schema merges
  (ADR-0008 decision 6).

## Alternatives considered
| Option | Why not |
|---|---|
| Full envelope in each module table (brief §5.4 and the scaffold as written) | Links, psets, workflow, queries and the feed would each need a second code path per module type, or a second copy of every row |
| Typed fields as a pset on the generic row (the extension-type way) | No typed columns or indexes for segments, class and status; the P1-I1 exit asks for parsed segment columns |
| Module events without a `Record.Created` | The record would not exist for links, feed and queries |
| Modules listed by hand in `default_registry()` | `tl_core` would import every module; a module could not be added without editing the core |
