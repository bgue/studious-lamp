# X-ray 4D linking schema (LinkML)

`xray_4d.yaml` is the source of truth for the data that links P6 schedule activities to IFC elements: the location / trade /
zone **assignments** of elements, the **activity links** built from them, and the **ties** left for a person. Design:
[docs/design/4d-xer-animation.md](../../docs/design/4d-xer-animation.md).

| File | What |
| --- | --- |
| `xray_4d.yaml` | the LinkML schema (tree root `LinkDataset`) |
| `xray_4d.sql` | generated SQL tables (`gen-sqltables`): one table per class, join tables for lists, foreign keys to `Activity(task_code)` and `Element(global_id)` |
| `xray_4d.schema.json` | generated JSON Schema: `links.json` written by the viewer and `xray-4d` validates against it |
| `examples/` | example datasets (validated by `generate.sh`) |
| `generate.sh` | regenerate both outputs and validate the examples |

Working in SQL / MCP:

- Keys are stable across updates: an activity is its P6 Activity ID (`task_code`), an element its IFC `GlobalId`. A new XER
  or a re-exported IFC keeps every assignment and link.
- One database (or SQL schema) per project model: `Element.global_id` and `Activity.task_code` are table-wide keys.
- People and agents write `Assignment` and `ActivityLink` rows with `status = proposed` and `source` (`agent`, `manual`, ...),
  `confidence` and `reasons`; review sets `accepted` / `rejected`; a newer row for the same element and attribute (or activity
  and role) marks the old one `superseded`. Only accepted rows drive the 4D plan and are saved into the IFC (`Xray_4D`
  property set, `IfcTask` + `IfcRelAssignsToProcess`).
- `reviewed_by` is personal data: it stays in the dataset, never goes into share links or packed pages, and into the IFC only
  by explicit opt-in.
- Dates: schedule dates are `local_datetime` (no zone, as P6 writes them); record timestamps (`created_at`, `reviewed_at`)
  are zoned.

The TypeScript side is `web/src/schedule/types.ts` (`FourDLinks` and friends); `web/tests/fourd-links-schema.test.ts` checks
that its field names match the generated JSON Schema.
