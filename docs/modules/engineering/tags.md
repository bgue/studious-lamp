# Engineering module: tags and tag classes

Status: draft. Brief §9 M2, §27.5. Spec of the records; the commands arrive in P1-I1 T06 and T07.

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
