# Engineering module: the standards registry

Status: draft. Brief §6.4, §6.3. Spec of the registry records; commands and loader arrive in P1-I1 T03.

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
`tl_mod_engineering.document`; `tl standards load` (T09a) writes the entries as records, skipping the ones the ledger has.
