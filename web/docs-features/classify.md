# Classify: discipline, sub-discipline and MasterFormat division

The **Classify** tool of the action panel labels every element with a **discipline**, a **sub-discipline** and, for building
elements, a CSI **MasterFormat division** (2018 edition, 00 to 49). The labels come from a controlled, schema-defined code list,
so downstream processing can rely on them: a check, a quantity sum or a query never meets a free-text value.

The core is `src/classify/`: pure TypeScript with no DOM, so it runs in Node as well (`import { classifyInputs } from './classify'`).
The viewer adds the drawer, the settings section and `window.__xrayClassify` (`src/plugins/classify.ts`).

> **The shipped schema is a PLACEHOLDER.** The project's own target schema (the "Truxion specified schema") was not available.
> `public/classification/default-schema.json` is a draft written by the viewer authors. Swap in your own file, see
> [Your own schema](#your-own-schema). The drawer shows "PLACEHOLDER" while the draft is in use.

## The pipeline

Cheapest step first. An element leaves the pipeline at the first step that decides it.

1. **Manual** results (a person set the codes) win over everything and are kept per model.
2. **Deterministic rules** (`rules.ts`): an IFC class map with property, system-name and name hints. `IfcDuctSegment` is HVAC;
   `IfcBeam`, `IfcColumn` and `IfcFooting` are Structural; `IfcWall` is Architectural unless `LoadBearing = true`; `IfcPipeSegment`
   follows the system name (sprinkler, chilled water, domestic water, process, site drainage). A rule gives an answer and a
   confidence. A rule at or above **0.85** is final. A weaker rule is kept as a fallback only.
3. **Signature cache**: one decision per signature, which is the IFC class, the type name (or, with no type name, the name stem
   without digits), `PredefinedType`, `LoadBearing`, `IsExternal`, the systems, the material, the class of the first parent and
   whether the element is in a building. A model with 5,000 elements needs tens of requests, not thousands. The cache is kept
   per model in `localStorage`, keyed by **model name, schema hash and provider/model id**, so a decision of another schema or
   another model is never reused.
4. **The decision model**, for the rest, one signature at a time (the first element of the signature is the representative):
   - Request 1: `discipline` (a choice over the schema's disciplines), `building_element` (a yes/no statement that decides
     whether MasterFormat applies) and `masterformat` (a choice over the divisions).
   - Request 2: `sub_discipline`, a choice limited to the sub-codes of the chosen discipline. When the discipline confidence is
     below the minimum confidence, it is a choice over the sub-codes of the **top 2 disciplines combined** (options like
     `MEC/DUC`), and the answer breaks the tie: if it names a sub-code of the runner-up, that discipline is used. A discipline
     with a single sub-code needs no request. The strategy is pluggable (`subDiscipline` option: `'top'`, `'top2-when-unsure'` or
     your own function).
   - Every answer is validated against the schema: a choice outside the options, a probability outside 0 to 1, a missing
     answer or a code that is not in the schema fails the signature. The elements then fall back to a weak rule (flagged for
     review) or stay unclassified (`stats.failed`). The reason is in `stats.errors`.

### Why a decision model, not a language model

A decision model answers **typed questions with probabilities**: for a choice, the option and the probability of every option.
That gives a real confidence, a top-2 margin and an answer that cannot leave the code list. A generative model produces text
that has to be parsed and checked, and its "confidence" is whatever it writes. Here the code list is the answer space, and
`needsReview` is computed from numbers.

### needsReview

A result needs review when the discipline, the sub-discipline or the division has a confidence below the **minimum confidence**
(default 0.6, from the schema or the setting), when the probability margin between the top 2 options is below 0.15, or when
`building_element` is undecided (0.35 to 0.65). A weak rule used as a fallback is always flagged. Results keep their
probabilities, so the table shows the top 2 disciplines.

## What is sent to Jev

The viewer sends one `POST` per decision. This is the exact request for a pipe of `synth5k` (the lists in `criteria` are cut
after 3 options here; the viewer sends all 11 disciplines and all 35 divisions, in the full wording of the schema):

```json
{
  "model": "jev-1.13.0",
  "state": {
    "class": "IfcPipeSegment",
    "name": "Pipe riser L0 4,0",
    "type": { "class": "IfcPipeSegmentType", "name": "Pipe PVC 100" },
    "psets": {
      "Attr": { "ObjectType": "Pipe PVC 100", "PredefinedType": "RIGIDSEGMENT" },
      "Pset_PipeSegmentTypeCommon": { "Reference": "P-100", "IsExternal": false }
    },
    "quantities": { "Qto_PipeSegmentBaseQuantities": { "Length": 3.5 } },
    "material": "PVC",
    "systems": ["Domestic Water"],
    "hierarchy": ["IfcBuildingStorey: Level 0"],
    "parents": [
      { "class": "IfcSlab", "name": "Slab L0 4,0",
        "psets": { "Pset_SlabCommon": { "IsExternal": false, "LoadBearing": true, "FireRating": "REI90", "Reference": "S-250" } } }
    ],
    "building_context": true
  },
  "questions": {
    "discipline": {
      "type": "choice",
      "instructions": "Choose the engineering discipline that owns this BIM element. Decide from its IFC class, name, type, property sets, quantities, position in the building and its parents.",
      "criteria": {
        "ARC": "Architectural. Building envelope and interior fit-out that is not primarily structural: walls, partitions, doors, windows, finishes, roofs, stairs, furniture.",
        "STR": "Structural. Load-bearing frame and foundations: footings, piles, columns, beams, slabs, structural walls, bracing, reinforcement.",
        "MEC": "Mechanical and HVAC. Heating, ventilation and air conditioning: ducts, air terminals, fans, air handling, chillers, boilers, hydronic piping.",
        "...": "..."
      }
    },
    "building_element": {
      "type": "noul",
      "instructions": "This element is part of a building (not of a road, a bridge, a site utility or a process plant)."
    },
    "masterformat": {
      "type": "choice",
      "instructions": "Choose the CSI MasterFormat 2018 division that covers the work of this BIM element. Choose by the work that the element belongs to.",
      "criteria": {
        "00": "Procurement and Contracting Requirements. Bidding, contract forms and conditions. Not a physical element.",
        "...": "..."
      }
    }
  }
}
```

The `state` is a compact JSON of the element: class, name, type and property sets, quantities, the hierarchy path (the model
loaded in the viewer has storeys but no site or building objects, so the path holds the storey), the host elements as
parents, the systems and the material. Empty values and strings over 160 characters are dropped. The state is capped at
`maxStateBytes` (default 4000): detail is removed in steps (parent properties are cut to the key ones, then the quantities go, then the other
properties) until it fits; class and name always stay. `window.__xrayClassify.questions(id)` shows the exact request for any element, with the
state size in bytes and an example of the second request (`sub_discipline`).

The second request for the same element has the same `state` and one question:

```json
{ "sub_discipline": { "type": "choice", "instructions": "Choose the sub-discipline of this BIM element within Plumbing.",
    "criteria": { "SUP": "Domestic water supply. Cold and hot domestic water piping and fittings.", "DRN": "...", "FIX": "...", "EQP": "...", "STM": "..." } } }
```

A response, as the viewer reads it (`jevAdapter.parseResponse`):

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "discipline": { "type": "choice", "choice": "PLB", "confidence": 0.93, "probabilities": { "PLB": 0.93, "MEC": 0.04, "PIP": 0.02, "...": 0.01 } },
    "building_element": { "type": "noul", "noul": 0.97 },
    "masterformat": { "type": "choice", "choice": "22", "confidence": 0.88, "probabilities": { "22": 0.88, "23": 0.07, "...": 0.05 } }
  },
  "usage": { "input_tokens": 812, "output_tokens": 6 }
}
```

The `model` of every response is stored with the result (`result.model`, the `Model` property, the CSV column, and
`stats.models` with a count per id), so pinned versions can be audited. A result from the cache carries the id of the
model that made the cached decision.

## Settings

Params section `classify` (exported, imported and applied like the other sections; never part of saved views, presets or
packed pages unless you pass it to `--params`). It is a discriminated union on `provider`:

| Field | Applies to | Default | Meaning |
| --- | --- | --- | --- |
| `provider` | all | `off` | `off` (rules and cache only), `jev`, `webllm`, `mock` |
| `schemaUrl` | all | empty | URL of a schema file. Empty: the built-in placeholder (or the file you loaded in the drawer) |
| `minConfidence` | all | `null` | 0 to 1. `null`: the value of the schema |
| `writePset` | all | `true` | Write the results as properties of the elements |
| `endpoint` | `jev` | `https://api.typesafe.ai/v1/systemone` | An https URL, or a same-origin path such as `/api/jev` |
| `model` | `jev` | `jev-1.13.0` | The pinned model id. `jev-latest` is a moving alias and gives a warning. DigitalOcean inference uses `typesafe-jev-1.13.0` |
| `timeoutMs` | `jev` | 30000 | 1000 to 300000 |
| `concurrency` | `jev` | 4 | Requests in flight, 1 to 16 |
| `maxStateBytes` | `jev` | 4000 | Cap of the element state, 500 to 64000 |
| `webllmModel` | `webllm` | `Qwen2.5-0.5B-Instruct-q4f16_1-MLC` | One of the tested WebLLM model ids |

Settings are checked on load with plain messages (for example `concurrency must be a whole number from 1 to 16. Using 4.`); a bad
value keeps its default, and a field that looks like a secret (`apiKey`, `token`, ...) is refused. The drawer shows the
messages. `window.__xrayClassify.configure({ provider: 'jev', model: 'typesafe-jev-1.13.0' })` changes settings from a script.

## Setup: Jev

1. Choose **Jev (HTTP)** in the drawer. Keep the default endpoint and the pinned model id `jev-1.13.0`.
2. Paste your API key and click **Save key**. The box empties; the drawer shows only that a key is set.
3. Click **Test connection**. It sends one small yes/no question and shows the model id that answered.
4. Read the estimate (it lists elements, rules, cached, signatures and requests), then click **Classify selection** or
   **Classify all**. **Stop** ends the run after the requests in flight.

Retries: HTTP 429 and 5xx, and timeouts, are retried up to 4 times with the `Retry-After` header, else 0.5 s, 1 s, 2 s, 4 s.
HTTP 401 and 403 are not retried. A browser blocks a call to an endpoint that does not allow cross-origin requests (CORS); the
message says so. Then use a same-origin proxy.

### Proxy (recommended for shared deployments)

A proxy keeps the key on the server and gives the page a same-origin endpoint, so there is no CORS problem and no key in
the browser. Set the endpoint to `/api/jev` and leave the key box empty: with no key, no `Authorization` header is sent.
The proxy below serves the viewer and forwards `POST /api/jev` (17 lines, Node 18 or later; tested against a local stand-in
for the upstream):

```js
// node proxy.mjs ./dist-single   (Node 18+; set JEV_API_KEY). Serves the viewer and adds the key to POST /api/jev.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
const { JEV_API_KEY, PORT = 8787, JEV_URL = 'https://api.typesafe.ai/v1/systemone' } = process.env;
const root = process.argv[2] ?? '.', types = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.glb': 'model/gltf-binary' };
createServer(async (req, res) => {
  if (req.method === 'POST' && req.url === '/api/jev') {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const up = await fetch(JEV_URL, { method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${JEV_API_KEY}` }, body: Buffer.concat(chunks) });
    res.writeHead(up.status, { 'content-type': 'application/json', ...(up.headers.has('retry-after') && { 'retry-after': up.headers.get('retry-after') }) });
    return res.end(Buffer.from(await up.arrayBuffer()));
  }
  const path = normalize(req.url.split('?')[0]), file = join(root, path.endsWith('/') ? `${path}index.html` : path); // normalize drops any ../ above the root
  try { const data = await readFile(file); res.writeHead(200, { 'content-type': types[extname(file)] ?? 'application/octet-stream' }).end(data); } catch { res.writeHead(404).end(); }
}).listen(PORT, () => console.log(`http://127.0.0.1:${PORT}/`));
```

Run `JEV_API_KEY=... node proxy.mjs ./dist-single`, with the viewer page as `index.html` in that folder, and open
`http://127.0.0.1:8787/`. The proxy has no login: bind it to localhost, or put your own authentication in front of it.

## Setup: WebLLM (a tiny model in the browser)

Choose **Browser model (WebLLM)**. The viewer then loads `@mlc-ai/web-llm` **at run time from a CDN, from an exact pinned
version** (`https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.82/+esm`, constant `WEBLLM_VERSION`), never bundled, so the
single-file viewer does not grow, and nothing downloads until you start a run or click **Test connection**.

| Model id | Download (estimate) | GPU memory (`vram_required_MB` of WebLLM 0.2.82) |
| --- | --- | --- |
| `SmolLM2-360M-Instruct-q4f16_1-MLC` | about 210 MB | 376 MB |
| `Qwen2.5-0.5B-Instruct-q4f16_1-MLC` (default) | about 300 MB | 945 MB |
| `Qwen2.5-1.5B-Instruct-q4f16_1-MLC` | about 900 MB | 1630 MB |

WebLLM does not list the download size; the download figures are estimates for the 4-bit weights. The browser caches the model.

It follows the Jev semantics. Each option of a choice question gets a one-character label (A to Z, then a to z). The model
answers with one token and the **probabilities are the log probabilities of the label tokens at that position** (WebLLM
returns the top 5; an option outside the top 5 gets 0), renormalised over the labels. `confidence` is the top probability times
the probability mass that fell on labels. A yes/no question uses the tokens `Y` and `N`. The answer has the Jev shape, so the
pipeline does not know which provider it talks to. The returned `model` is `webllm:<model id>`.

A tiny model is much weaker than Jev. Treat its results as a draft: more elements will need review. It needs **WebGPU**
(Chrome or Edge on a computer with a GPU). Without it the drawer says so in plain words and **Test connection** returns the same
message; use Jev or the rules only. Requests run one at a time.

## Number of calls

Measured on the shipped models, with the mock provider (the numbers do not depend on the provider):

| Model | Elements | Rules (final) | Signatures to the model | Requests | Source counts |
| --- | --- | --- | --- | --- | --- |
| `synth5k`, default | 5000 | 5000 | 0 | **0** | rules 5000 |
| `synth5k`, rules off | 5000 | 0 | 9 | **18** | model 9, cache 4991 |
| `fzk-haus`, default | 82 | 40 | 1 (the 42 `IfcMember`) | **2** | rules 40, model 1, cache 41 |
| a repeat of any run | | | | **0** | cache |

Requests are at most 2 per signature (discipline, building and division, then sub-discipline). The drawer estimates them before
a run (`estimate(target)` in the API): "elements, by rules, cached, signatures, N to M requests". Retries after 429 and 5xx
are not counted in `stats.calls`.

## Schema

`xray-classification-schema/1`, a JSON file. The shipped draft is `public/classification/default-schema.json`.

```json
{
  "schema": "xray-classification-schema/1",
  "title": "My project schema",
  "version": "1.0.0",
  "psetName": "XR_Classification",
  "minConfidence": 0.6,
  "properties": { "discipline": "Discipline", "subDiscipline": "SubDiscipline", "masterformatDivision": "MasterFormatDivision",
                  "masterformatTitle": "MasterFormatTitle", "confidence": "Confidence", "source": "Source", "model": "Model",
                  "needsReview": "NeedsReview" },
  "fallbackDiscipline": "GEN",
  "disciplines": [
    { "code": "MEC", "label": "Mechanical and HVAC", "description": "Heating, ventilation and air conditioning: ducts, fans, ...",
      "rulesKey": "MEC",
      "subDisciplines": [ { "code": "DUC", "label": "Ductwork", "description": "Duct segments and duct fittings." } ] }
  ],
  "masterformat": { "edition": "MasterFormat 2018", "appliesTo": "building",
                    "divisions": [ { "division": "23", "title": "Heating, Ventilating, and Air Conditioning (HVAC)", "description": "Ducts, air handling, ..." } ] }
}
```

- **disciplines**: a code, a label and a short `description` for each; the description becomes the Jev `criteria` text, so
  write it for a reader that has to choose between the options. **subDisciplines** are listed per discipline, with the same
  three fields.
- **masterformat.divisions**: a two-digit division (00 to 49), a title and a description. The shipped list has the 35
  divisions of the 2018 edition that exist (00 to 14, 21 to 23, 25 to 28, 31 to 35, 40 to 46, 48; the others are reserved).
  `appliesTo: "building"` (default) leaves the division empty for elements that the model judges not to be part of a building.
- **psetName** and **properties**: the property set and property names that the results are written under (default
  `XR_Classification` with `Discipline`, `SubDiscipline`, `MasterFormatDivision`, `MasterFormatTitle`, `Confidence`, `Source`,
  `Model`, `NeedsReview`, and `MasterFormatSection` when a rule knows one).
- **minConfidence**: the review limit (the `minConfidence` setting overrides it).
- **rulesKey**: the built-in rules speak in the codes of the default schema. A discipline or sub-discipline of your schema that
  has another code sets `rulesKey` to the default code it replaces (`"code": "M", "rulesKey": "MEC"`). A rule whose discipline
  your schema does not have gives no rule; the element goes on to the cache and the model.

The default codes follow the Throughline `Discipline` list where it has an entry (`PIP`, `MEC`, `ELE`, `INS`, `CIV`, `STR`; `origin:
"throughline"`); `ARC`, `PLB`, `FPR`, `TEL` and the fallback `GEN` are added. Throughline's `PRO` (process) is merged into `PIP`
here, because the specification asked for "Piping/Process" as one discipline.

### Your own schema

- In the drawer: **Load schema file**. The file is checked (plain messages for each problem) and kept in `localStorage`
  (`xray.classify.schema.v1`); **Use built-in schema** goes back.
- By URL: the `schemaUrl` setting (also in a params document or `xray-pack --params`).
- From a script: `window.__xrayClassify.setSchema(jsonObjectOrText)` returns the list of problems (empty: accepted).
- In Node: `parseSchema(json)` and pass `schema` to `classifyInputs`.

A new schema has a new hash, so caches and manual overrides of the old one are not mixed in.

## Output

With `writePset` (default on) every result is written to the element properties as `<psetName>.<Property>`, so the viewer sees them
like any other property: the hover card, the search bar and the query engine. A bare property name works in a query when only one
property set has it:

```
count where discipline = 'MEC'
sum length by discipline
where XR_Classification.NeedsReview = TRUE
where MasterFormatDivision = '23' and class = 'IfcDuctSegment'
```

The properties live in the loaded model only: export CSV or JSON to keep them. **Colour by discipline** tints the elements
(the legend lists the codes). **Select needs review** selects the elements that need review; **Save needs-review set** opens the
criteria-set editor with the query `"XR_Classification.NeedsReview" = TRUE`. **Export CSV** and **Export JSON** save the
results (`GlobalId`, discipline and its top 2 probabilities, sub-discipline, division, confidence, source, model id,
`NeedsReview`, rationale for rules).

### Manual overrides

The pencil on a row opens a form: discipline, sub-discipline and division (lists from the schema). **Apply override** gives the
element a result with source `manual` and confidence 1. A manual result wins over rules, cache and model, survives
**Clear results** and new runs, and is kept per model and schema hash in `localStorage`. **Remove override** deletes it.

## API: `window.__xrayClassify`

| Method | Meaning |
| --- | --- |
| `classify(ids \| 'selection' \| 'all', opts?)` | Classify elements (GlobalIds or element indexes). `opts.rules: false` skips the rules. Returns the `ClassifyResult[]` |
| `classifyInputs(inputs)` | Classify prepared `ClassifyInput` objects |
| `buildInput(id)` | The `ClassifyInput` of an element |
| `questions(input \| id, discipline?)` | The exact Jev request (`main`) and an example of the second (`sub`) |
| `schema()`, `setSchema(json)` | Read, replace the schema |
| `results()`, `stats()` | The results; counts by source, `calls`, `signatures`, `needsReview`, `failed`, `errors`, `models`, `usage` |
| `override(id, { discipline?, subDiscipline?, masterformat? })` | A manual result |
| `clear()`, `abort()` | Remove results and written properties (manual results stay); stop a run |
| `export('json' \| 'csv')` | The export text |
| extras | `estimate`, `configure`, `settings`, `setKey`, `keyState`, `testConnection`, `selectNeedsReview`, `colourByDiscipline`, `state` |

Types (`src/classify/types.ts`): `ClassifyInput { id, ifcClass, name, psets, quantities?, type?, hierarchy?: { path, parents? },
systems?, material? }` and `ClassifyResult { id, discipline: { code, label, confidence, probabilities }, subDiscipline | null,
masterformat: { division, title, confidence, probabilities } | null, buildingElement, source: 'rules' | 'cache' | 'model' |
'manual', model?, needsReview, rationale? }`. Providers implement `DecisionModel { decide(state, questions, signal) }` and return
the Jev response shape.

In Node:

```ts
import { classifyInputs, defaultSchema, createJevProvider } from './src/classify';
const provider = createJevProvider({ endpoint: '/api/jev', model: 'jev-1.13.0', apiKey: () => null, timeoutMs: 30000 });
const { results, stats } = await classifyInputs(inputs, { schema: defaultSchema(), provider });
```

Commands (palette): `classify.selection`, `classify.all`, `classify.review`, `classify.stop`, `classify.colour`.

## Key security

- The API key is **never** in the params document, the share link (`#p=`), the exported params JSON, saved views, presets or packed
  pages. It is not a setting: a params document that contains a key field is refused with a message. A unit test checks
  `collectParams`, the share URL, saved views and the packed output.
- It is kept in `sessionStorage` (gone when the tab closes). The **Remember on this device** switch, off by default, keeps it
  in `localStorage` instead.
- The box is a password field and empties after saving; the drawer shows only that a key is set and its length. The viewer never
  logs it, and it is removed from error messages.
- It is sent in the `Authorization` header to the configured endpoint only, and not at all when the endpoint has no key
  (a proxy). The requests use `credentials: 'omit'`.
- **A key held in a page can be read by anyone who uses that browser profile**, by any script on the page, and by a browser
  extension. For a shared deployment use the proxy above and leave the key box empty.
- The element data goes to the endpoint too. Check that your organisation allows it before you classify a real project with a
  hosted model, or choose the browser model or the rules only.

## Unverified details of Jev

These come from public secondary sources. `docs.typesafe.ai` was not reachable when this was written. **Check them against
the vendor documentation.** Every field name is in one file, `src/classify/jevAdapter.ts`, so a correction is one edit.

- Endpoint `POST https://api.typesafe.ai/v1/systemone`, headers `Authorization: Bearer <key>` and `Content-Type: application/json`.
- Model ids `jev-1.13.0` (pinned) and `jev-latest` (alias); `typesafe-jev-1.13.0` on DigitalOcean inference.
- The request fields `model`, `state` and `questions` (types `choice`, `score`, `noul`; `instructions`; `criteria`) and the
  response fields (`model`, `answers`, `choice`, `confidence`, `probabilities`, `score`, `legend`, `noul`, `usage`).
  The viewer assumes `noul` is the probability that the statement is true.
- **Not documented, assumed:** batching (not used: one request per decision), rate limits (429 is retried with backoff), the
  error format (the status code and the first 200 characters of the body are shown, with the key removed), CORS for browsers
  (assumed not to be allowed: use a proxy), the largest `state` and the number of `criteria` that a question may have
  (35 divisions are sent; the state is capped at 4000 bytes by default).
- Whether `probabilities` always lists every option (the viewer accepts a subset) and whether an option key may be a
  bare number such as `"23"` (the division codes are sent as keys).

The WebLLM model sizes and the library version were read from the `@mlc-ai/web-llm@0.2.82` package; the load from the CDN was not
run in this environment (no WebGPU, no model download), only a fake engine in the tests.
