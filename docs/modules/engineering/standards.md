# Engineering module: the standards registry

Status: accepted. Brief §6.4, §6.3. Spec of the registry records, their commands and the loader.

## Entries
| Kind | Record type | What it holds |
|---|---|---|
| Code list | `engineering.CodeList` | `code` (`Discipline`), `label`, `definition`, `value_list_policy` (`closed`, `extensible`, `project_defined`), `adoption`, owner, effective dates |
| Code value | `engineering.CodeValue` | `code_list`, `code`, `label`, `meaning` (IRI), `crosswalk` (a company code), `origin` (`company` or `project`), `sort_order`, effective dates, `attributes` (a unit of measure: `ucum`, `dimension`) |
| Mnemonic | `engineering.Mnemonic` | `code` (`FV`), `label` (the meaning), `data.class_hint`, `data.discipline` |
| Numbering pattern | `engineering.NumberingPattern` | `code`, `data.template` (`{area}-{mnemonic}-{seq:4}`), `data.record_type`, `data.segments` (role and source of each segment), `data.allocate` |

Every entry carries an `edition` (`co.acme.standards@1.0.0`), a `lifecycle` (`active`, `superseded`, `retired`) and, when
superseded, the id that replaced it. A new edition is a new record; the old one is closed, never rewritten.

## Value lists
- `closed`: only company values. A project cannot add one.
- `extensible`: a project may add a value in its own scope; it must name a company value of the list as its `crosswalk`.
- `project_defined`: a project owns its values; a crosswalk is optional, and when given it must name a company value.
Resolving a value gives its label and the company code it stands for, so reports across projects use company codes.

## The standards file
One YAML file is one edition: `schema/fixtures/standards/co.acme.standards@1.0.0.yaml`. The model and its checks are
`tl_mod_engineering.document`; `tl_mod_engineering.loader` writes the entries as records: code lists with their values (sort order 10, 20, ... in file order), mnemonics, numbering patterns, then tag classes, through the registry commands in one unit of work and under one correlation id.

## Loading
`tl standards load FILE [--dry-run]` (admin) is `plan_load` then `load_standards`. Loading is idempotent: an entry whose code the
registry already holds (a list, mnemonic or pattern of that code in any edition, a value of that list, a tag class of that code)
is skipped and reported. A tag class that requires a pset the company schema does not define stops the load before anything is
written. A later edition of a standard is not loaded by this path: its entries change through the commands, one decision each.

## Commands
| Command | Effect | Refusals (error class) |
|---|---|---|
| `RegisterCodeList`, `RegisterMnemonic`, `RegisterNumberingPattern` | `Record.Created` + `Standard.Defined` | not company scope (`RegistryScopeError`), same code and edition (`DuplicateStandardError`), a template that does not parse or a second active pattern for a record type (`InvalidPatternError`) |
| `AddCodeValue` | `Record.Created` + `CodeValue.Defined` in company or project scope | unknown list, duplicate, closed list, crosswalk missing or not an active company value |
| `CloseStandard`, `CloseCodeValue` | `Standard.Closed` / `CodeValue.Closed`: superseded (names the replacement) or retired | already closed, replacement of another kind or list |
CLI: `tl standards load|ls|show|values|add-value|close|close-value` and `tl standards class define|ls|show|revise|close`.
