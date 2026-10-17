# Document schema fixtures

Sample document schemas for the derivation pipeline (P1-I3, brief §9 M1): the JSON Schema a derived CSV or XLSX
is checked against, its version, a sample file that passes, and the header names a person's file is likely to use.
These are data, not LinkML; the pipeline loads them into `DocumentSchema` records.

## Files

| File | What it is |
|---|---|
| `<code>@<version>.schema.json` | The schema: JSON Schema 2020-12 for **one row**, plus an `x-throughline` block |
| `<code>@<version>.sample.csv` | A file that passes the schema. Its header uses the schema's property names |
| `instrument-index@1.0.0.invalid.csv` | The sample with one row wrong (row 6, `fail_action` is `OPEN`): the demo of P1-I3 |

| Code | Rows in the sample | Publish target |
|---|---|---|
| `instrument-index` | 40 tags in areas 47, 10 and 20 | `engineering.Tag` (key `tag_number`, title `service`, class `tag_class`) |
| `equipment-list` | 10 equipment items | `engineering.Tag` (key `equipment_tag`, title `description`, class `equipment_class`) |
| `line-list` | 10 process lines | none in Phase 1 (`target` is null) |

## How a row meets the schema

- A cell is text (`tl_core.derivation.Cell`). An **empty cell is an absent property**: leave the key out before
  validating. A property that must be present is listed in `required`.
- Every property is declared `"type": "string"`, so a row can be validated exactly as the extractor returns it.
  A number is a string with a `pattern`, and carries `"x-tl-type": "decimal"` so that the step after validation
  (the publish mapping) knows to convert it.
- `additionalProperties` is `false`: a column the schema does not name is an error on every row, which is how a
  misspelt or unmapped header is found. The extractor's `header_map` option renames a person's headers to the
  schema's names (see `x-throughline.header_aliases`).
- The tag number pattern is the shape of the Acme tag pattern (`{area}-{mnemonic}-{seq:4}`). Whether the area is a
  value of the `Area` list and the mnemonic a registered one is judged when the tag is created, not here.

## The `x-throughline` block

| Key | Meaning |
|---|---|
| `code`, `version`, `title` | The `DocumentSchema` identity. The file name is `<code>@<version>` |
| `target` | `{module, record_type, key, title, class}`: the record type a published row becomes and which property fills which field; null when nothing publishes |
| `unique` | Properties whose value must be different on every row (checked over the whole file, not by JSON Schema) |
| `header_aliases` | For each property, headers a person's file may use instead. Build the extractor's `header_map` option from it by inverting it: `{alias: property}` |
| `sample`, `invalid_sample` | File names of the sample files, beside the schema |

## Checks

`packages/tl-extract/tests/test_document_schema_fixtures.py` validates every schema, checks that each sample passes
and that `instrument-index@1.0.0.invalid.csv` fails on exactly one row, that the 40 tag numbers are distinct, fit the
Acme standards (`schema/fixtures/standards/co.acme.standards@1.0.0.yaml`: the area is in `Area`, the mnemonic is
registered, the class is the mnemonic's class) and that the aliases name real properties.
