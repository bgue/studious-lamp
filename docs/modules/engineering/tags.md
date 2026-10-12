# Engineering module: tags and tag classes

Status: accepted. Brief §9 M2, §27.5. Spec of the records and of the commands, import and reports that serve them.

## Tag
A tag is the project-unique identifier of an engineered item. Its number is its record key (`47-FV-1001`); its title is the
service description. The number is checked against the registry numbering pattern for `engineering.Tag`:
- it must fit the pattern (`{area}-{mnemonic}-{seq:4}`: the sequence is written with four digits);
- the area must be a value of the `Area` list (company, or the project's own);
- the mnemonic must be a registered, active mnemonic.
The parsed segments are kept as typed columns: `area`, `mnemonic`, `sequence`, and every segment in `segments`. A number that
breaks the pattern is refused, except in a bulk import that accepts violations: it is stored with `number_status` `violation`
and the list of problems.

## Tag class
A tag class (`ControlValve`) names the property sets a tag of that class must carry (`required_psets`), the mnemonics that
normally identify it, and ITR template references (resolved by the quality module in Phase 3). The class binds psets by name:
- a bound pset with no values is a `class_required` issue at the pset's enforcement (non-conformant for `required`);
- the pset's own property rules (`required_in_states`) apply as for any record;
- adding a required pset to a class is a *constraining* change (brief 27.5): existing tags are flagged, nothing is rewritten.

## Rename, split, merge
Each creates new tags that supersede the old ones: the old tag leaves service (workflow state `Superseded`), a `supersedes`
link runs from the new tag to the old, and `Tag.Superseded` records the operation and the reason. Links to the old tag stay on
the old tag; they are not moved automatically.

## Workflow
`engineering.tag` (fixture `schema/fixtures/workflows/engineering-tag.yaml`): Planned, Design, Installed, Commissioned, Deleted,
Superseded. `design`, `install` and `commission` carry a conformance guard (`max_status: warning`): a tag cannot move on while
its class's property sets are missing. `supersede` is run by rename, split and merge.

## Commands
| Command | Effect |
|---|---|
| `CreateTag` | `Record.Created` + `Tag.Defined`, then `Pset.ValuesSet` for each pset given. The number must fit the pattern |
| `RecordTag` (admin) | As `CreateTag`, but a number that breaks the pattern is kept with `number_status` `violation` and its problems |
| `ReclassifyTag` | `Tag.Reclassified`: the new class binds its own psets; conformance is recomputed |
| `RenameTag`, `SplitTag`, `MergeTags` | New tag(s), `supersedes` links, `Tag.Superseded` and the `supersede` transition on the old ones, all under one correlation id |
Generic commands allowed on a tag (ADR-0010 addendum): `UpdateRecord` (title, description), `SetPsetValues`, `TransitionWorkflow`,
`AddLink`, `SuggestLink`, `AttachFile`. `VoidRecord` is not: a tag is retired by its workflow.

## Bulk import
`tl tag import FILE --mapping TEMPLATE --project P` reads a CSV with a mapping template (`dev/seed/templates/tag-list-instrument-index.yaml`
is the example; `dev/seed/legacy/instrument-index.csv` a sample), compares it with the project's tags and prints the plan:
`new`, `changed`, `unchanged`, `removed` (in the project, not in the file; never touched) and `invalid`. A row is invalid when its
cells cannot be read, its number is blank or repeated in the file, or its number is held by an ended (superseded or deleted) tag:
a number is never reused. `--apply` (admin) writes the plan in one unit of work, all or nothing, with source `import:<job>`; a
number that breaks the pattern is kept as a violation with origin `import`. `--skip-invalid` leaves the invalid rows out.

## Reports
`tl tag report summary` (tags in service by class and state with stored conformance counts), `missing` (what each tag lacks now,
evaluated against the current schema) and `violations` (numbers that break the pattern).
