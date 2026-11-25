# 25. Mapping elements to location, trade and zone

## 25.1 Giving every element three labels [P]

A schedule says "Level 2, steel, zone B, erect frame". A model says "IfcBeam, 'HEB 240', Level 2". To connect them, both
sides must use the same three words: where, what kind of work, which part. If the model has no such words, no rule can
link the activity to the beams. The elements need labels first.

### The idea

Each element gets three labels, called **attributes** here:

- **location**: normally a storey ("Erdgeschoss", "Level 2").
- **trade**: the kind of work that builds it ("CONC", "STEEL", "MEP-MECH", "FACADE"). The default list is CONC, STEEL,
  MASONRY, FACADE, ROOF, MEP-MECH, MEP-ELEC, MEP-PLUMB, FINISHES and SITE. You can add your own.
- **zone**: a part of the site or building ("Zone A", "North wing").

One label on one element is an **assignment**. It has a value, a source (who or what gave it), a confidence, reasons and a
status (chapter 24: proposed, accepted, rejected, superseded). Only accepted assignments count.

The tool is the **4D** tab of the right sidebar. Open it with the tab, or with the command `4D mapping: open the 4D tab`.
On a phone it is a bottom sheet. The tab has three steps under its film bar (chapter 24). Mapping is the first one, **Map**.
Click **Map** to see its sections, top to bottom: **Values**, **Assign**, **Suggest** and **Coverage**. The step shows
"not started" until you have an accepted assignment, a count of "to decide" while suggestions wait, and a check mark when
it is done. A line at the top of the step reads "Manual assignments: N accepted, N proposed. Kept in this browser for this
model." It counts only the location, trade and zone labels you work with here, not the schedule links.

Do you need this step? Not always. The linker can read location from the storey and trade from a query. The FZK-Haus 4D
sample does exactly that and needs no assignments. Use the mapping tool when the model has weak class use, when the
schedule talks about zones the model does not name, or when you want labels saved into the IFC for other people.

### Try it

On the **FZK-Haus** sample (not the 4D one, so you start clean):

1. Open the **4D** tab and click the **Map** step. In **Values**, press **Seed from model**. Storey names become locations, groups with "zone" in
   their name become zones, and the classifier's disciplines become trades.
2. Open **Suggest** and press **Suggest**. The review list fills. Each row shows the element, the proposed value, a
   confidence and the reasons, highest first. A wall on the ground floor gets location "Erdgeschoss" at 0.90 ("the storey
   that contains the element").
3. Click a row. The element is selected so you can look at it. Press **Accept** or **Reject**.
4. To take the sure ones at once, use **Accept all above** and pick a confidence, for example 0.85.
5. Open **Coverage**. For each attribute you see how many elements have a value, have none, and have a proposal. Press
   **Select without** to select the elements that still have no accepted value, so you can see what is left.
6. Press **Colour** and pick location, trade or zone. Elements are tinted by value; grey ones have none. The colouring is
   temporary: it goes away when you leave the tab and comes back when you return.

> Picture: the 4D tab on Coverage, the house tinted by trade, grey elements still unassigned.

### Assign by hand

In **Assign**, type or pick a value, then give it to one of these:

| Target | How |
| --- | --- |
| The selection | select elements first |
| A criteria query | type a query as in the search bar (chapter 8); the count shows live and matches are tinted orange |
| A storey | every element of that storey |
| A selection set | a set from chapter 8 |

`Every storey` sets the location of every element from its storey in one click. `Clear` removes the accepted value of the
chosen attribute from the selected elements. Anything you do by hand is accepted at once, with source `manual`.

## 25.2 How suggestions are made

Suggestions use only evidence in the model. They never use the schedule.

| Attribute | Evidence | Confidence |
| --- | --- | --- |
| location | the storey that contains the element | 0.90 |
| zone | the zone group the element belongs to | 0.90 (0.70 with several zones) |
| trade | the IFC class from an editable table; a `class:material` row such as `IfcBeam:steel` wins | 0.70, or 0.85 with a material rule |
| trade | the classifier's discipline | 0.9 times its confidence |
| trade | the classifier's MasterFormat division | 0.85 times its confidence |

When two sources agree, the confidence goes up by 0.05 per extra source, never above 0.99. When they disagree, the
reasons say so ("Not MEP-MECH: ..."). Elements that already have an accepted value get no proposal. Spaces, openings and
proxies get no trade proposal, because nothing is built "as" them.

**Suggest** replaces the open proposals each time. Your accepted and rejected decisions stay.

The table of class to trade is editable (`Class to trade table`) and kept per model. If your trade list uses other names,
edit the table once and every later run follows it.

## 25.3 Values

The **Values** section of the Map step lists known locations, trades and zones, one attribute at a time. You can:

- rename a value. The rename changes every assignment that uses it.
- pick a colour for it. The same colours tint Coverage and, later, the film.
- add a value, or delete an unused one.
- see values that an import brought in.

## 25.4 Saving, reading back, exchanging

**Into the IFC.** When you save the IFC (chapter 19), the box **Include 4D location, trade and zone** writes the accepted
values as a property set `Xray_4D` with properties `Location`, `Trade` and `Zone` on each mapped element. The save adds
to the file and never edits what was there; saving with the box off removes the set. Proposed, rejected and superseded
records are never written. When the file is opened again, the viewer reads `Xray_4D` back and makes accepted assignments
with source `property`. A saved model reopens mapped. If your browser already holds a newer value for the same element and
attribute, yours stays.

**In the browser.** Assignments, value lists and the class table are kept per model in the browser (IndexedDB). They return
when you open the same model again. In a private window nothing is kept, and the tab says so. Nothing goes into share
links, saved views, presets or packed pages.

**As a file.** In the **Film** step, the section **Import / Export** holds **Export JSON**. It writes a LinkML dataset (chapter 28) with the model, its elements and all assignments of all
statuses. **Import JSON**, in the same section, merges one: records with new ids are added, and for the same element and attribute the newer
accepted record wins; the older becomes superseded. Importing the same file twice changes nothing. Rows that do not fit
the schema are skipped and counted.

`reviewed_by`, the name of who decided, is never written by the tool. It is personal data. It stays out of share links,
saved views, packed pages, the IFC and, unless you ask for it, the export.

## 25.5 Limits and gotchas

- Zones come from IFC groups recognised by "zone" in their name. A zone named otherwise you add by hand.
- A glb sidecar made by the Python converter carries no saved 4D values. Open the IFC itself.
- A federation suffix on a GlobalId (`~2`) is cut off in the export; the IFC write uses the model's own id.
- Seeding and suggesting are first drafts. Read the Coverage table before you trust them.

## See also

- Chapter 8: the query language used in Assign.
- Chapter 18: the classifier whose discipline feeds trade suggestions.
- Chapter 24: the three steps of the 4D tab.
- Chapter 26: linking the schedule to the labelled elements (the Link step).
