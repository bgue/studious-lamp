# 26. Linking the schedule

## 26.1 Opening a schedule and linking it [P]

You have a schedule with 300 activities and a model with 20,000 elements. Joining them by hand would take weeks. Joining
them by guesswork would put the roof on in week 1. You want rules that do the sure part, a list of what is left, and a
way to look at every guess.

### The idea

The linker works through six sources, best first, and for every link it keeps the reason.

1. **Manual**: links a person or an agent already accepted. They win.
2. **Native**: the IFC already holds tasks (`IfcTask`) assigned to elements. Confidence 1.
3. **Property**: an element property holds the activity id, such as `Xray_4D.ActivityIds`. Confidence 1.
4. **Override**: your configuration names an activity's elements by a query or a list of GlobalIds. Confidence 1.
5. **Attributes**: the normal case. An activity's elements are those whose location, trade and zone equal the activity's
   own. Each of the three is optional. Confidence 0.6, 0.8 or 0.9 for one, two or three matching attributes.
6. **Suggested**: for activities that got nothing, the words in the activity name and WBS path are matched against storey
   names, zone names and class words (slab, column, wall, duct, door). These are only **proposed**.

Linking is the second step of the 4D tab, **Link** (chapter 24). It holds the sections **Schedule**, **Configure** and **Link**,
then the lists of decided links and of activities **Not in the model**. The tab opens on this step while no schedule is
loaded. Its state reads "not started" before a schedule, "not linked" before the first run, a count ("2 ties", "3 to
decide") while something waits for you, and a check mark when it is done.

An activity that names its elements (sources 1 to 4) does not also infer elements from attributes. Explicit beats inferred.

When two activities claim the same element, the stronger claim wins: manual, native, property, override, then three
attributes, two, one. If two different activities are equally strong, the element is a **tie**. It goes to neither and
is listed for a person to decide. A tied activity also gets no suggestion.

### Try it: link the FZK-Haus schedule by hand

The 4D sample already did this for you. To see the steps, repeat them.

1. Choose **FZK-Haus** in Sample Projects. Open the **4D** tab. It opens on the **Link** step, because no schedule is loaded.
2. In **Schedule**, press **Open .xer**, or drop an `.xer` file on the viewer. The sample file is
   `web/public/samples/fzk-haus.xer`. The summary shows the project (FZK-HAUS), data date (19 May 2027), 46 activities,
   their types, the code types (Level, Trade, Phase) with value counts and the user fields. A file with several projects
   shows a list: pick one and press **Use project**.
3. In **Configure**, set **Location from** to `Activity code: Level` and **Trade from** to `Activity code: Trade`. Leave
   **Zone from** at `Not used`.
4. Open the value table for location. The schedule says `EG` and `DG`; the model says "Erdgeschoss" and "Dachgeschoss".
   Type the model value in the box beside each schedule value. An empty box uses the schedule value as it is.
5. Open the trade queries. Each trade gets a query that says which elements it builds, for example for `MASON-EXT`:
   `class = 'IfcWallStandardCase' and name like 'Wand-Ext%'`. The live count shows how many elements match, and the
   matches are tinted orange while the box has focus. A zero means the query is wrong.
6. Press **Link schedule**. Read the result, described below.
7. In the suggestions list, click a row (it selects the elements), then **Accept** or **Reject**. The list shows the best
   confidence first and the reasons under each row.
8. Press **Open report** for the link report in a new window.

> Picture (4d-link-step): the Link step after a run: coverage table, ties, unlinked groups and the suggestions list.

Press **Save** in **Configure** to keep the setup for this model. It is also kept after every change.

### Reading the result

After a run the **Link** section shows:

- **Coverage**: elements and activities, each as linked, of, share.
- **Ties**: elements two activities claim equally.
- **Unlinked elements**, grouped by class and storey. Each group has **Select**, and **Select unlinked** selects all.
- **Activities without elements**, as a list "N activities without elements". Each row has **Not modelled**, and the list has
  **Mark all not modelled** (see below).
- **Suggestions** with **Accept** and **Reject**. The list shows the first 60.

The film bar at the top of the tab keeps a one-line summary of this result, for example "82 of 82 elements linked · 15 of 15
modelled activities have elements · 25 not in the model". It stays in view in every step.

### Activities with nothing in the model

Some activities build things the model does not contain: earthworks, drainage, plaster, services. They will never get an
element, however good the rules are. Left in the gap list, they hide the activities that really need your attention. So you
can say "the model has nothing for this".

- Press **Not modelled** beside an activity, or **Mark all not modelled** for the whole list. The bulk button leaves out
  activities that have a suggestion, because those might be linkable. Decide them first.
- A marked activity moves under **Not in the model (N)**, with a one-line explanation. **Back to list** undoes the mark.
- A marked activity is no longer a gap. The coverage counts only modelled activities, so the line reads "15 of 15 modelled
  activities linked; 25 not in the model". The link report lists them under their own heading.
- The mark belongs to the configuration (chapter 28). It is kept per model and travels with the exported `.4d.json`.
- While a marked activity is under way, the film's on-screen display adds "Also under way (not in the model): A, B +N more"
  under the list of current activities (chapter 27). It names at most two, then counts the rest.

The FZK-Haus 4D sample has its 25 such activities marked. The marks come from its configuration file
(`fzk-haus.4d.json`), not from the schedule: open the same `.xer` without that configuration and nothing is marked until you
mark it.

The **link report** is one page with no scripts. It shows coverage by trade and by first WBS level, elements with no
activity (each group with the query that selects it, so you can paste it into a trade query), activities with no
elements, ties, links to review, and checks on the schedule itself: open starts and ends, actual dates after the data
date, work started before a predecessor finished, negative float, finish before start, and "built before support" (a
wall that starts before the slab beneath it). The checks are listed, never fixed.

## 26.2 Review state and what is kept

Each link has a status: proposed, accepted, rejected. The linker keeps your decisions when you run it again.

- An accepted suggestion, or a manual link, goes back in as a prior link and stays accepted.
- A rejected link goes back in too, so the activity gets no new suggestion.
- Links the configuration makes again (attributes, overrides, and property or native links from the model) are not kept.
  They follow the configuration and the model, so a changed rule changes them.
- An open suggestion is made again on every run. **Reopen**, under **Decided links**, sets a link back to proposed.

Only accepted links drive the plan and are written into the IFC. Nothing proposed ever reaches the film.

### Remove links

An activity can demolish instead of build. In the configuration, an activity with `role: remove` removes the elements it
matches, existing ones included. In the plan such an element is existing, then active (fading out), then removed.

### Splitting one activity over its days

"Ground floor masonry" is one activity over three weeks. You do not want 40 walls to pop in on the first morning. A
**split** rule spreads the elements over the activity's duration, in order:

| Rule | Order |
| --- | --- |
| none | all together |
| sweep x, y or z (or minus) | along an axis, by element centre |
| by storey | bottom up |
| by name | natural order (Pour 2 before Pour 10) |

Neighbouring slices overlap a little so the work looks continuous. Split rules are per trade or per activity in the
configuration, with `*` as the default. In the sample, external and internal masonry, rafters and windows sweep along x.

## 26.3 Save the links into the IFC

In the **Film** step, press **Save IFC with 4D links**. It opens the usual Save IFC dialog (chapter 19) with the 4D box on. The `Xray_4D`
property set gains **ActivityIds**: the task codes of the element's accepted build links, sorted and comma separated
(`A1010,A1040`). Remove links are not written. A task code that contains a comma or semicolon is skipped.

When you open that IFC again, the viewer reads `Xray_4D.ActivityIds`. **Link schedule** then gives those links back as
accepted, confidence 1, source `property`. You need the schedule loaded and no configuration. The links travel with the
model.

The full `IfcWorkSchedule` and `IfcTask` write-back, so other 4D programs can use the links, comes from the command line
(chapter 32).

## 26.4 How it works

The linker sees the model as a flat list: GlobalId, class, name, storey, zone, properties, bounding box, discipline and
material. It sees the schedule as activities with codes, user fields, a WBS path and dates. The configuration says
where location, trade and zone live on each side, and how values translate. Schedule sources are an activity code type, a
user field, a WBS level, a pattern on the WBS path or a pattern on the activity name. Model sources are a property, the
storey, the zone or the discipline. Accepted assignments from chapter 25 beat model properties.

Everything is deterministic. The same schedule, model and configuration give the same links, byte for byte.

## 26.5 Limits and gotchas

- The configuration is a JSON file, not YAML. A zone given as a box or a set is not supported; a zone is an IfcZone, a
  property or an assignment.
- The tab picks one source per attribute. A configuration file with several sources keeps them and shows them, and only
  the first is edited. The `activities` overrides and the model side (`config.model`) are read from the file and not
  edited in the tab.
- A baseline `.xer` is not loaded in the viewer yet. The command line takes one.
- Files above 24 MB are not stored in the browser; the configuration and links are.
- The sample's key trick is the trade query. If a trade has no query and the model gives no trade, its activities find
  nothing.

## See also

- Chapter 24: the three steps of the 4D tab.
- Chapter 25: labelling elements before linking (the Map step).
- Chapter 27: turning accepted links into a film.
- Chapter 28: exporting links and configuration. Chapter 32: the same steps on the command line.
