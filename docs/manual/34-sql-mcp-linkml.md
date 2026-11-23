# 34. SQL, MCP and LinkML [D]

## 34.1 Why a schema

A team of six links a schedule. The planner reviews structure. A site engineer reviews MEP. An agent proposes the rest. If
each keeps a private copy of a JSON file, you merge by hand and lose decisions. If they share a database, each person adds
rows and the review is a column. The trick is that everyone agrees on the shape of a row.

### The idea

**LinkML** is a way to write down the shape of data in one file. The file `schema/linkml/xray_4d.yaml` says what a 4D
dataset contains: what an assignment is, what an activity link is, which fields each has, which values a field may take.
From that one file, tools generate the other things you need:

| File | What it is |
| --- | --- |
| `xray_4d.yaml` | the schema; the single source of truth |
| `xray_4d.sql` | SQL tables, one per class, join tables for lists, foreign keys to `Activity(task_code)` and `Element(global_id)` |
| `xray_4d.schema.json` | a JSON Schema; the viewer and the command line check `links.json` against it |
| `examples/` | example datasets, checked when the files are regenerated |
| `generate.sh` | regenerates the SQL and the JSON Schema and checks the examples |

An **MCP** (Model Context Protocol) server is a program that gives an agent tools for a system, for example for a
database or for IFC files. So, "SQL or MCP" means: put the dataset in a database, and let people and agents read and write
rows with tools. The viewer does not need to be open.

## 34.2 Keys and statuses

Two keys hold everything together.

- An activity is its P6 **Activity ID** (`task_code`).
- An element is its IFC **GlobalId** (`global_id`).

Both survive a new XER and a re-exported IFC, so rows stay valid when the inputs change. Use one database, or one SQL
schema, per project model, because the keys are table-wide.

Rows that people and agents write have a **status** (this is the proposed, accepted, rejected and superseded of chapter 24):

| Status | Set by | Meaning |
| --- | --- | --- |
| `proposed` | a person, a rule or an agent | a suggestion with `source`, `confidence` and `reasons` |
| `accepted` | a reviewer, or a deterministic rule | current; the only status that drives the plan and is saved into the IFC |
| `rejected` | a reviewer | no; the activity or element is not suggested again |
| `superseded` | the system, when a newer row arrives | replaced for the same element and attribute (or activity and role); kept as history |

The `source` of a link is one of `native`, `property`, `attributes`, `override`, `suggested`, `manual`, `agent` and
`classifier` (the last for assignments). An agent writes `source = agent`, `status = proposed`, with a confidence and the
reasons in words. Nothing an agent writes counts until a person accepts it.

## 34.3 The tables

There are two kinds of row that matter for review.

- **Assignment**: element, attribute (`location`, `trade` or `zone`), value, source, confidence, reasons, status,
  `reviewed_by`, `reviewed_at`, `created_at`.
- **ActivityLink**: id, activity, role (`build` or `remove`), elements (a list, so a join table), source, confidence,
  reasons, split, rule, status, and the same review fields.

Around them are the `Activity` and `Element` tables, so a query can filter by dates, trade or class without reading XER or
IFC, and `Tie`, the elements two activities claim with equal strength.

Dates: schedule dates (`start`, `finish`, `data_date`) are `local_datetime`, written as P6 does, with no time zone. Record
timestamps (`created_at`, `reviewed_at`) have a zone.

## 34.4 Try it: read accepted links from SQL

This assumes you loaded the generated tables into a database (for example by running `xray_4d.sql` in SQLite or
Postgres) and imported a link dataset, such as the one the viewer's **Export links** wrote from FZK-Haus 4D.

Accepted links with one row per element:

```sql
SELECT l.id, l.activity AS task_code, l.role, e.elements_global_id AS global_id
FROM "ActivityLink" l
JOIN "ActivityLink_elements" e ON e."ActivityLink_id" = l.id
WHERE l.status = 'accepted'
ORDER BY l.activity, e.elements_global_id;
```

What is waiting for review:

```sql
SELECT 'link' AS kind, id, activity AS subject, source, confidence FROM "ActivityLink" WHERE status = 'proposed'
UNION ALL
SELECT 'assignment', id, element, source, confidence FROM "Assignment" WHERE status = 'proposed';
```

The current accepted location, trade or zone of each element, when there is more than one accepted row, is the newest:

```sql
SELECT element, attribute, value
FROM "Assignment" s
WHERE s.status = 'accepted'
  AND s.created_at = (SELECT MAX(created_at) FROM "Assignment" t
                      WHERE t.element = s.element AND t.attribute = s.attribute AND t.status = 'accepted');
```

To accept a proposal, update its status. Then export the rows back into a `LinkDataset` JSON and import it in the viewer
(chapter 28), or give it to the agent skill (chapter 33) as `--links`. The script needs only `model`, `activities`, `links`
(with `elements` as GlobalId lists) and `assignments`.

> Check: the table and column names in the queries come from the skill's SQL reference and the generated `xray_4d.sql`.
> The join table is named `ActivityLink_elements` with column `elements_global_id`. Confirm against your generator's version.

## 34.5 The JSON Schema

`xray_4d.schema.json` checks a `links.json` before you trust it. Any JSON Schema validator works. Use it in a pipeline to
refuse a dataset that has a bad status, a confidence outside 0 to 1, or a link with no elements (a link needs at least one).
Tie rows need at least two candidate activities.

## 34.6 Review with an agent in the loop

A working pattern:

1. The viewer or `xray-4d link` writes accepted links and open suggestions.
2. A script loads them into the database.
3. An agent with a SQL or MCP tool reads unlinked activities and elements, and writes `proposed` rows with reasons.
4. People review in the viewer (import the dataset) or with SQL (update `status`).
5. The accepted rows go back in as prior links (`xray-4d link --prior links.json`), then into the plan and the IFC
   (chapter 32).

The database is the record. The IFC is a product of it. If an IFC server cannot write what a row says, report the
difference; do not edit the row to fit the server.

## 34.7 Limits and gotchas

- `reviewed_by` is personal data. It stays in the dataset. It does not go into share links, packed pages or the IFC, unless
  someone opts in.
- Regenerate the SQL and the JSON Schema when the YAML changes (`generate.sh`). The TypeScript types in the viewer have a
  test that their field names match the JSON Schema.
- An element has at most one accepted build link. A removal link may follow it.
- One schedule per dataset; one dataset per model.

## See also

- Chapter 24: proposed against accepted. Chapter 28: the files the viewer reads and writes.
- Chapter 33: the agent that writes proposals. Chapter 32: the command line that uses the same dataset.
