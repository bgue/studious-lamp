# Module spec: engineering (M2)

Status: draft (P1-I1 in progress). Brief sections: §6.4 (standards registry), §6.3, §9 M2, §27.5. Decision: ADR-0010.

## Purpose
The engineering module holds the company standards registry (code lists, mnemonics, numbering patterns) and the
engineering records that depend on it: `Tag`, the project-unique identifier of an engineered item, and `TagClass`, which
says which property sets a tag of that class must carry. Pages: [standards](standards.md), [tags](tags.md).

## Record types
| Type | Purpose | Table | Workflow |
|---|---|---|---|
| `engineering.CodeList` | A named list of coded values (`Discipline`) with its `value_list_policy` | `cur_engineering_standard` | none |
| `engineering.CodeValue` | One value of a list, in the scope that defined it (company, or a project with a crosswalk) | `cur_engineering_code_value` | none |
| `engineering.Mnemonic` | A tag prefix and its meaning (`FV`, flow control valve) | `cur_engineering_standard` | none |
| `engineering.NumberingPattern` | A parseable key convention (the tag number) | `cur_engineering_standard` | none |
| `engineering.TagClass` | A tag class with its required psets and ITR template references | `cur_engineering_tag_class` | none |
| `engineering.Tag` | A tag: number, class, parsed segments | `cur_engineering_tag` | `engineering.tag` (planned in T06) |

Every record is also a row of `cur_core_record` (ADR-0010). Keys: `CL:<code>@<version>`, `MN:<code>@<version>`,
`NP:<code>@<version>`, `CV:<list>.<code>@<version>`, `TC:<code>`; a tag's key is its number.

## Events
| Event type | Payload (see the catalog for the schema) | Projector |
|---|---|---|
| `Standard.Defined` | kind, code, label, definition, edition, owner, adoption, value_list_policy, effective dates, data | `engineering_standard` |
| `Standard.Closed` | lifecycle, superseded_by, effective_to, reason | `engineering_standard` |
| `CodeValue.Defined` | code_list, code, label, meaning, crosswalk, origin, sort_order, effective dates, attributes, edition | `engineering_code_value` |
| `CodeValue.Closed` | lifecycle, superseded_by, effective_to, reason | `engineering_code_value` |
| `TagClass.Defined` | code, label, family, required_psets, itr_templates, mnemonics, edition | `engineering_tag_class` |
| `TagClass.Revised` | changes `{field: [old, new]}`, reason | `engineering_tag_class` |
| `TagClass.Closed` | lifecycle, superseded_by, reason | `engineering_tag_class` |
| `Tag.Defined` | number, class, segments, pattern, number_status, violations, origin, supersedes, bound psets, conformance | `engineering_tag` |
| `Tag.Reclassified` | from_class, to_class, reason, bound psets, conformance | `engineering_tag` |
| `Tag.Superseded` | operation, superseded_by, reason | `engineering_tag` |

Each `*.Defined` event follows `Record.Created` in the same append. The catalog is `schema/modules/engineering/events.yaml`
(generated: `packages/tl-schema/src/tl_schema/generated/docs/event-catalog.md`).

## Open questions
- Feeding pset value lists from the registry (today the package lists are the source; the fixture mirrors two of them).
- Per-project adoption status of a standards edition (impact reports belong to P1-I8).
- Conversion factors between units of measure.
