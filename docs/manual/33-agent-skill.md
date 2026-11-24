# 33. The agent skill ifc-4d-schedule [D]

## 33.1 What an agent skill is, and why this one exists

Linking a schedule is mostly routine, and partly judgement. Rules can do the routine: the same level, the same trade,
the same zone. The judgement is the leftover: "Roof tiling" has no code that matches any element, but a person reading the
roof slab names knows what it builds. That reading is slow for a person with 300 activities. It is what a language-model
assistant, an **agent**, does well, if you check it.

### The idea

An **agent** is an AI assistant that can run programs and read files on your computer, for example Claude Code. A **skill**
is a folder of written instructions and small tools that you give such an assistant. The instructions tell it how to do
one kind of job, in what order, with which tools, and which rules it must keep. You do not run a skill. You install it and
then ask the assistant for the job in plain words: "link this schedule to this model".

The skill `ifc-4d-schedule` does the 4D job of chapters 24 to 26 outside the viewer. It:

- reads the P6 schedule and the IFC itself;
- links activities to elements with the same rules as the viewer, using a 4D configuration you give or one it drafts;
- proposes links of its own for what the rules leave over, each with its reasons and a confidence;
- writes the accepted links into a **copy** of the IFC (the work schedule, tasks with dates, task-to-element assignments,
  the logic between tasks, and `Xray_4D`), and into a copy of the XER as three activity user fields;
- writes an animation script that plays any part of the build in schedule order, and checks it with the viewer's own
  compiler.

The key rule is the one from chapter 24: the agent proposes, you decide. Proposals are written as `proposed`. Only links you
accept reach any file.

## 33.2 Install

A skill is a folder. Copy `skills/ifc-4d-schedule` from the repository into `.claude/skills/` of your project, or into
`~/.claude/skills/` to have it everywhere. Any agent that reads `SKILL.md` skills can use it, including Claude Code and
programs built on the Claude Agent SDK.

What it needs:

| Need | For |
| --- | --- |
| Python 3 | reading and linking the schedule, writing the XER |
| ifcopenshell 0.8.x (`pip install -r requirements.txt` in `scripts/`) | reading and writing the IFC |
| Node 18 or newer | checking animation scripts with the viewer's compiler |
| an IFC MCP server (optional) | writing the IFC through a connected server instead of the bundled tool |

To test the install, run `scripts/selftest.sh`. It runs every step on the FZK-Haus sample and prints `ok` with the folder
it used. Set `PYTHON=` to the Python that has ifcopenshell if your default one does not.

## 33.3 Try it: link the FZK-Haus schedule with an agent

Open your agent in the repository folder.

1. Ask: "Use the ifc-4d-schedule skill. Link `web/public/samples/fzk-haus.xer` to `models/AC20-FZK-Haus.ifc` with
   `web/public/samples/fzk-haus.4d.json`."
2. The agent reads both files and reports: the project, data date and activity count; the code types and values; the model's
   storeys and element counts by class; any 4D links already in the IFC.
3. It links by the configuration. You see how many links are accepted, how many activities have no elements and how many
   ties there are. For the sample, activities such as plaster, screed drying and services have no geometry and stay unlinked.
4. It looks at what is left and proposes. For each proposal it tells you the activity, the elements and why ("roof tiling
   covers the roof slabs Dach-1 and Dach-2"). Read them.
5. Tell it which to accept and which to reject. It records your decisions in the links file and runs the linker again so they
   stick.
6. It writes `model.4d.ifc`, checks it, writes `schedule.4d.xer` and reports counts, skipped items, files and checksums.
7. Open `model.4d.ifc` in the viewer (chapter 2). The 4D tab links come back as accepted (chapter 26).

## 33.4 The steps the skill follows

1. **Read both files.** `xer_read.py` and `ifc_read.py`, or the MCP equivalents.
2. **Get a configuration.** Yours, or a draft from step 1 that it shows you. Same format as the viewer's `.4d.json`
   (chapter 28).
3. **Link.** `link.py`. Strength order: links already in the IFC, per-activity overrides, then location, trade and zone. An
   element two activities claim equally is a tie and goes to neither.
4. **Propose** for activities with no elements, unlinked elements and ties. Proposals are `proposed`, never `accepted`. The
   agent shows them and you decide.
5. **Write the IFC** to a new file, with `apply_links.py` or through the IFC MCP server, then run `verify.py`. It must
   pass. An existing `Xray 4D` schedule is replaced; the agent asks first if you have not said so.
6. **Write the XER.** Three activity user fields are added to a copy:

   | Field | Holds |
   | --- | --- |
   | `4D Elements` | how many elements the activity builds |
   | `4D Status` | linked, proposed, tie, no elements or no geometry |
   | `4D Model` | the model file |

   Import it into P6 with "update existing project" so only those fields change.
7. **Write an animation** when asked, with `anim_write.py`. You can select by activity, trade, location, WBS, date range,
   critical path or status: "the roof", "everything critical in June", "the ground-floor masonry". The camera follows the
   work, captions give the date and activity, and work finished before the window is shown built. Choose the length in
   seconds or days per second. For a whole film with automatic camera work, use `xray-4d script` (chapter 32); the agent's
   writer is for parts of the build.
8. **Check** the script with `node xrayanim_check.mjs`. Every error is fixed before the file is handed over.
9. **Report**: accepted, proposed, rejected and tie counts, coverage, tasks written, what was skipped and why, the files
   and their SHA-256.

## 33.5 Rules the skill keeps

- Activities are keyed by P6 Activity ID, elements by GlobalId, never by name alone.
- Only accepted links are written into the IFC, counted in the XER fields, or used by animations.
- Never write `reviewed_by`. It is personal data.
- Every output is a new file. Running again gives the same file: the `Xray 4D` schedule and the `4D` fields are replaced, not
  duplicated, and nothing else is touched.
- IFC2X3 has no `IfcTaskTime`. Tasks and assignments are written, dates are not, and the report says so.
- P6 can link one pair of activities twice (SS and FF). IFC keeps one sequence per pair. The first stays; the other is reported.

## 33.6 With an IFC MCP server

If a server that can edit IFC is connected, the skill can write through it. The skill first looks for a tool that runs the
IfcOpenShell API or code on the model. Failing that, it uses specific tools to create entities and property sets. With
read-only tools it checks the model and writes with the bundled script on a local copy. It writes to a new path, makes one
call per task with its elements, and re-reads one task to check before doing the rest. If a failed call leaves half its
changes, it starts again from the original file.

## 33.7 Limits and gotchas

- The agent's proposals are only as good as the names in your model and schedule. Reading "Wand-Ext-ERDG-2" works if the
  agent knows German; a model with names like "Generic - 200" gives it nothing.
- An agent can be wrong, and sure of itself. That is why proposals are never accepted for you.
- The bundled linker (`scripts/link.py`) is a separate program in Python. It reads the same configuration format as the viewer.
  On the FZK-Haus sample it gives the same links as the viewer's linker (`web/src/schedule/link.ts`). That was checked. No
  other model has been compared, so look at the coverage and the ties on your own model.

## See also

- Chapter 24: why proposed is not accepted. Chapter 26: the rules the skill follows.
- Chapter 34: the SQL tables where proposals and decisions can live.
- Chapter 32: the command line for the whole film.
