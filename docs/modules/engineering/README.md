# Module spec: engineering (M2)

Status: accepted (built in P1-I1). Brief sections: §6.4 (standards registry), §6.3, §9 M2, §27.5. Decision: ADR-0010.

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
| `engineering.Tag` | A tag: number, class, parsed segments | `cur_engineering_tag` | `engineering.tag`: Planned, Design, Installed, Commissioned, Deleted, Superseded |

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

## Who can do what
| Action | Entry points | Access |
|---|---|---|
| Load or close standards, add or close a company code value, define, revise or close a tag class | `tl standards ...`, `tl standards class ...`, `POST /commands/Register*`, `AddCodeValue`, `Close*`, `DefineTagClass`, `ReviseTagClass` | admin (`admin.command.<Name>`, `require_admin`); a project value on an extensible or project-defined list is open to any signed-in person |
| Create, reclassify, rename, merge a tag | `tl tag ...`, `POST /commands/CreateTag`, `ReclassifyTag`, `RenameTag`, `MergeTags` | any signed-in person (split: CLI only) |
| Keep a tag number that breaks the pattern | `tl tag create --allow-violation`, `POST /commands/RecordTag`, `tl tag import --apply` | admin |
| Read standards, classes, tags, reports | `tl standards ls/show/values`, `tl tag ls/show/report`, `GET /standards`, `/tag-classes`, `/projects/{p}/tags`, MCP `list_code_values`, `list_tag_classes`, `get_tag`, TUI `F8` | any signed-in person; agents may read |
| Change a registry record or a tag class with a generic command | none | refused for everyone: the registry records allow no generic command (ADR-0010 addendum) |

An agent never changes a record directly: its tag changes are proposals a person accepts. A tag's `origin` is set by the
server (`created`, `import`, `rename`, `split`, `merge`), never by the caller.

## Limits
Lists and texts in a command are bounded (`tl_mod_engineering.limits`: 500 items in a list, 50 psets, 200 properties of a
pset, 20 pattern segments, 128 characters in a number) and the API refuses a `/commands/` body over 1 MiB (413).

## Open questions
- Feeding pset value lists from the registry (today the package lists are the source; the fixture mirrors two of them).
- Per-project adoption status of a standards edition (impact reports belong to P1-I8).
- The wide per-type view `v_engineering_<class>` that ADR-0010 requires before the first flat consumer (P1-I8 lake marts); today reads join `cur_core_record` in `registry.py`.
- Loading a second edition of the standards: the loader skips entries whose code exists (any edition); changes go through the commands.
- Conversion factors between units of measure.
