# 18. Classifying elements

A model arrives with 20,000 elements and no trade on any of them. You need to know which are mechanical, which are structural,
which belong to the piping contractor. Doing that by hand takes days, and two people will draw the line in different places.
A check, a quantity sum or a query that depends on the answer is only as good as the labels.

This chapter covers the discipline and its review. The other questions (who builds it, is it outside, when is it built) are
facets, chapter 18A. Concrete elements get extra data, chapter 18B.

## 18.1 Run rules and a decision model

### The idea

Classifying means giving every element three labels: a **discipline** (for example `MEC`, mechanical and HVAC), a
**sub-discipline** (`DUC`, ductwork) and, for building elements, a **MasterFormat division** (`23`, heating and ventilating).
The labels come from a **code list**: a fixed list of allowed values called the schema. An answer outside the list cannot
happen, so a later query never meets a free-text value.

The viewer decides cheapest first, the way a clerk sorts mail. A letter with a clear address goes straight to its box. Only the
odd ones go to a person who has to think. Here the steps are:

1. **Your own answer** (a manual override or a committed review) always wins.
2. **Rules.** A built-in table of IFC classes and name hints. An `IfcDuctSegment` is HVAC; a column is structural; a pipe follows
   its system name (sprinkler, chilled water, process). A rule that is at least 0.85 sure is final: nothing else is asked.
3. **The signature cache.** Many elements are twins: same class, same type name, same material, same storey kind. The viewer
   decides once per kind (one **signature**) and reuses the answer. A model of 5,000 elements needs tens of questions, not thousands.
4. **A decision model**, for the kinds the rules left open. It does not write prose. It answers typed questions
   ("which of these 11 disciplines?") and gives a probability for every option. That probability is the **confidence**.

Why a decision model and not a chat model? A chat model writes text that must be parsed, and its "I am 90 % sure" is whatever
it wrote. A decision model can only pick from your list, and its numbers are real probabilities.

An answer **needs review** when any of its three confidences is below the minimum confidence (default 0.6), when the top two
options are close (under 0.15 apart), or when the model is unsure whether the element is a building element at all.

### Try it

Use the **Process plant** sample. It has pumps, vessels, piping, paving and kerbs, which makes the rules do real work.

1. Open **Sample Projects** and choose **Process plant**.
2. Open the **Classification** tab of the right sidebar. On a phone it is a bottom sheet. If the sidebar is folded, press `]`.
3. Keep **Provider** on its default (rules and cache only). Click **Classify all**.
4. Read the results table: element, discipline, sub-discipline, division, confidence, top 2, source. Most rows say *rules*.
5. Click **Colour by discipline**. The plant is tinted by trade and the legend lists the codes.
6. Click **Select needs review**. Only the elements the rules were not sure about are selected.
7. In the search bar type `count where discipline = 'MEC'`. The count comes from the classification, because the results are
   written back to the elements as properties.

With rules alone on this plant, nothing is left unresolved: 214 elements are civil site works (paving, kerbs, fence posts,
drain trenches, equipment foundations), 429 are piping and 428 mechanical.

Now try the decision model. In **Provider** choose **Decision model (in browser, WebGPU)**, click **Test model**, then
**Classify all**. The first use downloads the model weights (87 MB for the default) and the browser keeps them. Set **Rules and
model** to *off* if you want to see the model answer every kind of element.

### How it works

**The decision model.** The default is a small zero-shot language-inference model (a DeBERTa family model from Hugging Face)
that runs in your page. For each option it reads the element's description (class, type, name, key properties, system,
material, storey) as a premise and a sentence such as "This building element belongs to the Mechanical and HVAC discipline" as a
hypothesis, and rates how well they fit. The ratings of all options become probabilities. The element data stays in the page;
only the model files are downloaded. With WebGPU it is fast. Without it the model runs on the processor and the tab says so.

**Other providers.** The tab also offers Decision 3.0 d3-edge (in the browser with WebGPU after a large download, or on a
server of your own), a small chat or embedding model in the browser (WebLLM) and Jev, a model reached over HTTP. Jev needs an
endpoint and an API key. The key is kept in the tab or, if you choose, on this device. It is never part of any file the viewer
writes (see 19.4). A browser cannot call an endpoint that forbids cross-origin requests; run it through a proxy of your own.

**Confidence and calibration.** A small model is timid: with 11 disciplines its top probability is often 0.2 to 0.5, so
with the default limit of 0.6 almost every answer needs review. **Calibrate on rules** corrects this. It takes the kinds of element
that a final rule labels, lets the model answer them, and fits one temperature per question so that "70 % sure" means right
about 70 % of the time. The chosen option never changes, only the number. The rules are a proxy for the truth, not the truth,
so a model that agrees with a wrong rule looks worse than it is. **Calibrate on confirmed** (18.2) uses your own answers instead.

### Choices and settings

| Setting | What it changes |
| --- | --- |
| **Provider** | Rules and cache only, decision model, d3, WebLLM, Jev |
| **Minimum confidence** | The line under which an answer needs review (0.6 unless the schema says otherwise) |
| **Rules and model** | `final`: a rule at 0.85 or more decides alone. `off`: the model answers every kind |
| **Write properties to the model** | On by default. Off: results stay in the table |
| **Classify selection** / **Classify all** / **Stop** | Run on the selected elements or all. **Stop** ends after the requests in flight |

Before a run the tab estimates the work: elements, how many by rules, how many cached, how many signatures, and how many
requests. A repeated run costs zero requests, because the cache answers.

### Limits and gotchas

- Rules cover common IFC classes and names. A model with odd class use (everything as `IfcBuildingElementProxy`) sends most
  kinds to the model.
- A small in-browser model is a draft maker. On a test of 20 kinds it got the discipline right about 14 times, the
  sub-discipline 8 times and the division 5 times. The rules stay the first step for that reason.
- Software rendering without WebGPU makes the decision model slow: about 10 s per kind in one measurement.
- A process plant and a hospital use the same words differently. The rules decide "process context" for the whole model,
  conservatively, from line numbers, plant-only services and process equipment.
- The authors have not run the WebGPU path of the in-browser model (no GPU on their test machine). Treat its speed as untested.

## 18.2 Review: Accept, Change, Unsure

### The idea

A label you did not look at is a guess with a number on it. Review turns guesses into decisions that other people can trust.
Every answer you give is recorded as a **change** in a **review log**. The log is append-only: you can add a commit and revert
one, but you cannot rewrite history.

### Try it

1. On the **Process plant**, with results from 18.1, click one pump in the model.
2. At the top of the Classification tab, the card shows that element: class, name, the three labels with their confidences, the
   source, the rule's reason, and whether it needs review.
3. Click **Accept** if the labels are right. Click **Change...**, pick other values in the three lists and **Apply change** if
   not. Click **Unsure** if you can only guess.
4. A button **Commit N pending** appears. Click it. The first time, the viewer asks for your name or initials.
5. Press `Shift+R` to start the **Review walk**. The camera frames one kind of element at a time and ghosts the context.
   `Enter` or `Y` confirms. `2` takes the runner-up. `E` opens the correction form. `N` or the right arrow skips. The left arrow
   goes back. `?` flags the next answer as a guess. `A` switches between "all N of this kind" and "this element only". `Esc`
   ends the walk and puts back your camera and selection.

### How it works

A decision does not touch the results immediately. It goes into a **pending** set (tab **Pending**, with **Undo** on each row).
**Commit** writes the pending set as one commit: who, when, a note, and for each element the before and after.
**History** lists the commits, and **Revert** appends a new commit that puts the earlier state back. The old commit stays.

The newest committed change per element becomes its result: source *confirmed* or *corrected*, confidence 1, no review needed.
A re-run of the classifier never overwrites it. If a later run disagrees, the table marks it ("the model now disagrees")
and you decide again.

The order of the walk matters. **By type, then location** (default) shows one item per kind of element and confirms all N at once,
storey by storey. **Along systems** follows a pipe or duct run from one end. **By location** sweeps storey by storey.
**Needs review first** starts with the shakiest answers. Filters narrow it further: only needs review, only unconfirmed, only
unsure, only skipped, one discipline.

**Skip** leaves the element as it is. It writes nothing, so it never enters the log. The header counts what you skipped
this session. **Unsure** is different: it sets the codes but marks them as a guess. An unsure answer gets confidence 0.75, still
needs review, and is left out of **Calibrate on confirmed**.

Your reviewer name is kept in this browser and written in the review log and the exports you choose to make. It is personal
data. It is never in a share link, saved view, preset, parameters file, packed page or the element properties.

### Choices and settings

- **Review walk** order and filters, above.
- **Calibrate on confirmed**: refits the confidence on your committed answers. It needs at least 8 kinds and 4 answers per question.
- **Export review log** and **Import review log**: a file of commits (`xray-classification-review/1`). Importing the same file
  twice changes nothing, and a file for another model is refused with both fingerprints named.
- The pencil on a result row opens a manual override. It wins over rules, cache and model, and survives **Clear results**.

### Limits and gotchas

- The log is kept per model, in the browser's database (IndexedDB), with local storage as the fallback. If both fail the walk
  still works, and the History tab says "Not saved on this device". Export the log to keep it.
- The log belongs to one model and one schema. A different schema or a changed set of element ids gives a new fingerprint, and
  the old commits do not apply. For a new version of the same model, use the revision walk (chapter 20).
- Changing a code in the table does not edit the IFC file. To write results into a file, see 19.3.

## 18.3 Code lists: the default schema, your own, export

### The idea

The shipped schema is a stand-in. Your company has its own list of disciplines, and the labels are only useful downstream when
they use yours.

### Try it

1. In the Classification tab, open **Schema**.
2. To use a Throughline list, click **Import Throughline list** and pick the JSON file of the `Discipline` list. The tab names any
   entry it skips (another list, retired values) and warns when an entry has no description.
3. To use a schema file of your own, click **Load schema file**. Plain messages list every problem in it. **Use built-in schema** goes back.
4. Run **Classify all** again. A new schema has a new identity, so old cache entries and overrides are not mixed in.
5. Click **Export CSV**, **Export JSON** or **Export Throughline JSON** to save the results.

### How it works

A schema is a JSON file (`xray-classification-schema/1`). Each discipline has a code, a label, a short description and its
sub-disciplines. The description is what the decision model reads, so write it for a reader who must choose between options.
The MasterFormat list (2018 edition) is part of the schema too.

The built-in rules speak in the codes of the default schema. If your code for mechanical is `M`, give it a `rules_key` of
`MEC`, and the rules keep working for you. The Throughline importer reads that from the list's `rules_key`, its crosswalk, or
the code itself.

The results are written to the model as a property set, by default `XR_Classification`, with `Discipline`, `SubDiscipline`,
`MasterFormatDivision`, `MasterFormatTitle`, `Confidence`, `Source`, `Model` and `NeedsReview`. You can query them like any
property: `where XR_Classification.NeedsReview = TRUE`. **Save needs-review set** opens the set editor with that query, so the
list stays current (chapter 8).

The exports: **Export CSV** and **Export JSON** hold the GlobalId, the codes, the top two disciplines with probabilities, the
confidence, the source and, for committed answers, who confirmed it and when. **Export Throughline JSON** holds the code list
as rows plus each element's discipline. It can be imported again with the same importer.

### Choices and settings

- The default schema's disciplines include `PIP`, `MEC`, `ELE`, `INS`, `CIV`, `STR` (from the Throughline list) and `ARC`, `PLB`,
  `FPR`, `TEL`, `GEN` (added).
- `schemaUrl` in a parameters file loads a schema from an address. The settings for the classifier are in a `classify` section of
  the parameters; the API keys and the Hugging Face token are not.
- Appendix B lists every setting.

### Limits and gotchas

- The MasterFormat list is the shipped one. Throughline has none to import.
- A discipline added by the project, such as `ARC`, has no crosswalk to the company list. The Throughline export lists such
  codes under `needs_crosswalk`. A closed company list takes company codes only: load the real list before you load results
  elsewhere.
- Results held in the model are not saved with it. Export them, or write them into a copy of the IFC (19.3).

## 18.4 [D] Calibration and truth files

### The idea

If you change rules, schema or model, you need to know whether the labels got better. For that you need a file with the
right answer for every element: a **truth file**.

### Try it

From the `web` folder of the source:

```
npm run classify:truth -- --ifc <model.ifc> --truth <truth.json> --arms rules,majority
```

The command checks the truth file against the schema, converts the IFC, runs the classifier arms and prints tables
of accuracy per discipline, sub-discipline and division. Add `xsmall`, `base2`, `d3` or `hybrid-d3` to the arms to include the
models; those need their model files.

### How it works

The truth file is `xray-truth/1`: for each GlobalId a name, an IFC class, and the right discipline, sub-discipline and
division. A sub-discipline or division may list alternates that a lenient column accepts. Exit code 0 means done, 2 a bad truth
file or an element without a truth entry, 3 a failure of the converter or the bench, 64 bad usage, so the command can run in CI.
Results are cached per signature in the output folder, so a rerun costs nothing.

The repository ships a truth file for the Process plant (`models/Process-Plant.truth.json`) and an independent water works model
(`models/independent/Water-Works.ifc`) that the rules were not tuned on.

### Limits and gotchas

- The Process plant truth is one synthetic plant: 114 kinds, 1,294 elements. Numbers from it are measurements, not a general result.
- The rules were written while looking at that plant. The independent model exists to check that they are not memorising it.

### See also

Chapter 18A (facets, the By classification tree, colour by facet), chapter 18B (concrete), chapter 8 (queries over the classification properties), chapter 19 (writing results into the IFC), chapter 20 (carrying
decisions into a new model version).
