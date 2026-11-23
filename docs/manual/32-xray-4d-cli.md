# 32. xray-4d command line [P][D]

## 32.1 Why a command line

The schedule changes every week. If the film and the link report are made by clicking, they get made when someone has
time. If they are made by a command, they can be made every Monday by a machine, and the only human work left is
looking at what it found. The command line also reaches things the viewer's tab does not: a baseline schedule, a
whole-job render with no browser window, and a full write of the schedule into a copy of the IFC.

### The idea

`xray-4d` is a Node program that runs the same steps as the 4D tab (chapters 24 to 27), one command per step. Every step
leaves a file that a person can open and correct, and every step is deterministic: the same inputs give the same files.
That is what makes a weekly run safe.

```
schedule.xer + model.ifc --link--> links.json (+ link-report.html, + model.4d.ifc)
links.json --plan--> build.4d.json --script--> film.xrayanim (editable)
                                   --render--> build.mp4
                                   --pack----> build.html (kiosk page, autoplay)
xray-4d all ... -o out/   every step in one run, stopping at the first failure
```

Run it from the `web/` folder of the repository (Node 22 needed):

```
node tools/xray-4d.mjs inspect schedule.xer
npm run 4d -- inspect schedule.xer --json
```

Every command has `--help`.

## 32.2 The commands

| Command | Does | Main output |
| --- | --- | --- |
| `inspect` | reads an XER and reports on it | a text report, or JSON with `--json` |
| `link` | links activities to elements | `links.json`, optional report and IFC copy |
| `plan` | builds the 4D plan | `build.4d.json` |
| `script` | the director writes an editable script | `film.xrayanim` |
| `render` | records the film headless, frame by frame | `build.mp4`, `.webm` or a PNG zip |
| `pack` | a single-file kiosk page that plays the film | `build.html` |
| `all` | link, plan, render and pack in one run | a folder |

Progress and warnings go to stderr, results to `-o`. For `link` and `plan`, leaving out `-o` writes to standard output.

### Try it: inspect the sample

1. From `web/`, run `node tools/xray-4d.mjs inspect public/samples/fzk-haus.xer`.
2. Read the report: project FZK-HAUS, data date 2027-05-19, 46 activities (40 tasks, 2 milestones, 4 finish milestones),
   64 relations, the code types Level, Trade and Phase with their values, the calendar with its holidays, and the WBS
   tree with the activity count of each node.
3. Add `--depth 3` to see more WBS levels. Add `--json` for a machine-readable summary (`xray-4d-inspect/1`).

A file with several projects needs `--project NAME`; without it, the error lists them.

### inspect

`inspect schedule.xer [--project NAME] [--depth N] [--json]`. The reader looks fields up by name, so a different P6 version
with other column order still reads. It takes UTF-8, or Windows-1252 as P6 writes it. Data problems become warnings; only
a file that is not an XER, or a project choice that cannot be made, stops the tool.

### link

```
xray-4d link model.ifc schedule.xer --config map.4d.json [--assignments a.json] [--prior links.json]
             [--id-property P] [--min-coverage 0.9] [--project NAME] [--write-ifc out.ifc] [--report r.html] -o links.json
```

It uses the six tiers of chapter 26. Two files feed it besides the model and schedule:

- `--config` is the configuration (chapter 28). JSON only; a `.yaml` file is refused with exit 3.
- `--assignments` is the mapping tool's export. `--prior` keeps the accepted links of an earlier `links.json`.

The coverage (share of elements linked) is printed to stderr. Below `--min-coverage`, the files are still written and the
exit code is 4. That makes the exit code a gate for a pipeline without hiding the output.

### plan

```
xray-4d plan model.ifc schedule.xer links.json --config map.4d.json [--view planned|actual|variance] [--baseline b.xer]
             [--window all|lookahead:6w|range:2027-05-01..2027-07-01] [--length 120s | --pace 1w=2s] [--write-ifc out.ifc]
             -o build.4d.json
```

The style comes from the configuration; flags override it. `--length` fits the film to a length. `--pace 1w=2s` fixes the
speed (one schedule week per 2 s). Give one of them, not both. `lookahead:6w` starts at the data date. A baseline `.xer` is
matched by activity code and gives the planned side of the variance view.

### script

```
xray-4d script build.4d.json --model model.ifc [--style calm|dynamic] [--labels N] [--no-explode] [--no-section]
               [--name NAME] -o film.xrayanim [--notes notes.txt]
```

This is the director of chapter 27. The plan carries no geometry, so it needs `--model`: the IFC itself, or the sidecar
JSON. The notes file has one line per decision: time, date, and what and why. The script is compiled once before it is
written, as a check.

### render and pack

```
xray-4d render model.ifc build.4d.json [--script film.xrayanim] [--size 1920x1080] [--fps 30] [--format mp4|webm|png] [--hud on|off] -o build.mp4
xray-4d pack   model.ifc build.4d.json [--script film.xrayanim] [--loop] [--title T] -o build.html
```

`render` needs Playwright with a Chromium (set `PLAYWRIGHT_MODULE` to its folder if it is not found). It packs the model and
plan into a temporary page with the same code as `xray-pack` (chapter 30), opens it in Chromium and runs the same
frame-by-frame exporter as the Script tab. The speed of the machine therefore does not change the video. `--fps` is a whole
number from 1 to 120. `png` writes a zip of frames. The last line on stdout is a JSON summary: file, frames, size, bytes,
milliseconds.

Without a GPU, the software renderer is slow. Measured on the FZK-Haus sample: 2 s at 320x180 and 12 fps in 12 s in all,
and 10 s at 640x360 and 24 fps in 54 s (about 0.2 s per frame). Larger sizes cost more.

`pack` is `xray-pack` with the plan, the autoplay and the kiosk options. The page plays itself, and a press or a wheel turn
stops it. `--loop` plays it again and again. If you give a script, its cues are added to the plan's film.

### all

```
xray-4d all model.ifc schedule.xer --config map.4d.json -o out/ [--no-render] [--min-coverage 0.9] [--write-ifc]
            [--script F] [--view V] [--window W] [--length T] [--size S] [--fps N]
```

It writes `out/links.json`, `link-report.html`, `build.4d.json`, `build.mp4` and `build.html`, and `model.4d.ifc` with
`--write-ifc`. It stops at the first failing step with that step's exit code.

> Check: `all` does not list `script` among its steps in `--help`. It passes `--script F` through. Confirm that `all` does
> not run the director on its own.

## 32.3 A weekly run

Every Monday: export the schedule from P6 as `schedule.xer`, then run this.

```
node tools/xray-4d.mjs all model.ifc schedule.xer --config map.4d.json -o out/ \
     --min-coverage 0.95 --view actual --window lookahead:6w --length 60s --size 1280x720 --write-ifc
```

Publish `out/build.mp4`, `out/build.html`, `out/link-report.html` and `out/model.4d.ifc`. The short look-ahead keeps the
render quick on a machine without a GPU. Exit code 4 fails the job when the model and schedule have drifted apart: someone
changed the schedule's codes, or the model lost its storeys. The remedy is a human one. Open `link-report.html`, then
update the configuration.

To keep human decisions across runs, pass `--prior links.json` (the file you reviewed and saved) to `link`, so accepted and
rejected links survive.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | ok |
| 1 | unexpected internal error |
| 2 | usage: unknown command or option, missing file |
| 3 | input: file missing, unreadable or of the wrong kind; a project that cannot be chosen |
| 4 | link coverage below `--min-coverage` |
| 5 | render failure: no Playwright or Chromium, the viewer did not start, the export failed |

## 32.4 IFC write-back

`link --write-ifc` and `plan --write-ifc` write a copy of the model with the schedule in it. The original bytes are
untouched. One block is inserted before the final `ENDSEC;`. A second write replaces only the 4D part, and rewriting gives
the same bytes.

| Entity | Content |
| --- | --- |
| `IfcWorkSchedule` | one, named `Xray 4D`; project name, schedule hash, data date, first start and last finish, planned or actual |
| `IfcTask` | one per linked activity and role: task code, name, milestone flag, construction or demolition |
| `IfcTaskTime` | scheduled start and finish, actual start and finish when present, critical flag |
| `IfcRelAssignsToControl` | the work schedule controls its tasks |
| `IfcRelAssignsToProduct` | build: the element is the task's output |
| `IfcRelAssignsToProcess` | remove: the elements are inputs of the demolition task |
| `IfcRelSequence` and `IfcLagTime` | logic between two written tasks: FS, SS, FF, SF and the lag |

An activity with no linked element in the file gets no task. IFC2X3 has no `IfcTaskTime`, so the command warns and skips
the IFC copy, and writes the other outputs. Use IFC4 or IFC4X3.

Reading back is automatic. `link` reads the model's own task assignments and treats them as native links with confidence 1.
A file written by `--write-ifc` links natively again, with no configuration.

## 32.5 Limits and gotchas

- The configuration is JSON. There is no YAML parser.
- The TypeScript reader is bundled on first use into a file that is not committed; it is rebuilt when `web/src/schedule` is
  newer. The first run takes a few seconds longer.
- `render` needs Playwright and a Chromium. Without them the exit code is 5.
- The viewer's 4D tab and the command line share the pure code but not the browser storage. Move work between them with the
  files of chapter 28.

## See also

- Chapter 26: the linking rules. Chapter 27: what the film shows.
- Chapter 30: `xray-pack`. Chapter 33: an agent that does the same work with a person's review.
