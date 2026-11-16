# Runbook — inspections and checklists: plan, schedule, record, verify, reinspect, and what the refusals mean

Purpose: run inspections day to day: write a checklist, publish it, plan a hold point against an IWP, schedule and record it, verify it,
reinspect a rejected one, and read what each refusal means. Module: [quality](../modules/quality/README.md). Design:
[inspections.md](../build-spec/module-designs/inspections.md) (sections 1 to 10). Reference: [inspections.md](../reference/inspections.md).

## When to use
- A hold, witness, review or surveillance inspection is due on a work package, a tag, a document or another record.
- A question set (a checklist) must be fixed before inspectors run it.
- A recorded inspection failed and must be reinspected, or it must be cancelled because it is no longer needed.
- You need the inspections by state, point, area, inspector or work package, or an export for a report.

## Before you start
- Sign in (`tl login <name>`). Writes take the ledger from `--db` or `TL_DB` and the project from `--project`; reads take `--project` too.
- Words (`schema/settings/access-words.yaml`): reads need `quality.view`. Checklist create and edit, plan, schedule, record and reinspect
  need the `user` table word. Checklist publish, revise and retire, verify and cancel need the `controller` table word.
- Who holds which word: an account with the platform role `user` or `document_controller` holds the `user` word on every module by
  derivation (`schema/settings/module-roles.yaml`). The `controller` word needs an explicit grant:
  `uv run tl admin roles grant <who> --project P123 --module quality --role superuser --reason "<why>"`. The demo gives `sue` and `rob`
  that grant and `uma` only the derived `user` word.
- Keys: `P123-CHK-0001` (checklist), `P123-INS-0001` (inspection). A cancelled or retired record keeps its key.

## Checklists

### Create and edit
1. Write the questions as a JSON list. Each question has `id` (`q1`, `q2`, ...), `text`, `kind` (`yes_no_na`, `number`, `text`, `choice`),
   `required`, `unit`, `min`, `max`, `choices` and `fails_when` (`no` for a yes/no/n-a question, `out_of_range` for a number).
2. `uv run tl checklist create --project P123 --title "Hold check, flange make-up" --discipline piping --questions-file questions.json`
   prints `created P123-CHK-0001  version <v>`. The checklist is Draft. The file is read before it is parsed and refused over 256 KiB
   (`error: questions file is too large`).
3. `uv run tl checklist edit P123-CHK-0001 --project P123 --title "..."` changes a Draft. At least one field is needed (`nothing to change`).

### Publish
1. `uv run tl checklist publish P123-CHK-0001 --project P123` prints `published P123-CHK-0001  version <v>`. Publish refuses an empty or
   malformed question list and lists each problem after `the question list cannot be published: `.
2. A Published checklist never changes. An edit is refused (see the table).

### Revise and retire
1. `uv run tl checklist revise P123-CHK-0001 --project P123` copies it as a new Draft and prints `revised P123-CHK-0002  version <v>`.
   Publish the copy: publishing it retires `P123-CHK-0001` in the same step. One live revision per checklist; a second one is refused
   (`a revision of this checklist already exists`).
2. `uv run tl checklist retire <key> --project P123` retires a Draft or a Published checklist. A retired one takes no change.
3. Read them: `uv run tl checklist ls --project P123` (filters `--state Draft|Published|Retired`, `--discipline`, `--limit`) and
   `uv run tl checklist show <key> --project P123` (the question table).

## Inspections

### Plan
1. `uv run tl insp plan --project P123 --subject <KEY> --for <IWP-KEY> --title "Flange make-up, F16" --point hold`
   prints `planned P123-INS-0001  version <v>`. The state is Planned.
2. `--subject` is the record inspected (an IWP, a tag, a document, a letter). `--point` is required: `hold`, `witness`, `review` or
   `surveillance`. `--for` names the work package it serves (optional), `--area` and `--planned-on YYYY-MM-DD` are optional.
3. A subject you may not read is refused as a missing record: `error: no record <KEY>`. Nothing is written.

### Schedule
1. `uv run tl insp schedule P123-INS-0001 --project P123 --checklist P123-CHK-0002 --on 2026-12-01 --inspector user:uma` prints
   `scheduled P123-INS-0001  version <v>`. The state is Scheduled and the checklist version is pinned at this moment.
2. The checklist must be Published. Scheduling again (a new date or inspector) is allowed while Planned or Scheduled.
3. Readiness moves to `ok` once the inspection is Scheduled (see Readiness below).

### Record
1. `uv run tl insp record P123-INS-0001 --project P123 --answer q1=no --answer q2=yes --answer q3=5 --note "Gauge missing"`
   prints `recorded P123-INS-0001  version <v>`, then `result reject` and `punch 1`.
2. Answers are `--answer Q=VALUE` (repeat it) or `--answers-file answers.json` (a JSON list of `{"q", "value"}`, at most 256 KiB), not both.
   A number question takes a number; yes, no and n/a take the text. Answers are checked against the checklist version pinned at schedule.
3. The result is computed, not typed: `reject` when a required question fails, `conditional` when only an optional one fails, else `accept`.
   Each failed question raises one punch item (category A on a failed required question of a hold point, else B), linked to the
   inspection. Read them with `tl insp show` (the `Punch items` line) and `tl punch ls`.
4. Record works on a Scheduled inspection only. Its time is now; a planned date later than today is refused (`the time is before the
   day the inspection was planned`), so record on or after the planned day.

### Verify
1. `uv run tl insp verify P123-INS-0001 --project P123` prints `verified P123-INS-0001  version <v>`. Verify works on a Done inspection.
2. The person who recorded it may not verify it, even with the controller word (`the person who recorded an inspection may not verify it`).
   Another controller verifies it.

### Reinspect
1. `uv run tl insp reinspect P123-INS-0001 --project P123 [--planned-on 2026-12-05]` plans a new inspection that copies the title,
   subject, work package, point and area; it prints `reinspected P123-INS-0002  version <v>`. Its `show` names the first (`Reinspection of`).
2. Only a Done or Verified inspection with `reject` or `conditional` can be reinspected (`only a rejected or conditional inspection can be
   reinspected`). Schedule and record the new one as usual.

### Cancel
1. `uv run tl insp cancel P123-INS-0003 --project P123 --reason "Wrong subject"` prints `cancelled P123-INS-0003  version <v>`.
2. Cancel works on a Planned or Scheduled inspection, with a reason. A cancelled inspection counts in neither readiness number.

### Read
1. `uv run tl insp ls --project P123` lists inspections by key, one row each, with a `N of total` line. Filters: `--state Planned|Scheduled|Done|Verified|Cancelled`,
   `--point`, `--area`, `--inspector user:X`, `--subject <KEY>`, `--for <KEY>`, `--limit N` (default 200).
2. `uv run tl insp show P123-INS-0001 --project P123` prints the inspection, its answers and its punch items.
3. `uv run tl insp export --project P123 --format csv` (or `jsonl`) writes one row per visible inspection with the columns `number`,
   `subject`, `for`, `point`, `state`, `result`, `scheduled`, `done`, `inspector`, `punch_count`. The export holds the same rows as `ls`.
   `punch_count` is the number of punch items the result raised. It is not a live count of open punch items.
4. An inspection you may not read is absent from every list, every total and the export. Its `show` answers as a missing key.

## Terminal (TUI)
1. Start the TUI with `just tui` (project from `TL_PROJECT`, default `P123`), open the command palette and choose `inspections`.
2. The log lists the inspections. Keys: `s` cycles the state filter, `p` the point filter, `m` mine. Enter opens an inspection.
3. On an inspection: `v` verifies (Done only), `r` reinspects (Done or Verified; the handler refuses unless the result is reject or
   conditional), `x` cancels (Planned or Scheduled), `escape` closes, `F5` reloads. Only the keys the state offers do anything. A refusal shows `! <text>` on the status line
   and reloads the screen.
4. The TUI does not plan, schedule, record or run a checklist. Use `tl insp` (or the API) for those. The runner screen is follow-up work.

## Refusals and what they mean
Texts are copied from the handlers (`packages/tl-modules/quality/src/tl_mod_quality/handlers/`) and the CLI tests
(`packages/tl-cli/tests/test_cli_insp.py`, `test_cli_checklist.py`). The CLI prints `error: <text>`; `<KEY>` is the key you typed.

| Text | Meaning | What to do |
|---|---|---|
| `error: forbidden` (checklist verbs print `error: forbidden: ...`) | Your account lacks the word for this command | Ask a person who holds it |
| `no inspection <KEY>` | Unknown, in another project, or hidden from you (the same text for all three) | Check the key with `tl insp ls` |
| `no checklist <KEY>` | Unknown, in another project, or hidden from you | Check the key with `tl checklist ls` |
| `no record <KEY>` | The `--subject`, `--for` or `--checklist` key is unknown or hidden; nothing was written | Check the key |
| `an inspection that is <State> does not take <Command>; it needs <states>` | Wrong state (for example `RecordInspectionResult` on a Planned inspection; it needs Scheduled) | Make the move first |
| `a checklist that is <State> does not take <Command>; it needs <states>` | Wrong state (for example edit of a Published checklist; it needs Draft) | Revise it instead |
| `a checklist that is <State> cannot be scheduled; it needs Published` | The checklist is Draft or Retired | Publish or pick a Published one |
| `the question list cannot be published: <problems>` | The questions break a rule (each problem is listed) | Edit the Draft, fix each problem, publish again |
| `a revision of this checklist already exists` | A live Draft revision exists | Publish or retire it first |
| `nothing to change` | An edit with no field | Give at least one field |
| `a retired checklist accepts no further change` | The checklist is Retired | Create or revise another |
| `the person who recorded an inspection may not verify it` | You recorded it | Another controller verifies it |
| `the answers do not fit the checklist: <problems>` | An answer does not fit its question (each problem is listed) | Fix the answers and record again |
| `give --answer or --answers-file, not both`; `an answer is Q=VALUE, for example q1=yes` | Usage error (exit 2) | Fix the options |
| `error: answers file is too large` | The file is over 256 KiB | Split the answers |
| `only a rejected or conditional inspection can be reinspected` | The result is accept, or the inspection is not Done or Verified | Do not reinspect; plan a new one if needed |
| `the time is before the day the inspection was planned`; `the time is in the future` | Record time is outside the planned day or after now | Record on or after the planned day |
| `a cancelled inspection accepts no further change` | The inspection is Cancelled | Plan a new one |
| `that record names a subject that itself names a subject; plan the inspection against the work itself` | The subject sits two hops from another record | Plan against the work record itself |
| A refusal of the `--point` value (the allowed points are `hold`, `witness`, `review` and `surveillance`) | Bad `--point` | Fix the option |

## Readiness
The check `inspections_planned` runs for each IWP (`tl awp readiness show <IWP-KEY> --project P123`). It is `n_a` when no inspection
names the IWP and `quality.inspections.required_for_iwp` is off (the default). With the setting on, it is `blocked` until one is planned.
It is `blocked` while a linked inspection is still Planned, or while a hold point is Done with `reject` and has no reinspection.
It is `pending` while an inspection due before the IWP's planned start is not Done. It is `ok` once every linked inspection is Scheduled
or better. A conditional hold point does not block. Cancelled inspections count in neither number.
A fresh IWP shows `no readiness` until it reaches constraint-check and the awp worker has run (`tl awp worker --once`).

## What an agent may propose
- An agent (MCP) may call `propose_inspection` with `subject_key`, `title` and `point` (required) and optionally `for_key`, `area` and
  `planned_on`. Nothing is planned at once: the proposal is pending.
- A person who holds `quality.inspection.plan` accepts it: `uv run tl proposal ls`, then `uv run tl proposal accept <id>`. The inspection
  is planned as that person. Reject with `tl proposal reject <id>` ([proposal review queue](proposal-review-queue.md)).
- No agent tool schedules, records, verifies, reinspects or cancels. An agent account files only where it holds an explicit `user` grant
  (see [accounts and access](accounts-and-access.md)).

## The generator (demo data)
- `just demo-project dev/data/demo-project.db --sections core,engineering,awp,constraints,quality` prints `quality: <n> records, <m> events`.
  The quality section also builds three sample checklists (from `schema/fixtures/quality/checklists/`; the flange one is revised once) and
  18 inspections in fixed final states.
- The generator runs the real commands, so the generated data follows the same rules as the terminal.

## Verify the demo
- `just demo P2-INSP` runs clauses 1 to 7 on SQLite and on Postgres, and clause 7b (the generator) on SQLite (`dev/demos/P2-INSP.sh`).
  Each clause prints `PASS clause N: ...` only after its check succeeds. Postgres must be reachable at `TL_PG_URL` (`just dev up`).

## Not built yet
- The inspection runner screen (run a checklist one question per screen): follow-up slice T11.
- Checklist screens in the TUI (list and record) and the palette and navigation lines for them: follow-up slice T12 and T13.
- Scheduling and recording in the TUI: CLI only until the runner screen.
- The `--answers` export (one row per answer); the export has the inspection rows only.
- TUI filters `o` (open), `d` (due today or overdue), `h` (hold points) and by area; the log has `s`, `p` and `m`.
- Hook declaration of the module surfaces beyond what the S2 engine did (see [DEFERRED.md](../build-spec/DEFERRED.md)).
- Later (design section 11): instruments and calibration, witness guest sign-off, the full ITP, checklist import from a file, photos per
  answer, a hold-points-released guard on IWP closeout, an Inspections tab on the IWP, web twins.
