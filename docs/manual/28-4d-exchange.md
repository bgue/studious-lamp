# 28. Exchanging 4D data

## 28.1 Files in, files out [P]

A planner wants to keep a setup for next week's schedule. A colleague wants to review links on another machine. A database
team wants every link in a table. The viewer keeps its work in the browser, which is private to that machine. To share
work, you need files.

### The idea

4D uses three kinds of JSON file. Two of them end in `.4d.json`, which is confusing, so here are all three side by side.

| File | What it holds | Written by | Read by |
| --- | --- | --- | --- |
| Configuration (`xray-4d-config/1`), for example `fzk-haus.4d.json` | what the schedule's codes mean, value translations, trade queries, split rules, activities marked not modelled, film style | **Export .4d.json** in Configure (Link step) | **Import .4d.json**, or drop it on the viewer; `xray-4d --config` |
| Link dataset (LinkML) | model and schedule references, activities, elements, assignments, links, ties | **Export JSON** (mapping; Film step, Import / Export), **Export links** (links; Link step) | **Import JSON**, **Import links**; `xray-4d --prior`, `--assignments` |
| 4D plan (`xray-4d-plan/1`), for example `build.4d.json` | per element: states over time, the time map, milestones | `xray-4d plan` | `xray-4d render`, `pack`, `script`, and packed pages (`xray-pack --plans`) |

The configuration is a recipe. The link dataset is the work you reviewed. The plan is a calculation from both, and you can
rebuild it at any time. Keep the first two; the third follows.

The 4D tab cannot open a plan file. It builds its own plan from the accepted links when you press **Play**, and keeps it in
memory. Plan files are for the command line and for packed pages.

### Try it

1. Choose **FZK-Haus 4D** in Sample Projects. Click the **Link** step. In **Configure**, press **Export .4d.json**. You get the configuration the
   sample was built with.
2. In the **Link** section of the same step, press **Export links**. You get a link dataset: schedule, activities, links, ties and unlinked lists.
3. Open the dataset in a text editor. Find a link: it has an id like `ln-A1200-build`, an activity, a role, a list of
   GlobalIds, a source, a confidence, reasons and a status.
4. Reload the page and choose **FZK-Haus** (the one without 4D). In the **Link** step, in **Schedule**, open the sample's `fzk-haus.xer` (it
   is in `web/public/samples` of the repository). Then press **Import .4d.json** and **Import links** and pick your two
   files. The setup and the reviewed links come back.

### Rules for importing

- **Import links** replaces the links on screen and merges the dataset's assignments into the mapping tool.
- **Import JSON** in the **Import / Export** section of the Film step reads only the assignments of any such file. For the same element and
  attribute, the newer accepted record wins (by review time, else creation time). The older becomes superseded. Importing
  the same file twice changes nothing.
- A file that names a different model is merged with a warning. Check that it is the model you meant.
- Rows that do not fit the schema are skipped and counted.
- An older mapping-only export has no schedule block, or a marked placeholder; both read as no schedule.

### Keys keep the work

Records point at elements by their GlobalId and at activities by their P6 Activity ID. A new `.xer` from next week, or a
re-exported IFC with the same GlobalIds, finds the same links. Changed activities keep their decisions; new activities
arrive unlinked. This is why you can run the linker every week without losing a month of review.

## 28.2 What the dataset contains

The LinkML dataset has these parts. The schema is in `schema/linkml/xray_4d.yaml`; chapter 34 shows how to use it.

- `model` and `schedule`: which model (identity key, file name, hash, IFC schema) and which schedule (file hash, project,
  data date).
- `activities`: code, name, WBS path, type, status, start, finish, and the location, trade and zone of each.
- `model_elements`: class, name, storey and the three labels of each element.
- `assignments`: every location, trade and zone record, with source, confidence, reasons and status.
- `links`: activity, role (build or remove), elements, source, confidence, reasons, split, rule and status.
- `ties`, `unlinked_activities` and `unlinked_elements`: what is left for a person.

Schedule dates carry no time zone, as P6 writes them. Timestamps of records (`created_at`, `reviewed_at`) do.

### Privacy

The name of who reviewed a record (`reviewed_by`) is personal data. The viewer never writes it. If another tool puts it
in a dataset, it stays in the dataset. It never goes into share links, packed pages or the IFC unless you opt in.

## 28.3 Reading a configuration

The sample configuration is short enough to read whole. Its parts, in order:

- `schedule`: which project, and where location and trade live in the schedule. The sample says `{ "code": "Level" }` and
  `{ "code": "Trade" }`: the activity code types of those names. Other sources are a user field, a WBS level, a pattern on
  the WBS path and a pattern on the activity name.
- `model`: where the same labels live on the model side. The sample reads the saved property `Xray_4D.Location` first and
  falls back to the storey; for trade it reads `Xray_4D.Trade`.
- `values`: translations from schedule values to model values, such as `EG` to `Erdgeschoss` and `DG` to `Dachgeschoss`. A key
  written between slashes is a pattern: `/^L(\d+)$/` with the target `Level $1` turns `L3` into `Level 3`. With no match,
  the schedule value is used as it is.
- `tradeQueries`: one query per trade in the query language of chapter 8. The sample has twelve, from `CONC-SLAB` to
  `RAILINGS`.
- `activities`: exceptions for one activity: a query, a list of GlobalIds, a `role` of `remove`, or a `split`. The mark
  **Not modelled** (chapter 26) is stored here too, as `notModelled: true`. The sample marks 25 activities this way.
- `split`: how elements of an activity appear over its days (chapter 26). `*` is the default.
- `style`: the film options of chapter 27, including the trade colours.

Because the configuration holds queries, and queries depend on names in the model, a configuration is tied to a family of
models, not to one file. Keep one per project, next to the schedule export, and edit it when the model changes.

## 28.4 Limits and gotchas

- The configuration is JSON only. A YAML configuration is refused by the command line.
- The tab edits one source per attribute; a file with more keeps them, but only the first is edited in the tab.
- A mapping-only export has no schedule. The links export has one.
- The sidecar of a glb carries no saved 4D values. Always keep the IFC.

## See also

- Chapter 26: where the exports are made. Chapter 29: what a share link carries, and that 4D is not in it.
- Chapter 32: the command line reads and writes the same files.
- Chapter 34: the same dataset as SQL tables.
