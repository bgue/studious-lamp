# Classify: discipline, sub-discipline and MasterFormat division

The **Classify** tool of the action panel labels every element with a **discipline**, a **sub-discipline** and, for building
elements, a CSI **MasterFormat division** (2018 edition, 00 to 49). The labels come from a controlled, schema-defined code list,
so downstream processing can rely on them: a check, a quantity sum or a query never meets a free-text value.

The core is `src/classify/`: pure TypeScript with no DOM, so it runs in Node as well (`import { classifyInputs } from './classify'`).
The viewer adds the drawer, the settings section and `window.__xrayClassify` (`src/plugins/classify.ts`).

> **The shipped schema is the "Throughline-aligned default".** Its discipline codes follow the Throughline `Discipline` code list where
> it has an entry (`PIP`, `MEC`, `ELE`, `INS`, `CIV`, `STR`); `ARC`, `PLB`, `FPR`, `TEL` and `GEN` are added. It is a stand-in:
> **load the project's actual `Discipline` code list (the company standards edition) to replace it**, see
> [Throughline alignment](#throughline-alignment). `public/classification/default-schema.json` is the file.

## The pipeline

Cheapest step first. An element leaves the pipeline at the first step that decides it.

1. **Manual** results (a person set the codes) win over everything and are kept per model.
2. **Deterministic rules** (`rules.ts`): an IFC class map with property, system-name and name hints. `IfcDuctSegment` is HVAC;
   `IfcBeam`, `IfcColumn` and `IfcFooting` are Structural; `IfcWall` is Architectural unless `LoadBearing = true`; `IfcPipeSegment`
   follows the system name (sprinkler, chilled water, domestic water, process, site drainage). A rule gives an answer and a
   confidence. A rule at or above **0.85** (`RULE_FINAL`) is **final**: the element is decided there, for the discipline, the
   sub-discipline and the division together, with the rule's confidence, and no request goes out for it. A weaker rule is kept as a
   fallback only (used, and flagged for review, when the model fails). The setting **`rulesMode`** chooses (drawer: *Rules and model*):
   `final` (default, "rules where certain, else the model": the behaviour above) or `off` (the rules are not run, the model answers
   every element; the *Calibrate on rules* run always uses this, as its labels must not be the model's own answers). There is no
   per-question mix: a final rule that names the discipline keeps its own sub-discipline and division, so the three answers of
   one element never come from two sources.
3. **Signature cache**: one decision per signature, which is the IFC class, the type name (or, with no type name, the name stem
   without digits), `PredefinedType`, `LoadBearing`, `IsExternal`, the systems, the material, the class of the first parent and
   whether the element is in a building. A model with 5,000 elements needs tens of requests, not thousands. The cache is kept
   per model in `localStorage`, keyed by **model name, schema hash and provider/model id**, so a decision of another schema or
   another model is never reused.
4. **The decision model** (the in-browser `decision` provider, Decision 3.0 d3-edge, WebLLM, Jev or the mock), for the rest, one signature at a time (the first element of the signature is the representative):
   - Request 1: `discipline` (a choice over the schema's disciplines), `building_element` (a yes/no statement that decides
     whether MasterFormat applies) and `masterformat` (a choice over the divisions).
   - Request 2: `sub_discipline`, a choice limited to the sub-codes of the chosen discipline. When the discipline confidence is
     below the minimum confidence, it is a choice over the sub-codes of the **top 2 disciplines combined** (options like
     `MEC/DUC`), and the answer breaks the tie: if it names a sub-code of the runner-up, that discipline is used. A discipline
     with a single sub-code needs no request. The strategy is pluggable (`subDiscipline` option: `'top'`, `'top2-when-unsure'` or
     your own function).
   - **Calibration** (logit scaling, see [Logit scaling](#logit-scaling-calibration)) is applied when a decision is read from the cache, so the
     confidence is meaningful. The sub-discipline step sees the scaled discipline confidence.
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

### Rules: civil and site works

The deterministic rules place site works (CIV) before the structural and plumbing rules that would otherwise take them. Most
site items have no IFC class of their own (paving is an `IfcSlab`, a kerb or a fence post an `IfcBuildingElementProxy`), so the
rule reads the names: the name, the type name, `ObjectType`, `Description`, `Tag` and `PredefinedType`. Pset names and system
names are not read for this. The name rules apply only to the classes that can carry a site item (proxies, slabs, walls,
railings, plates, members, element assemblies and civil or geographic elements). A pipe, valve, duct or cable never takes a
civil name.

| Item | Rule | Discipline / sub-discipline | MasterFormat |
| --- | --- | --- | --- |
| Paving, pavement, hardstanding, apron, road, highway, car park | name; `IfcSlab` with `PredefinedType = BASESLAB` | CIV / PAV | 32 13 00 |
| Base slab outside a building | `IfcSlab`, `BASESLAB`, not in a building | CIV / PAV | 32 13 00 |
| Kerb, curb | name; `IfcKerb` | CIV / PAV | 32 16 13 |
| Fence, site or vehicle gate | name | CIV / LND | 32 31 00 |
| Drain trench, drain channel, gully, catch basin | name | CIV / DRN | 33 44 00 |
| Culvert | name | CIV / DRN | 33 41 00 |
| Manhole, inspection chamber | name | CIV / DRN | 33 39 00 |
| Earthwork, excavation, grading, bund | name; `IfcEarthworks*` | CIV / ERT | 31 23 00 |
| Retaining wall | name (any wall class) | CIV / ERT | 32 32 00 |
| Equipment foundation, plinth, pump or skid base | name or `ObjectType` of an `IfcFooting` | CIV / FND | 03 30 00 |
| Footing in the site, not in a storey | `IfcFooting` in an `IfcSite` with no storey | CIV / FND | 03 30 00 |

- A **building footing** stays STR / FND, and a **building ground slab** (`BASESLAB` in a building, not named as paving) stays
  STR / SLB.
- The MasterFormat divisions of the schema apply to building elements. Outside a building the division is empty, as for every
  other discipline, so a site item gets its division only when it is in a building storey.
- The sub-discipline `FND` under CIV (equipment foundations and plinths) is in the default schema. The other CIV
  sub-disciplines are `ERT`, `PAV`, `DRN`, `UTL` and `LND`.
- Confidence: a name rule is 0.88, which is final. An equipment foundation is 0.9.
- Process-plant sample (`models/Process-Plant.ifc`), rules only, before and after: STR 404 to 274, CIV 0 to 214, PLB 81 to 71,
  unresolved 74 to 0. MEC 428, PIP 429, ELE 56, INS 19 and ARC 23 do not change. The 120 paving slabs, 2 roads, 48 kerbs,
  26 fence posts, 10 drain trenches and 8 equipment foundations (under the pumps, exchangers and vessels) are now CIV. The
  28 footings under the rack and platform columns stay STR.

### Rules: process facilities, supports and equipment parts

The same words mean different things in a process facility and in a building, and the schema decides (`default-schema.json`): `PIP/UTL` is "utility piping such as air, steam, water and nitrogen", `PIP/PMP` is
"process pumps and compressors", `PIP/VES` and `PIP/HTX` are vessels and heat exchangers, `PIP/SUP` is "pipe supports, hangers and guides", `MEC/HYD` is "heating and cooling water piping" and `PLB` is "building plumbing",
and MasterFormat division 40 is "process piping, valves, instrumentation and control of process systems". So the rules need to know which of the two they are in.

- **Process context** (`isProcessModel`, `processEvidenceOf` in `rules.ts`; `buildInput` sets `ClassifyInput.processContext` for the whole model). It is decided for the model, conservatively: it needs **two different kinds of evidence on at least
  three elements**. The kinds are a line number (a `LineNumber` property, or an ISA-style number such as `150-CW-1203-A1A` in the tag), a service that only a plant has (a system name or `Service` property with process, flare, crude,
  hydrocarbon, slurry, solvent, chemical, blowdown, nitrogen, instrument air, plant air or fuel gas), and process equipment (an `IfcTank` `VESSEL` or `PRESSUREVESSEL`, an `IfcHeatExchanger` `SHELLANDTUBE`). Steam, condensate and cooling
  water are **not** evidence: a hospital has them too. An element built without the model flag (a unit test, an API call) is in a process context only when it carries a line number **and** a process or utility service. None of the other
  bundled models (building, fzk-haus, plumbing, synth5k, debris-demo) has a process context; a unit test checks it.
- **In a process context:** steam, condensate, cooling water, boiler feed water, utility air or water and service water piping is `PIP/UTL` (division 40), process and flare services are `PIP/PRC`; a pipe with a line number and no service name is `PIP/PRC`;
  a valve in such a line is `PIP/VLV`, a `REGULATING` valve is `INS/CTL` (the schema lists control valves there); an `IfcPump` or `IfcCompressor` is `PIP/PMP` (43), an `IfcTank` is `PIP/VES` (43) and an `IfcHeatExchanger` is `PIP/HTX` (42), unless a fire
  or plumbing name says otherwise (a fire pump stays `FPR`); an `IfcElectricMotor` that names the machine it drives (`Driver`) is `PIP/PMP`; a sensor or flow meter is `INS/SNS` with division 40 (25 in a building); baseplates, skirts, saddles and channels of
  pumps, vessels and exchangers follow their equipment. **In a building** the same names stay `MEC/HYD` (cooling, chilled, heating, steam), `PLB` (domestic water) and `MEC/EQP` or `PLB/EQP` (pumps, tanks, exchangers).
- **Supports** (any context): a member, plate, proxy or accessory whose name, type, `ObjectType` or `PredefinedType` says pipe support, sleeper, hanger, shoe, guide or riser guide is `PIP/SUP` (division 40 in a process context, 22 or 23 by system name, else 05);
  one that says it supports a cable tray (tray support, hanger, bracket, stanchion, riser) goes with the tray, `ELE/CND` (26). A member named bracing, strut or gusset and a plate named base plate, gusset or splice plate are `STR/BRC` at 0.9 (final); an unnamed member stays 0.8
  and goes to the model.
- **Other:** a load-bearing masonry wall is `STR/WLS` with division 04 (masonry), not 03; a grating or checker plate floor panel is a metal deck, division 05.
- **Not read:** the generator's tags, the truth file, or any exact string of the process plant sample. The vocabulary is the one in the schema descriptions and common to real models, but it was written while looking at this plant: see
  [the truth bench](#truth-bench-the-process-plant) for what that means for the numbers.
- A unit test (`tests/classify-rules-regression.test.ts`) snapshots the rules' output for every other bundled model (`tests/fixtures/rules-snapshot.json`: discipline, sub-discipline, division and the final flag of 5,534 elements) and fails on any difference.

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
| `provider` | all | `off` | `off` (rules and cache only), `decision` (a small NLI model in the browser, recommended), `d3` (Decision 3.0 d3-edge), `webllm`, `jev`, `mock` |
| `schemaUrl` | all | empty | URL of a schema file. Empty: the built-in placeholder (or the file you loaded in the drawer) |
| `minConfidence` | all | `null` | 0 to 1. `null`: the value of the schema |
| `writePset` | all | `true` | Write the results as properties of the elements |
| `rulesMode` | all | `final` | `final`: a rule at or above 0.85 decides the element completely (discipline, sub-discipline, division), the model answers the rest. `off`: the model answers every element, the rules are not run. See [The pipeline](#the-pipeline) |
| `calibration` | all | `auto` | Logit scaling of the confidence: `auto` (the numbers shipped for the model), `fitted` (fitted on this model by **Calibrate on rules**), `manual` (`temperatures`), `off` (the model as it comes) |
| `temperatures` | all | `{}` | The `manual` mode: a number from 0.05 to 50 per question (`discipline`, `sub_discipline`, `masterformat`, `building_element`). A question that is missing is not scaled |
| `images` | `d3` (endpoint, and the browser with a vision export), `jev` | `off` | Pictures of the element: `off`, `isolated` (the element alone), `context` (the element in its bounding box with the elements around it), `both` (isolated first, then context). The old values `element` and `element+neighbours` are read as `isolated` and `context`, with a warning. See [Pictures](#pictures-for-a-model-that-reads-images) |
| `imageStyle` | same | `render` | `render` (shaded) or `vector` (a simplified line drawing: silhouette and feature edges, black on white) |
| `imagePlan` | same | `false` | Add a plan view of the element alone to the isolated picture |
| `imageSize` | same | 384 | Pixels, 256 to 512, a multiple of 32 (another value is moved to the nearest multiple, with a warning: the vision model reads blocks of 32 pixels and a picture of that size needs no resize) |
| `imageMargin` | same | 25 | Margin of the context box, 0 to 200 percent of the largest side of the element, never under 0.5 m |
| `geometryText` | `jev`, `d3` (both backends) | `off` | `off` or `svg`: put the shape of the element into the request state as compact SVG text. Independent of `images`. Not used by `decision` and `webllm` (their premise is short; a warning says so). See [Geometry as SVG text](#geometry-as-svg-text) |
| `geometryContext` | same | `true` | With `svg`: also the element in its bounding box with the elements around it (the margin is `imageMargin`) |
| `imageViews` | none | | Removed. An old value is ignored, with a warning |
| `endpoint` | `jev` | `https://api.typesafe.ai/v1/systemone` | An https URL, or a same-origin path such as `/api/jev` |
| `model` | `jev` | `jev-1.13.0` | The pinned model id. `jev-latest` is a moving alias and gives a warning. DigitalOcean inference uses `typesafe-jev-1.13.0` |
| `timeoutMs` | `jev` | 30000 | 1000 to 300000 |
| `concurrency` | `jev` | 4 | Requests in flight, 1 to 16 |
| `maxStateBytes` | `jev` | 4000 | Cap of the element state, 500 to 64000 |
| `jevImages` | `jev` | `false` | Send the pictures (`images`) to the endpoint. **Untested**: Jev is not known to read images |
| `d3Backend` | `d3` | `browser` | `browser` (onnxruntime-web with WebGPU) or `endpoint` (a System One server) |
| `d3Repo`, `d3Revision` | `d3` | `warsang/d3-edge-web`, the pinned commit | The Hugging Face repository of the ONNX export and its commit (40 characters; a branch gives a warning), **or the web address of a folder** that serves the export (for example `http://localhost:8123/d3-mm`; see [Your own export, with pictures](#your-own-export-with-pictures-in-the-browser)). For a folder address the revision is only a label: it goes into the cache identity and into the address of every file (`?v=<label>`), so change it when you export again to the same folder. A Hugging Face token is never sent to a folder address |
| `d3HfEndpoint` | `d3` | `https://huggingface.co` | Where the files come from (a mirror or your own proxy) |
| `d3Device` | `d3` | `auto` | `auto` (WebGPU with `shader-f16`, else a plain refusal), `webgpu`, `wasm` (very slow, about 5 GB of memory) |
| `d3Endpoint`, `d3Model` | `d3` | `http://localhost:8899/v1/systemone`, `vllm-sr/d3-edge` | The System One URL and model id of the endpoint backend (what `vllm-sr serve -e vllm-sr/d3-edge` exposes) |
| `d3MaxStateBytes` | `d3` | 2000 | Cap of the element state in the prompt, 500 to 64000. Each token costs time on a small device |
| `timeoutMs`, `concurrency` | `jev`, `d3` (endpoint) | 30000, 4 | As for Jev |
| `hfModel` | `decision` | `MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33` | A Hugging Face repository id, `owner/name`, of a zero-shot or NLI model with ONNX weights |
| `device` | `decision` | `auto` | `auto` (WebGPU when the browser has it, else WASM), `webgpu`, `wasm` |
| `dtype` | `decision` | `auto` | `auto` (q8 on WASM, fp16 on WebGPU when the adapter has `shader-f16` and the model has fp16 weights, else fp32), `fp32`, `fp16`, `q8`, `q4` |
| `hfEndpoint` | `decision` | `https://huggingface.co` | Where the weights come from (a mirror or your own proxy; `env.remoteHost` of transformers.js). An https URL or a same-origin path |
| `hypothesis` | `decision` | the 4 default sentences | Advanced. One hypothesis sentence per question (`discipline`, `sub_discipline`, `masterformat`, `building_element`); `{}` marks the option |
| `webllmModel` | `webllm` | `Qwen3-0.6B-q4f16_1-MLC` | One of the tested WebLLM model ids |
| `webllmMode` | `webllm` | `chat` | `chat`, `embed` or `hybrid` |
| `webllmEmbedModel` | `webllm` | `snowflake-arctic-embed-s-q0f32-MLC-b4` | Embedding model for `embed` and `hybrid` (`-m-` is the larger one) |
| `embedTemperature` | `webllm` | 0.05 | 0.005 to 1. Softmax temperature over the cosine similarities |
| `hybridMargin` | `webllm` | 0.15 | 0 to 1. Hybrid: below this top-2 margin the chat model decides |
| `webllmCustomModel`, `webllmCustomLib` | `webllm` | empty | Advanced. A custom MLC model: the Hugging Face repository URL and the compiled `.wasm` library URL. Both or neither |

Settings are checked on load with plain messages (for example `concurrency must be a whole number from 1 to 16. Using 4.`); a bad
value keeps its default, and a field that looks like a secret (`apiKey`, `hfToken`, `token`, ...) is refused. Neither the Jev key nor the
Hugging Face token nor the d3 key is a setting. Fitted temperatures are not settings either (they are kept per model in `localStorage`). The drawer shows the
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

## Setup: the decision model in the browser (recommended local option)

Choose **Decision model (in browser, WebGPU)**. It is a small **zero-shot NLI classifier** (DeBERTa-v3 family) that runs in the page
with [transformers.js](https://github.com/huggingface/transformers.js). It decides, it does not generate: a choice answer has a probability
for **every** option (not the top 5 of a chat model), a yes/no answer has p(yes), and nothing leaves the browser except the download of the
weights. The provider is `src/classify/providers/decision.ts`.

**Loading.** `@huggingface/transformers` is **not bundled**. It is loaded at run time, only when the provider is used, from an exact
pinned version (`https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.2/dist/transformers.min.js`, constant `TRANSFORMERS_VERSION`; this
file contains onnxruntime-web, so no other import is needed). The single-file viewer does not grow. The weights come from huggingface.co (or
`hfEndpoint`) on first use, and **the browser keeps them in the Cache API** (`transformers-cache`). The drawer shows the cache size and has
**Clear model cache**.

**Models** (ids and sizes checked against the Hugging Face model API; sizes are the ONNX files):

| Model id | Sizes | Note |
| --- | --- | --- |
| `MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33` (default) | q8 87 MB, fp32 284 MB | Trained for zero-shot on 33 datasets. Labels `entailment` / `not_entailment` |
| `MoritzLaurer/xtremedistil-l6-h256-zeroshot-v1.1-all-33` | q8 13 MB, fp32 51 MB | Tiniest and fastest, less exact |
| `Xenova/nli-deberta-v3-xsmall` | q8 87 MB, fp16 143 MB, fp32 284 MB | Plain NLI (SNLI, MNLI), labels `contradiction` / `entailment` / `neutral`. Has fp16 for WebGPU |
| `MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33` (better) | q8 244 MB, fp32 739 MB | About 3 times slower than xsmall |
| `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` | fp32 739 MB only | The repository has no quantized file: a large download |

The dropdown shows these with their sizes, and the **Hugging Face model id** box takes any other repository id (`owner/name`,
checked for its format). **Device** is `auto` (WebGPU when `navigator.gpu` gives an adapter, else WASM), `webgpu` or `wasm`; a forced
WebGPU that is not there is an error, never a silent switch. **Data type** is `auto` (q8 on WASM, fp16 on WebGPU when the adapter has
`shader-f16` and the model has fp16 weights, else fp32), `fp32`, `fp16`, `q8` or `q4`. Without WebGPU the drawer says in plain words:
"Slower: this browser has no WebGPU, so the model runs on the CPU with WebAssembly." The WebGPU path was **not run** here (no GPU in the sandbox).

**How a question becomes NLI.** The *premise* is a compact text of the element, the *hypothesis* is one sentence per option:

- **Premise** (`buildPremise`): built from the state, most informative first, and cut to 160 tokens (about 3 characters each) at a field
  boundary: `Element class IfcPipeSegment (pipe segment). Type Pipe PVC 100 (pipe segment type). Name Pipe riser L0. Properties:
  PredefinedType RIGIDSEGMENT, ObjectType Pipe PVC 100. System Domestic Water. Material PVC. Storey Level 0. Hosted in slab Slab L0. It is
  inside a building.` Class, type and name come first, then key properties, system, material, storey, parent and the building flag. The
  tokenizer truncates as a backstop (the model limit is 512).
- **Choice** (`discipline`, `sub_discipline`, `masterformat`): one pair per option. The hypothesis is the template of the question with the
  label and a short description of the option from the schema: `This building element belongs to the Mechanical and HVAC (heating,
  ventilation and air conditioning: ducts, fans) discipline.` The entailment logits of all options go through **one softmax** (the
  `multi_label: false` rule of the pipeline), so the probabilities sum to 1 over all options. `choice` is the largest, `confidence` is its
  probability, and the answer maps back to the option codes.
- **Noul** (`building_element`): one pair, the statement as the hypothesis. p(yes) = `softmax([contradiction, entailment])[1]` of that pair. A binary
  zero-shot model has no `contradiction` label: its `not_entailment` label is used as the "against" score.
- The hypothesis sentences are the **advanced** `hypothesis` setting, one per question; `{}` marks the option and must appear exactly once.
  Other sentences give other decisions, so a non-default set is part of the cache identity (`decision:<model>@h<hash>`).

**Passes.** A cross-encoder reads premise and hypothesis together, so an option cannot be encoded once and reused; what is cached and batched:

- All pairs of one request share the premise and run **in batches** (8 pairs per forward pass on WASM, 16 on WebGPU), across the questions of
  the request: the 47 pairs of the first request (11 disciplines, 1 statement, 35 divisions) take 6 passes, not 9. The provider calls the
  tokenizer and the model of the pipeline directly for this (the public pipeline call runs one pair per pass), and falls back to the public
  call when a pipeline does not expose them.
- A **pair cache** (4000 pairs) answers a repeated (premise, hypothesis); the option sentences are built once per request.
- It runs **per signature only**, never per element (the pipeline caches the decision per signature). Measured with the fake model on `synth5k`
  with the rules off (the pairs and passes depend on the schema and the batch size, not on the model; `bench/smoke-classify-local.mjs`):

| Element type (first element of its class) | Requests | Text pairs | Forward passes (batch 8) |
| --- | --- | --- | --- |
| `IfcSlab`, `IfcBeam`, `IfcColumn`, `IfcWall` | 2 | 61 | 8 |
| `IfcDuctSegment` | 2 | 59 | 8 |
| `IfcPipeSegment` | 2 | 52 | 7 |
| **9 signatures of `synth5k`** | 18 | 525 (58.3 per signature) | 70 (7.8 per signature) |

  A request 1 is 47 pairs and 6 passes. The sub-discipline request (request 2) adds 5 to 14 pairs and 1 to 2 passes: 14 when the
  discipline confidence is under the minimum and the question covers the sub-codes of the top 2 disciplines together. A second run costs 0
  passes (signature cache).

**Test model.** The button loads the model, runs one tiny choice (a duct against two disciplines) and reports the load time, the device,
the data type and the size: `Ready: <id> on wasm (q8) in 1.7 s, 87 MB of files. Test question: chose MEC (0.86) in 2 ms.` The drawer shows the
download progress (all files added together) while it loads. For a model that is not in the list it first reads `config.json` and the
file sizes from the Hub API.

**Custom Hugging Face models** ("pull from HF"): type any `owner/name`. Before any weights are downloaded the viewer reads its
`config.json` and refuses what cannot decide, in plain words:

- a language model: `"org/chat" is not a classifier (its architecture is Qwen2ForCausalLM), so it cannot decide among options. It needs a sequence-classification (NLI) model with an "entailment" label and a "contradiction" or "not_entailment" label, such as a DeBERTa zero-shot model.`
- a sentiment or other classifier: `... is not a zero-shot or NLI model: its labels are negative, positive, and none is "entailment".`
- not found (`HTTP 404`), private or gated (`HTTP 401/403`: save a token), host not reachable (check the network and the endpoint). The labels of
  the loaded model are checked once more after the load. A repository without the chosen data type's file gives `... has no q4 weights ...
  Choose another data type`; with `auto` the provider retries fp32 itself.

A failed load is not repeated for every signature of a run (30 seconds), so a run over 40 signatures does not try 40 downloads.

**Hugging Face token** (private or gated models): handled exactly like the Jev key (`keyStore.ts`, a second entry `xray.classify.hfToken`).
It is not a setting and never in the params document, the share link, saved views, presets or packed pages. It is kept in
`sessionStorage` (the tab), or in `localStorage` with **Remember token on this device**; the box is a password field that empties; the drawer
shows only that a token is set and its length. It is sent **only to the Hugging Face endpoint** (the origin of `hfEndpoint`), through the
`env.fetch` of transformers.js for the weights and in the header of the `config.json` check; not to the CDN, not to any other host, and
the wrapper is removed after the load. The leak test covers it together with the Jev key.

**Privacy.** The element data stays in the page: only the model files are downloaded. A model from a mirror is a download from that mirror.

**Checked against the real models** (`bench/real-classify-decision.mjs`; the real transformers.js 4.3.2, real weights from huggingface.co). 20 elements with
distinct signatures from `fzk-haus` (10) and `synth5k` (10) with a final rule, the rules' answers as the truth, the rules off for the model. This is a
small sample and the rules are only a proxy for the truth: read it as an order of magnitude.

| Model (q8, Node CPU) | Discipline | Sub-discipline | Division | Time per element |
| --- | --- | --- | --- | --- |
| `MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33` (default) | 14 of 20 | 8 of 20 | 5 of 20 | 845 ms |
| `Xenova/nli-deberta-v3-xsmall` | 13 of 20 | 7 of 20 | 2 of 20 | 818 ms |
| `MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33` | 12 of 20 | 4 of 20 | 6 of 20 | 1596 ms |
| `MoritzLaurer/xtremedistil-l6-h256-zeroshot-v1.1-all-33` | 11 of 20 | 8 of 20 | 6 of 20 | 132 ms |

In Chromium, on the WASM path with the real CDN module and the real download (`device wasm`, `q8`, no WebGPU in the sandbox): load 10.1 s for 95.9 MB of files
(the model, its tokenizer and config), the test question in 341 ms, and `synth5k` with the rules off (9 signatures, 544 pairs, 73 passes) in **86 s**, about 9.6 s per signature.

Read these results as follows:

- The **probabilities are flat**: with 11 disciplines the top probability is 0.1 to 0.5 (35 divisions: lower), so with the default minimum confidence 0.6 **every** decision of
  this provider needs review. The ranking carries the information, the confidence barely does. Lower **Minimum confidence** (0.15 to 0.25 is a start) and use the top-2
  margin and a person's review for what matters. A model of this size is a draft maker, as WebLLM is; use Jev when the labels must stand.
- The discipline is right in about 7 of 10 (this sample), the sub-discipline and the division much less often: they depend on the discipline, and the NLI model reads class
  names ("IfcMember") worse than words. The rules stay the first step for a reason.
- Option sentences with a short description beat the bare label (14 of 20 against 11 of 20 in the same run); three other templates for the discipline sentence gave 9 to 14 of 20.
  The `hypothesis` setting is there for a project that wants to tune them.

## Setup: WebLLM (a chat or embedding model in the browser)

Choose **Browser chat model (WebLLM)**. The viewer loads `@mlc-ai/web-llm` **at run time from a CDN, from an exact pinned
version** (`https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.87/+esm`, constant `WEBLLM_VERSION`), never bundled, so the
single-file viewer does not grow, and nothing downloads until you start a run or click **Test connection**. It needs **WebGPU**.

| Model id | Download | GPU memory (`vram_required_MB` of WebLLM 0.2.87) |
| --- | --- | --- |
| `SmolLM2-360M-Instruct-q4f16_1-MLC` | 206 MB | 376 MB |
| `gemma3-1b-it-q4f16_1-MLC` | 602 MB | 711 MB |
| `Qwen2.5-0.5B-Instruct-q4f16_1-MLC` | 285 MB | 945 MB |
| `Qwen3-0.6B-q4f16_1-MLC` (default) | 347 MB | 1403 MB |
| `Qwen3.5-0.8B-q4f16_1-MLC` | 437 MB | 1629 MB |
| `Qwen2.5-1.5B-Instruct-q4f16_1-MLC` | 876 MB | 1630 MB |
| `Qwen3-1.7B-q4f16_1-MLC` | 979 MB | 2037 MB |
| `snowflake-arctic-embed-s-q0f32-MLC-b4` (embedding, default) | 67 MB | 239 MB |
| `snowflake-arctic-embed-m-q0f32-MLC-b4` (embedding) | 218 MB | 540 MB |

The GPU memory figures are read from the `0.2.87` package. The download figures are the sizes of the weight shards and the tokenizer in the
model repositories on huggingface.co (the package does not list them). The browser caches the models. Qwen3 and Qwen3.5 think before they
answer unless told not to: the provider sends `extra_body: { enable_thinking: false }` for them, so the first token is an answer.

**Modes** (`webllmMode`):

- `chat` (default, as before). Each option of a choice question gets a one-character label (A to Z, then a to z). The model answers with one
  token and the **probabilities are the log probabilities of the label tokens at that position** (WebLLM returns the top 5; an option outside
  the top 5 gets 0), renormalised over the labels. `confidence` is the top probability times the probability mass that fell on labels. A
  yes/no question uses the tokens `Y` and `N`. The returned `model` is `webllm:<model id>`.
- `embed`. An embedding model (Snowflake Arctic Embed) turns the element text (the same premise as the decision model, with the retrieval
  prefix `Represent this sentence for searching relevant passages: `) and every option text into vectors. The **cosine similarity** of the
  element against each option goes through a **softmax with a temperature** (`embedTemperature`, default 0.05; cosines of related texts differ
  by 0.05 to 0.2), which gives a probability for **every** option, with no top-5 limit. The option vectors are computed once and kept, so a
  new element costs one embedding. A yes/no question is answered weakly (the statement against its negation): use `hybrid` or the decision
  provider when `building_element` matters. The returned `model` is `webllm:embed:<embed model>@T<temperature>`.
- `hybrid`. Embed first. When the **top-2 probability margin is below `hybridMargin`** (default 0.15), the chat model chooses **among the top 5
  options only** (the top-k order breaks ties by option order), where its top-5 log probabilities are complete. The top options share the
  probability mass that the embedding gave them, and the chat model splits it (the other options keep their embedding probability), so the
  probabilities still sum to 1. If the chat model names no letter, the embedding answer stays. A yes/no question always goes to the chat
  model. Both models load in one engine. The returned `model` is `webllm:hybrid:<embed model>+<chat model>@T..,m..`.

The mode and its knobs are part of the cache identity, so a decision of another mode is never reused. Requests run one at a time.

**A custom model from Hugging Face** (advanced): the **Custom model URL** (a repository such as `https://huggingface.co/mlc-ai/Qwen3-0.6B-q4f16_1-MLC`)
and the **Custom library URL** (the compiled `.wasm`, https). Both or neither. They are added to the engine as an `appConfig` model entry
(`model`, `model_id` `custom-<repository name>`, `model_lib`). A model library runs as code in the page: the drawer warns, and warns more for a
host other than huggingface.co, raw.githubusercontent.com and github.com. Settings with half a custom model, a non-https URL or a library that is not `.wasm`
are refused with a plain message.

Without WebGPU the drawer says so in plain words and **Test connection** returns the same message. A tiny model is weaker than Jev: treat
its results as a draft and expect more elements to need review.

## Logit scaling (calibration)

A decision model gives a score (a logit) per option. The probability is `exp(score / T)` normalised over the options; `T = 1` is the model as it comes.
The zero-shot NLI models are not confident on this task, so most answers sat under the minimum confidence (0.6) and went to review. **Logit scaling** fits one
temperature `T` per question (`discipline`, `sub_discipline`, `masterformat`, `building_element`) by minimising the negative log-likelihood on labelled answers.
`T` is positive, so **the chosen option never changes**; only the confidence does. A provider that returns probabilities (Jev, d3 on the endpoint, WebLLM) is scaled in the
log domain, `p_i ∝ exp(log p_i / T)`. The WebLLM embed mode gives the logits `cosine / embedTemperature`, so `embedTemperature` and the calibration temperature multiply.

- **Raw scores are cached.** The signature cache keeps the logits (or log-probabilities) next to every model decision (`raw` in `CachedDecision`). The calibration is applied when a
  decision is **read**, so a change of mode or temperature re-scores the results (and the stored results of the drawer) without running the model, and the calibration is **not**
  part of the cache identity. The sub-discipline step uses the scaled discipline confidence to decide how many disciplines to put in the second request.
  A cache entry from before this feature has no raw scores and is shown as it is.
- **Modes** (`calibration`): `auto` uses the numbers shipped for the model (`calibrationDefaults.ts`; none for a model that is not listed: no scaling and a hint);
  `fitted` uses the numbers fitted on this model by **Calibrate on rules** (kept per model id in `localStorage`, not secret, not in the settings); `manual` uses `temperatures`;
  `off` is the model as it comes.
- **Calibrate on rules.** The elements that a *final* rule labels in the loaded model (one per signature, at most 120) are the proxy labels. The model runs for the ones that are not in the
  cache, a fixed 30 % of the signatures (by hash) is held out, `T` is fitted on the rest, and the drawer shows before and after on the held-out part: accuracy, mean confidence,
  expected calibration error (ECE, 10 bins), the share of answers that clear the minimum confidence and their accuracy. The stored `T` is refitted on all signatures. **The rules are not the truth**: a rule can be wrong, and
  a model that agrees with a wrong rule looks worse than it is. The mode is set to `fitted`. API: `window.__xrayClassify.calibrate()`.

### Shipped numbers and what they show

`node bench/real-classify-decision.mjs` (needs the network and a Node install of transformers.js outside the project; see the file header). It takes every distinct signature that a final rule labels
in the bundled models: the five sidecars of `public/models` and the six IFC files of `models/` read with web-ifc, a model that is both counted once: **51 signatures** (fzk-haus 16, synth5k 9,
building 10, plumbing 2, debris-demo 13, Infra-Electrical 1). That is every one there is: 60 or more distinct signatures do not exist in the bundled models. With so few, one 70/30 split is noisy, so the bench
uses **5-fold cross-validation**: every number below is scored with a temperature fitted without that signature. Minimum confidence 0.6. Models run on CPU (onnxruntime-node, q8; v2.0 fp32), d3 with the fp16 torso.
Times were measured while another job kept the machine at a load of 8 to 12 on 4 cores, so read them as upper bounds.

Final labels (what the pipeline decides, including the sub-discipline tie-break), and the time per element (one element is 2 requests):

| Model | Discipline | Sub-discipline | Division | ms per element |
| --- | --- | --- | --- | --- |
| xsmall zero-shot v1.1 (default) | 39/51 | 15/51 | 18/49 | 4,590 |
| xtremedistil L6 | 26/51 | 18/51 | 10/49 | 684 |
| nli-deberta-v3-xsmall | 27/51 | 11/51 | 4/49 | 4,306 |
| base zero-shot v1.1 | 18/51 | 6/51 | 11/49 | 9,819 |
| **base zero-shot v2.0 (fp32, 739 MB)** | **43/51** | **28/51** | **29/49** | 19,684 |
| d3-edge (fp16 torso, CPU) | 24/51 | 24/51 | 23/49 | 44,769 |

Per question, before and after scaling, out of fold (accuracy is of the first-stage answer; "clear" is the share with confidence at or above 0.6 and the accuracy of those):

| Model, question | n | Right | T | Mean conf. | ECE | Clear 0.6 | Right of clear |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2.0 discipline | 51 | 69% | 0.53 | 0.55 to 0.77 | 0.20 to 0.10 | 53% to 65% | 96% to 94% |
| v2.0 sub-discipline | 48 | 56% | 0.58 | 0.39 to 0.54 | 0.20 to 0.16 | 17% to 35% | 88% to 82% |
| v2.0 division | 49 | 59% | 0.76 | 0.40 to 0.55 | 0.28 to 0.25 | 14% to 41% | 57% to 60% |
| default xsmall discipline | 51 | 35% | not shipped | 0.34 | 0.12 (0.24 scaled) | 0% (39% scaled) | 55% scaled |
| default xsmall sub-discipline | 47 | 30% | 0.43 | 0.16 to 0.33 | 0.14 to 0.11 | 0% to 6% | 100% (3 answers) |
| default xsmall division | 49 | 39% | 0.26 | 0.08 to 0.35 | 0.31 to 0.13 | 0% to 6% | 67% (3 answers) |
| d3-edge discipline | 51 | 45% | 1.53 | 0.65 to 0.48 | 0.30 to 0.18 | 63% to 18% | 50% to 89% |
| d3-edge sub-discipline | 29 | 83% | 1.36 | 0.91 to 0.84 | 0.13 to 0.10 | 93% to 83% | 85% to 88% |
| d3-edge division | 49 | 51% | not shipped | 0.44 | 0.30 | 39% | 63% |

What this says, honestly:

- **Scaling makes the confidence track accuracy; it does not make the model right.** The default model is right on 35% of the discipline questions before the tie-break; its raw discipline
  confidence (0.34) was already close to that, so scaling the discipline question only trades a little more NLL for a worse ECE and **no temperature is shipped for it**. Its sub-discipline and
  division answers were far under-confident (0.16 and 0.08 against 30% and 39% right), and scaling lifts them to about their accuracy, but almost nothing then clears 0.6,
  because it is too often wrong. "All answers clear review" is not a result that any scaling can give a model that is mostly wrong; the divisions stay low because the model is wrong on them.
- Of all the zero-shot models, **base zero-shot v2.0** is the one that works: 43/51 disciplines, 28/51 sub-disciplines, 29/49 divisions. After scaling, 65% of its discipline answers clear 0.6 and 94% of
  those are right; 41% of its division answers clear and 60% are right, which is what a 0.6 confidence should mean. It is a 739 MB fp32 download (no quantized file) and about 20 s per element on this CPU.
  It is **not** the default (size); it is the one to choose when quality matters. The 51 signatures are a small sample and the rules are proxy labels.
- d3-edge is over-confident on the discipline question (63% clear at 50% right) and scaling (T = 1.53) corrects that to 18% clear at 89% right. It chooses `GEN` (the General fallback) for walls, stairs, beams and braces of
  three of the models, which the rules call ARC and STR: its option reading of this schema is the weak point, not its confidence. Its sub-discipline answers are the best of all models (83%).
- **The minimum confidence stays 0.6.** After scaling, the answers that clear 0.6 are right about as often as 0.6 promises or more (v2.0: 94%, 82%, 60%), so there is no held-out reason to lower it per provider.
- A shipped temperature is kept for a question only when, out of fold, it lowered the NLL and did not raise the ECE. The numbers are in `src/classify/calibrationDefaults.ts`.

### Refit against the truth (process plant)

The numbers above were fitted on rule labels. The process plant has a design-intent truth (`models/Process-Plant.truth.json`), so the temperatures of the three models of the truth bench were re-checked on it with
`node bench/fit-truth-temperatures.mjs --bench <truth-bench.json> --truth ../models/Process-Plant.truth.json` (raw scores from `bench/real-classify-truth.mjs`). **One synthetic plant: 114 signatures, 1,294 elements, one generated unit.**
These are measurements on it, not a general result, and the other models (xtremedistil, nli-deberta, base v1.1) were not re-checked.

- One sample per element (the raw scores of its signature's representative, the truth as label), so the fit is weighted by element count; a second pass with one sample per signature must not contradict it.
- **5-fold cross-validation by signature** (a seeded shuffle of the signatures, seed 20240611, fold = position mod 5): the elements of one signature never sit on both sides, and every sample is scored with a temperature fitted on the other folds.
  The sub-discipline question is scored under the true discipline; the building question has no truth label and was left as it was.
- A number ships only where, out of fold, it lowers the NLL and does not raise the ECE, against both T = 1 and the value that shipped before. Where the new fit does not beat the old value but the old value itself beats T = 1 on the truth, the old
  value is kept; where nothing beats T = 1, the question has no shipped number. Each decision and its figures are written next to the number in `calibrationDefaults.ts` (`detail`).

Cover and precision at 0.6 per element, before (the values shipped until now) and after (out of fold for a new fit):

| Model | Question | Shipped before | Ships now | Cover before | Precision before | Cover after | Precision after | ECE before to after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| xsmall | discipline | none | 1.49 | 0% | - | 0% | - | 0.32 to 0.22 |
| xsmall | sub-discipline | 0.43 | none | 38% | 34% | 4% | 100% | 0.35 to 0.15 |
| xsmall | division | 0.26 | none | 8% | 21% | 0% | - | 0.22 to 0.12 |
| base v2.0 | discipline | 0.53 | 0.53 (kept) | 71% | 88% | 71% | 88% | 0.23 |
| base v2.0 | sub-discipline | 0.58 | 0.58 (kept) | 20% | 96% | 20% | 96% | 0.15 |
| base v2.0 | division | 0.76 | none | 14% | 20% | 11% | 7% | 0.29 to 0.27 |
| d3 | discipline | 1.53 | none | 25% | 100% | 54% | 83% | 0.25 to 0.11 |
| d3 | sub-discipline | 1.36 | 1.99 | 90% | 78% | 84% | 77% | 0.20 to 0.15 |
| d3 | division | none | none | 19% | 85% | 19% | 85% | 0.17 |

The d3 discipline question was under-confident against the truth (25% of the elements cleared 0.6 at 100% right with T = 1.53; raw, 54% clear at 83% right, and the raw numbers have the lower NLL and ECE). The default model's discipline question is
right at the top option for 2% of the elements, so no temperature makes its answers clear 0.6: the 1.49 that ships only makes its confidence honest (ECE 0.32 to 0.22).

## Setup: Decision 3.0 d3-edge

Choose **Decision 3.0 d3-edge**. d3-edge ([vllm-sr/d3-edge](https://huggingface.co/vllm-sr/d3-edge), Apache-2.0, revision `bee5e872f75b9c5d1405767bf244a6948b95c0af`) is a
0.6B Qwen3.5 fine-tune (0.10B of it the vision encoder) that answers typed questions with a probability for every option and generates no
text. Its API, "System One", is the request and answer shape of Jev, so the pipeline sees no difference (`src/classify/providers/d3.ts`,
`d3Format.ts`; the endpoint backend is the Jev HTTP provider with another id). It has two backends.

**Endpoint** (`d3Backend: 'endpoint'`). `vllm-sr serve -e vllm-sr/d3-edge` exposes `http://localhost:8899/v1/systemone` with the model
`vllm-sr/d3-edge` (the defaults). The official PyTorch model runs there, on a GPU or a CPU. The key box is optional and is **its own entry**
(a Jev key is never sent to a d3 server). This backend always sends [pictures](#pictures-for-a-model-that-reads-images) when `images` is on; the browser backend does so only with an export that has a vision graph.

**In the browser** (`d3Backend: 'browser'`, the default). onnxruntime-web with the WebGPU backend runs the **third-party** export
[warsang/d3-edge-web](https://huggingface.co/warsang/d3-edge-web) at the pinned revision `117fb255e630667ae1736666497e8a1c69c7a066` (it is not
from the d3-edge authors: no README, 29 downloads when it was pinned, scope "text-only v1"). Files: `onnx/torso_fp16.onnx` (1,043,107,948 bytes, the
Qwen3.5 stack with full attention, last-position hidden state), `onnx/readout.onnx` (fp32, 255 x 1024), `tokenizer.json`; 1.04 GB in all.

- **Libraries are not bundled.** onnxruntime-web `1.30.0` (`ort.webgpu.min.mjs`) and transformers.js `4.3.2` (the Qwen tokenizer) load from
  jsDelivr at exact versions, only when the provider is used.
- **A confirmed download.** The drawer reads `MANIFEST.json` and `decision_config.json` first (a few KB) and shows the size. **Test model** asks
  "download 1.04 GB from huggingface.co?" and downloads only after **Download model**. The files stream into the Cache API (`xray-d3-cache`); the next load
  reads them from there. **Clear model cache** deletes them and the confirmation.
- **Integrity.** Every file is checked against the size in the manifest, and the files up to 64 MB (readout, tokenizer) against its sha256. The torso is checked by
  size only (hashing 1 GB in the page is not practical); its sha256 `f8f7dd3a...c557766` was checked once outside the page and matches the manifest.
  A custom repository id is checked by its manifest and its `decision_config.json` (format `d3-code-readout-v1` and the same 255 codes) before any weights come.
  A manifest with a vision graph (and its file in the list) is loaded: the viewer then reads pictures (see [Your own export, with pictures](#your-own-export-with-pictures-in-the-browser)). The vision graph is checked by size, as the torso.
- **Device.** The torso is fp16, so WebGPU needs `shader-f16`. Without it, or without WebGPU, `auto` **refuses with a plain message** before any download
  ("needs WebGPU with 16-bit float support ... use the endpoint backend or the Decision model"). `wasm` can be chosen by name; see "What was run" below.
- **Prompt and readout.** `d3Format.ts` ports `d3_format.py` exactly: the Qwen3.5 chat template (system and user, thinking off), `State:` with the Python
  `json.dumps` text of the state, `Question:`, one `<code>: <key>: <description>` line per option, codes `A, B, ... AA, ...` from `decision_config.json`
  (255, not plain A..ZZ), then a 255-way readout at the last position and a softmax over the options. One torso pass per question; the largest question of the
  viewer has 35 options. The state cap defaults to 2000 bytes (each token costs time).
- The torso reads the whole prompt at once (full attention), so questions that share a state cannot share work: a signature costs 3 passes plus 1 for the sub-discipline.

### What was run (d3)

- **Prompt parity, byte for byte.** `tests/fixtures/d3-golden-prompts.json` holds 13 prompts that the official `d3_format.py` and the chat template of vllm-sr/d3-edge produced (`bench/d3/golden_prompts.py`);
  `tests/classify-d3-format.test.ts` requires the TypeScript prompt to be identical (text and JSON states, unicode, small floats, 60 options, options with no description, score levels). Python writes a float such as 1e-7 as `1e-07`; the port does the same.
- **Model parity.** `bench/real-d3-parity.mjs` runs the model card examples (support ticket: route, receipt, urgency; payment; a code request) and one BIM state through **our** TypeScript prompt builder, the Qwen tokenizer of transformers.js,
  the real torso and readout in onnxruntime-node (CPU), and `bench/d3/reference.py` runs the official `vllm-sr/d3-edge` with `transformers==5.17.0` and `trust_remote_code` (CPU, bf16) on the same requests: **the 9 prompts are identical and the
  largest probability difference is 0.0071** (the export's own manifest claims 0.0118 worst case); every argmax agrees. Examples: ticket route `returns` 0.9926 against 0.9927, receipt yes 0.9995 in both, the BIM pipe `PLB` 0.9606.
  The manifest's own parity requests are not given, so those numbers could not be reproduced one to one. The sha256 of every file of the export matches its manifest.
- **WASM.** The fp16 torso loads and runs on the onnxruntime-web WASM backend (run in Node, one thread): 18 s to load, about 25 tokens per second, 4.8 GB of memory. A browser limits a WebAssembly heap to 4 GB, so it will probably refuse;
  that was **not run in a browser**. It is offered only when chosen by name, with that warning.
- **Not run:** WebGPU (no GPU here; the browser path ran against a fake onnxruntime-web and a fake export in the unit tests and the smoke), the endpoint with real pictures against a real server, and `vllm-sr serve`.

### Your own export, with pictures (in the browser)

The only browser export on Hugging Face, warsang/d3-edge-web, reads text only. `tools/export_d3_web.py` makes **our own** export from the official checkpoint
([vllm-sr/d3-edge](https://huggingface.co/vllm-sr/d3-edge), Apache-2.0) with a vision graph. The output **stays local**: it is not uploaded anywhere by this repository. Run it in a throw-away
virtual environment (it runs the repository's own modelling code; about 8 GB of memory; the torso takes 1 to 2 minutes with `--no-optimize`, 20 minutes or more without):

```
python -m venv /tmp/d3env && . /tmp/d3env/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install "transformers==5.17.0" safetensors pillow numpy onnx onnxscript onnxruntime huggingface_hub
python tools/export_d3_web.py --checkpoint vllm-sr/d3-edge --out /tmp/d3-mm --no-optimize   # all graphs, the self-check, MANIFEST.json
```

The folder holds `MANIFEST.json`, `decision_config.json`, `tokenizer.json`, `tokenizer_config.json`, `config.json` and `onnx/vision_encoder.onnx`, `onnx/torso_mm.onnx`, `onnx/readout.onnx`.
Then **serve the folder over http with CORS** and point the viewer at it. For example, with Node:

```
node -e "require('http').createServer((q,r)=>{const f=require('path').join('/tmp/d3-mm',decodeURIComponent(new URL(q.url,'http://x').pathname));require('fs').stat(f,(e,s)=>{if(e||!s.isFile()){r.writeHead(404,{'access-control-allow-origin':'*'});return r.end()}r.writeHead(200,{'access-control-allow-origin':'*','content-length':s.size});require('fs').createReadStream(f).pipe(r)})}).listen(8123)"
```

In the Classify drawer choose Decision 3.0 d3-edge, backend In the browser, **Model repository** `http://localhost:8123` (any folder address works; a path such as `https://example.org/models/d3-mm` too),
and any text as **Revision** (a label: it goes into the cache identity and the file addresses, so change it when you export again to the same folder). Then set Images. Or upload the folder to a Hugging Face
repository of your own and use its id and commit. The drawer reads the manifest first (a few KB) and shows the size; **Test model** asks before it downloads, as for the default export. A token is never sent to a
folder address.

What the export is (all numbers from this repository's run, see below):

- `onnx/torso_mm.onnx`: input_ids `[1, L]`, image_embeds `[M, 1024]` (float32), position_ids `[3, 1, L]` (the T, H, W rows of the multimodal rotary positions) -> the last-position hidden state `[1, 1024]`.
  The embedding is in the graph, the rows of the `<|image_pad|>` tokens are replaced by the picture embeddings in order (masked scatter), 12 layers as in the official runtime (the Gated DeltaNet layers keep their causal
  scan, written as a `while_loop` over chunks of 64 tokens so that the length is dynamic; the 6 full-attention layers read the whole prompt, no causal mask), the final norm of the last position only. fp16 weights.
  It also answers **text-only** requests (no picture token: a dummy embedding row and the text positions 0..L-1 on the three rows), so one torso serves both.
- `onnx/vision_encoder.onnx`: pixel patches `[N, 768]` of **one** picture (merge-block order; the two equal frames of a still picture are folded into the patch matrix), the patch rows and columns, the 4 bilinear taps and weights into the
  learned 48 x 48 position table -> embeddings `[N / 4, 1024]`. Axial 2-D rotary and 12 blocks of full attention inside the picture, then the 2 x 2 merger. fp16 weights, dynamic N (4 to 4096 patches).
- `onnx/readout.onnx`: the official `readout.safetensors` (255 x 1024, fp32) as a matrix product, the codes beyond the option count masked to -inf. Its outputs equal those of the readout of warsang's export.
- The picture preprocessing and the positions are done in the page, in `src/classify/providers/d3Vision.ts` (checked against the official processor and backbone, see `tests/classify-d3-vision.test.ts` and its golden file
  `tests/fixtures/d3-vision-golden.json` from `bench/d3/vision_golden.py`): `smart_resize` (factor 32), the patch order, the position taps, the expansion of the placeholder to 1 token per 2 x 2 patches
  (144 tokens for a 384 px picture), and `get_rope_index`. A picture whose size is not a multiple of 32 is resized with a separable bicubic (a = -0.5) with a widened kernel, which is not bit-identical with torchvision's
  (the viewer's own pictures are multiples of 32 and are never resized). Several pictures run through the vision graph one by one, once per request (the main and the sub-discipline request share them).
- A manifest declares it with `"graphs": {"torso": "onnx/torso_mm.onnx (...)", "vision": "onnx/vision_encoder.onnx (...)", "readout": "..."}`, `"scope": "text and images"`, an `"mm"` block (image token id, patch 16, merge 2, position grid 48,
  pixel limits), the size and sha256 of every file, and a `"parity"` section. The viewer needs the vision file to be listed (a declared graph with no file is refused). The torso is checked by size (it is 1 GB), the vision graph too, the small files by sha256.
- **Cast, not CastLike.** The exporter writes ONNX `CastLike` nodes; onnxruntime 1.30 on the CPU provider refuses the graph with "does not match expected type (tensor(float16))". The tool replaces every `CastLike` by a `Cast` to the type
  that shape inference gives (86 nodes in the torso). The result loads in onnxruntime-node 1.30.0 (the version this viewer pins for the browser) and in Python onnxruntime 1.31.

### What was run (pictures)

All of it on this machine: 4 CPU cores, no GPU, onnxruntime-node 1.30.0 (the version the browser path pins), Python transformers 5.17.0 and torch 2.15 CPU for the official model.

- **Export size.** `onnx/torso_mm.onnx` 1,045,719,940 bytes, `onnx/vision_encoder.onnx` 200,593,328, `onnx/readout.onnx` 1,051,146, `tokenizer.json` 12,807,982 and three small files:
  **1,260,197,181 bytes (1.26 GB)** in all, 0.2 GB more than the text-only export (1.06 GB). Nothing of it is bundled into the viewer.
- **Parity with the official model** (`bench/d3/mm_reference.py` runs `AutoModel(...).system_one(..., images=[...])` on CPU in bf16; `bench/d3/mm_parity.mjs` runs the same requests through
  `createD3BrowserProvider` of the viewer with our export, the picture preprocessing and the positions in TypeScript):
  - **with pictures**, 10 requests and 24 questions (the model card's receipt example; a pipe spool and a pump of process-plant with the pictures of the viewer, render and line drawing; main and sub-discipline requests):
    the largest probability difference is **0.0348** (the pipe, "building" question: 0.4496 against 0.4844), every argmax agrees (24 of 24), and **the number of prompt tokens is identical to the official one in every request**.
    The receipt (900 x 1000, so it goes through our own bicubic resize, not torchvision's) differs by at most 0.0253 (route `technical` 0.6466 against 0.6715; "does the receipt list the blender" 0.9421 against 0.9430).
  - **text only**, the 4 requests of the earlier parity run (9 questions): largest difference **0.0074**, every argmax agrees (9 of 9).
  - The text-only path with warsang's export is **unchanged**: the prompts are identical and the answers are bit-identical to the run before this change (difference 0).
  - On the hidden state (the export's own self-check against the stock transformers code in fp32, with the official `PromptEncoder`): the vision graph has cosine 0.9999929 (largest difference 0.0146 on values up to 3.6),
    the torso with a picture 0.9999998 (0.0032 on values up to 12.3) and the torso with text only 0.9999996 (0.0061 on 11.9). The references are fp32 or bf16 and ours is fp16, so these are the rounding of the weights.
- **Time per element** (the main request with 3 questions and the sub-discipline request: 4 torso passes; Node, onnxruntime CPU, fp16 weights, 384 px pictures, mean of 3 runs after a warm-up, the vision graph runs once per request set):

  | | text only | 1 picture (isolated) | 2 pictures (isolated, context) |
  | --- | --- | --- | --- |
  | pipe spool (tokens in the 4 passes) | 8.4 s (2,890) | 11.3 s (3,646), of which vision 0.54 s | 12.9 s (4,230), of which vision 0.80 s |
  | pump | 7.5 s (2,622) | 10.4 s (3,378), of which vision 0.58 s | 13.2 s (3,962), of which vision 0.96 s |

  A 384 px picture is 576 patches and **144 prompt tokens** per pass, plus about 45 tokens of note in the state. A picture roughly adds 25 to 40 % to the time of an element on this CPU.
  The `bench/d3/mm_timing.mjs` script measures it. These are CPU numbers: WebGPU was not run.
- **Not run:** WebGPU (no GPU here: the browser path ran against a fake onnxruntime-web in the unit tests and in the smoke, and against the real graphs in Node), the endpoint with pictures against a real `vllm-sr serve`
  (the request body is checked against a fake server in the smoke), and the Loop operator of the torso on the WebGPU provider (the graph has one `Loop` per Gated DeltaNet layer, as the text-only export has).

## Pictures for a model that reads images

d3-edge reads images. Set `images` and every request carries up to three of them, as base64 data URLs (WebP for a render, PNG for a line drawing),
placed before the text of the request (that is where the System One prompt puts them). They are drawn off screen with three.js from the loaded model
(`src/classify/thumbs.ts`) on a canvas of their own, 256 to 512 pixels square (default 384, a multiple of 32 so that the vision model needs no resize).

| `images` | The model gets |
| --- | --- |
| `off` (default) | text only |
| `isolated` | **Picture 1**: the element alone, fitted, axonometric (from the corner x+, y+, z+, y up), neutral background, with a scale bar. With `imagePlan` a second picture of the element alone seen from above |
| `context` | **Picture 1**: the element highlighted inside its own **bounding box**, grown by `imageMargin` (25 % of the largest side, at least 0.5 m) on every side. Every other element whose bounds touch that box (at most the 120 nearest) is drawn ghosted and grey and **clipped to the box** (clipping planes of the off-screen render), and the outline of the box is drawn in blue. The picture shows exactly the surroundings of the element within its box, and nothing beyond it |
| `both` | the isolated picture first, then (the plan) and the context picture last |

Two styles (`imageStyle`). **`render`** is shaded (the element orange with its edges, the ghosts grey and transparent). **`vector`** is a simplified line drawing, black on
white: the crease edges of the mesh (30 degrees, the same machinery as the viewer's edges) plus the **silhouette edges** seen along the view (a pipe has no crease along its
sides, so the silhouette is what draws it), hidden lines removed by a white fill, the ghosts in thin grey lines. The line drawing is a PNG (crisp lines), a lot smaller,
and has no shading for the 0.6B model to misread. Which style reads better for the model was **not** measured on a large set (see the bench below).

**The note.** The prompt has no place for a caption, so the viewer adds a `pictures` entry first in the state (it is not counted in `d3MaxStateBytes`), for example:
`Picture 1: the element alone, a render, axonometric, with a scale bar. Picture 2: the element (orange) in its bounding box with nearby elements in grey.`
The sentences name the pictures in the order that they are sent.

Example pictures (a pipe spool, a pump, a beam and a wall of process-plant; top row render, bottom row line drawing with the plan): `bench/classify-pictures-pipe.png`,
`classify-pictures-pump.png`, `classify-pictures-beam.png`, `classify-pictures-wall.png`. The drawer with the preview of a column: `bench/classify-pictures-drawer.png`. `bench/smoke-thumbs.mjs` draws them and checks the sizes, the order, the note, that the
line drawing is black on white and that no ghost line lies outside the box.

The drawer shows the **same data URLs** that the request carries, for the selected element, with the note (a preview, "what the model sees"). They are drawn once per element and settings
and kept in memory only. **A picture is never in params, share links, saved views, presets, packed pages or `localStorage`** (a unit test checks it, with the picture, its note and every
setting). The picture settings that change a picture are part of the cache identity of a decision (`@i<hash>` in the model id) when pictures are sent, and absent when they are not; the plan
view only counts with the isolated picture and the margin only with the context picture.

**Where pictures are read.** On the **endpoint** backend always. In the **browser** backend only when the export has a **vision graph** (the manifest says so and lists its file): the
default export (warsang/d3-edge-web) reads text only, so the Images option stays visible but disabled with "The d3 export in use reads text only. Use the endpoint backend, or an
export with a vision graph." and a decision made with it is labelled as text only. See [Your own export, with pictures](#your-own-export-with-pictures-in-the-browser). Jev has a **Send images to Jev** switch, off by default and documented as
**untested** (Jev is not known to read images); it uses the same picture settings.

## Geometry as SVG text

`geometryText: "svg"` puts the shape of the element into the `state` of the request as native vector markup, so the model reads it as **text tokens**. It needs no picture and no vision
graph: it works with the text-only browser export (warsang), the endpoint and Jev. It is built by `src/classify/geometrySvg.ts` (pure, tested in Node) from the meshes of the loaded model.

- **Isolated** (always): the element alone, orthographic: a **plan** and one **elevation** (seen across the longest horizontal side), as simplified outlines: the convex hull of the projected mesh,
  simplified (Douglas-Peucker, a few points); a round outline is a `<circle>`, a filled rectangle a `<rect>`. Metres, IFC frame (X east, Y north, Z up), origin at the minimum corner of the bounding box, at most 2 decimals.
  The class, the predefined type and the size are attributes: `<svg id='plan' data-class='IfcPipeSegment' data-type='RIGIDSEGMENT' data-size='0.27x0.27x2' viewBox='0 0 0.27 0.27'>...`.
- **Context** (`geometryContext`, default on): the same two views of the bounding box grown by `imageMargin` (as for the context picture), with every other element that touches the box as an outline **clipped to the box**
  (Sutherland-Hodgman) in `<g data-class='IfcPump' data-tag='P-101A'>` (class and tag only: **never a classification result**), nearest first, tiny ones (under 2 % of the box) left out, at most 25. The element is `<g id='target'>`.
- A legend goes first: `Geometry as SVG, metres, plan then elevation; ... target element id=target.` The whole text is one line in `state.geometry`, after the note about the pictures when there are pictures. Attributes use
  single quotes, so the JSON state needs no escapes (each escape costs a token). The text is **not** counted in `d3MaxStateBytes`; it has its own budget of about **1500 tokens** (estimated at 3 characters a token): over it, the farthest neighbours
  are dropped first, then the outlines are simplified harder. Measured on the 51 representative elements of the real bench: the element alone about 110 tokens (largest 137), with the box about 750 on average (largest 1,479).
- The torso runs **once per question** over the whole prompt, so the tokens multiply by the questions (4 passes per element). d3-edge takes up to 32k tokens, so the length is not a limit; the time is (see below).
- The drawer shows the **same markup** for the selected element, rendered (the target in orange; the styles are for the preview only) and as text, with the token estimate. `window.__xrayClassify.geometry(id)` returns it.
- It is part of the cache identity (`@g<hash>`: with the box or not and the margin) for Jev and d3, and nowhere else. **It is never in params, share links, saved views, presets or packed pages** (the leak test checks it).
- Drawing: `bench/classify-geometry-svg.png` (pipe, pump, beam, wall: the element's plan and elevation, then the box views).
- Limits. The outline is a convex hull: a wall with a door opening is a plain rectangle in the isolated views, an L is filled. Round parts are only a circle when the outline is round within 5 %.

### The real bench with pictures and SVG (51 signatures)

`bench/real-classify-decision.mjs` with `PROVIDER=d3 D3_MM=1` (our export, onnxruntime-node CPU, **default calibration** `auto`/T = 1: raw agreement) on the same 51 signatures that a final rule labels in the bundled models
(fzk-haus 16, synth5k 9, building 10, plumbing 2, debris-demo 13, Infra-Electrical 1). The pictures come from `bench/d3/make-bench-pictures.mjs` (a headless browser draws the real elements, render, 384 px, isolated then context),
the SVG from the same script with `GEOMETRY_ONLY=1`. Agreement with the rules (the rules are proxy labels, not the truth):

| Arm | Discipline | Sub-discipline | Division | prompt tokens, 51 elements | discipline `GEN` (fallback) |
| --- | --- | --- | --- | --- | --- |
| (a) text only | **24/51** | **24/51** | **23/49** | 120,049 | 20 |
| (b) text + SVG, element alone | 15/51 | 15/51 | 12/49 | 146,061 | 32 |
| (c) text + SVG, element alone + box | 19/51 | 18/51 | 10/49 | 356,685 | 30 |
| (d) text + 2 pictures (render, isolated + context) | 18/51 | 16/51 | 12/49 | 184,841 | 22 |
| (e) text + SVG (alone + box) + 2 pictures | 14/51 | 13/51 | 11/49 | 423,645 | not counted |

Text only with our export gives the same 24/51, 24/51, 23/49 as warsang's export did (the export is faithful). **Every arm that adds geometry is worse than text only on this proxy**, by 5 to 10 elements out of 51: against (a), (d) fixes 5 and breaks 11
discipline answers, (b) fixes 1 and breaks 10, (c) fixes 3 and breaks 8, and the shape arms push the model towards `GEN` (the General fallback) more often. Read this with care:

- The rules **partly judge by shape and name too** (class, name and properties are in the text already), so the 51 proxy labels are the cases where text is enough; they are exactly the cases where the model has nothing to gain from a picture. The bench cannot say that
  pictures or SVG help for the parts that the rules **cannot** label (that is what they are for), and it has no truth set for those.
- d3-edge was trained with images and with long text states, but not on BIM line drawings or this SVG dialect; the 0.6B model reads 100 to 1,500 more tokens of geometry per question and it is less sure (more `GEN`). Calibration (`fitted` on the rules) could shift this; the bench uses the default as asked.
- Nothing here chooses between `render` and `vector`, or SVG and pictures, for the viewer: the defaults stay **off**.

Time per element (the main request with 3 questions and the sub request: 4 torso passes; Node CPU, mean of 3 runs after a warm-up; the SVG arms use the text of the same elements):

| | text only | SVG, element alone | SVG, element + box | 1 picture | 2 pictures |
| --- | --- | --- | --- | --- | --- |
| pipe spool | 7.5 s (2,890 tokens) | 9.5 s (3,494) | 16.7 s (5,958) | 9.9 s (3,646) | 11.8 s (4,230) |
| pump | 7.0 s (2,622) | 8.1 s (3,154) | 12.9 s (4,894) | 9.7 s (3,378) | 11.5 s (3,962) |

(The earlier table of this page, run with other background work, gave 8.4 / 11.3 / 12.9 s for the pipe and 7.5 / 10.4 / 13.2 s for the pump.) The SVG with the box costs about as much as two pictures or more on this CPU because every one of its 700 to 1,500
tokens runs through the torso 4 times; the element alone costs about 100 tokens. Memory: a request with SVG and the box (6,000 tokens) needs about 8 GB in onnxruntime-node CPU, so run one such process at a time.

## Scoring against a ground truth, from the command line

`npm run classify:truth` scores the classifiers on any IFC for which you have a ground truth, without the GUI:

```
cd web
npm run classify:truth -- --ifc <path.ifc> --truth <truth.json> [--arms rules,majority,xsmall,base2,d3,hybrid-d3] [--out dir] [--limit N] [--props common|all]
```

It checks the truth file against the shipped schema, converts the IFC to its element sidecar with `tools/ifc2glb.py` (into `<out>/sidecar/`),
checks that every element has a truth entry, runs `bench/real-classify-truth.mjs --sidecar <sidecar>` and prints the markdown tables (also
`<out>/truth-bench.md` and `truth-bench.json`). The default arms are `rules,majority,xsmall,base2,d3,hybrid-d3` (`hybrid-d3`: the rules where
final, else d3); `--arms rules,majority` needs no model files. Results are cached per signature in `<out>/cache`, so a rerun with the same `--out` redoes
nothing. `--props` is the converter's property mode (`common` is what the viewer's own IFC import keeps; `all` also keeps vendor property sets).
The d3 and DeBERTa arms find their files as the bench does (env `D3_DIR`, `ORT_NODE`, `TRANSFORMERS_NODE`); the script sets `NODE_USE_ENV_PROXY=1`.

The truth file is `xray-truth/1`: `{ format, model, generator, schema, convention, elements: { <GlobalId>: { name, ifcClass, discipline, subDiscipline,
division, alt? } } }`, where `alt` may hold `subDiscipline` (same discipline) and `division` lists, which the lenient column accepts, plus informational
`discipline` and `also` (`"DISC/sub"`) entries.

Exit codes: `0` done; `2` bad truth file (not JSON, wrong format, a discipline, sub-discipline, division or alternate that the schema does not have)
or an element of the model without a truth entry (a truth entry without an element is only a warning); `3` the converter or the bench failed;
`64` bad usage. So it can run in CI. The checks are in `tools/classify-truth-lib.mjs`, tested by `tests/classify-truth-cli.test.ts`.

The independent test facility is `models/independent/Water-Works.ifc` with `Water-Works.truth.json`, made by `tools/make_independent_plant_ifc.py`
(a water treatment works with a different naming style; see `models/NOTE.md`). Its numbers are in `bench/truth-bench-independent.md`. The rules were not tuned on it.

## Number of calls

Measured on the shipped models, with the mock provider (the numbers do not depend on the provider):

| Model | Elements | Rules (final) | Signatures to the model | Requests | Source counts |
| --- | --- | --- | --- | --- | --- |
| `synth5k`, default | 5000 | 5000 | 0 | **0** | rules 5000 |
| `synth5k`, rules off | 5000 | 0 | 9 | **18** | model 9, cache 4991 |
| `fzk-haus`, default | 82 | 40 | 1 (the 42 `IfcMember`) | **2** | rules 40, model 1, cache 41 |
| a repeat of any run | | | | **0** | cache |

For the decision provider a "request" is one `decide` call; each is several forward passes of the NLI model (see [Passes](#setup-the-decision-model-in-the-browser-recommended-local-option)).

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
  "codeList": "Discipline",
  "edition": "co.acme.standards@1.0.0",
  "psetName": "XR_Classification",
  "minConfidence": 0.6,
  "properties": { "discipline": "Discipline", "subDiscipline": "SubDiscipline", "masterformatDivision": "MasterFormatDivision",
                  "masterformatTitle": "MasterFormatTitle", "confidence": "Confidence", "source": "Source", "model": "Model",
                  "needsReview": "NeedsReview" },
  "fallbackDiscipline": "GEN",
  "disciplines": [
    { "code": "MEC", "label": "Mechanical and HVAC", "description": "Heating, ventilation and air conditioning: ducts, fans, ...",
      "rulesKey": "MEC", "origin": "throughline", "crosswalk": null, "meaning": null, "sortOrder": 20,
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
"throughline"`); `ARC`, `PLB`, `FPR`, `TEL` and the fallback `GEN` are added (`origin: "added"`; `PLB` and `FPR` suggest the crosswalk `PIP`, `TEL` suggests
`ELE`). Throughline's `PRO` (process) is merged into `PIP` here, because the specification asked for "Piping/Process" as one discipline. The optional fields
`codeList`, `edition` and, per discipline, `crosswalk`, `meaning` and `sortOrder` carry the Throughline `CodeValue` fields (below); they do not change a
decision, so they are not part of the schema hash.

### Your own schema

- In the drawer: **Load schema file**. The file is checked (plain messages for each problem) and kept in `localStorage`
  (`xray.classify.schema.v1`); **Use built-in schema** goes back.
- By URL: the `schemaUrl` setting (also in a params document or `xray-pack --params`).
- From a script: `window.__xrayClassify.setSchema(jsonObjectOrText)` returns the list of problems (empty: accepted).
- In Node: `parseSchema(json)` and pass `schema` to `classifyInputs`.

A new schema has a new hash, so caches and manual overrides of the old one are not mixed in.

### Throughline alignment

The target schema is Throughline's (read from `/home/user/studious-lamp/schema/modules/engineering/`; "Truxion" in the first request was a typo).
A coded list is an `engineering.CodeList` registry entry (`standard.yaml`); each value of it is an `engineering.CodeValue` row (`code_value.yaml`,
`events.yaml`, `docs/modules/engineering/standards.md`):

| `CodeValue` field | Meaning | Here |
| --- | --- | --- |
| `code_list` | The list the value belongs to | `Discipline` (`schema.codeList`) |
| `code`, `label` | The value | `disciplines[].code`, `label` |
| `meaning` | An IRI that says what the value means | `disciplines[].meaning` |
| `crosswalk` | The **company** code that a project-added value maps to | `disciplines[].crosswalk` |
| `origin` | `company` or `project` | `throughline` and `company` are `company`; anything else (`added`, `project`) is `project` |
| `sort_order` | Position in the list | `disciplines[].sortOrder`, else 10, 20, 30, ... |
| `edition` | The standards edition, `co.acme.standards@1.0.0` | `schema.edition` |
| `attributes` | List-specific JSON | `description`, `sub_disciplines`, `rules_key`, `fallback` |

Elsewhere `discipline` is a plain code of that list: `documents.Document.discipline` ("a value of the code list `Discipline`") and
`correspondence.TechnicalItem.discipline` ("a code of the project standards, for example `M`, `E`, `C`"). The sub-discipline and the
MasterFormat division are **not** Throughline code lists, so the export carries them as `attributes`, as a code list's own `attributes` do.

**Import** (`importDisciplineList`, drawer button **Import Throughline list**, `__xrayClassify.importThroughline(json)`,
`service.importThroughline(json)`): a JSON list of `Discipline` entries, or an object with `values`, `code_values` or `entries`, becomes the
schema. Entries of another list, and retired or superseded ones (`lifecycle`, `effective_to`), are skipped with a note. `label` and `code` carry over; the
text the decision model reads is `attributes.description` (the label when there is none, with a warning); `attributes.sub_disciplines`
(`{ code, label, description }`) gives the sub-disciplines; `origin`, `crosswalk`, `meaning`, `sort_order` and `edition` carry over; `attributes.fallback: true` (else `GEN`, else the
first entry) marks the discipline for elements that nothing could place. **The built-in rules keep working** when the project's codes differ from ours: `attributes.rules_key`
(else the `crosswalk`, else the code itself) names the rules code it replaces, so `M` with `rules_key: MEC` still gets ducts from the rule. The MasterFormat list is the shipped one
(Throughline has no MasterFormat list). A new schema has a new hash, so decisions of the old one are not reused. A file that is not a list gets a plain message.

**Export** (`exportThroughline`, drawer button **Export Throughline JSON**, `__xrayClassify.export('throughline')`): `xray-throughline-classification/1`.

```json
{
  "format": "xray-throughline-classification/1",
  "model": "fzk-haus",
  "count": 82,
  "code_list": { "code_list": "Discipline", "edition": "local:xray-throughline-aligned-default@1.0.0", "schema_title": "Throughline-aligned default", "schema_version": "1.0.0", "schema_hash": "..." },
  "code_values": [
    { "code_list": "Discipline", "code": "MEC", "label": "Mechanical and HVAC", "meaning": null, "crosswalk": null, "origin": "company", "sort_order": 30,
      "edition": "local:xray-throughline-aligned-default@1.0.0", "effective_from": null, "effective_to": null,
      "attributes": { "description": "...", "sub_disciplines": [ { "code": "DUC", "label": "Ductwork", "description": "..." } ] } }
  ],
  "needs_crosswalk": ["ARC"],
  "elements": [
    { "global_id": "2O2Fr$t4X7Zf8NOew3FLOH", "discipline": "PLB", "discipline_origin": "project", "crosswalk": "PIP",
      "attributes": { "sub_discipline": "SUP", "sub_discipline_label": "Domestic water supply", "masterformat_division": "22", "masterformat_title": "Plumbing",
                      "masterformat_section": null, "masterformat_edition": "MasterFormat 2018", "confidence": 0.93, "source": "model", "model": "decision:...", "needs_review": false } }
  ]
}
```

- `elements[].discipline` is a code of the `Discipline` list, never free text; `discipline_origin` and `crosswalk` say whether it is a company value or a
  project value and which company code it maps to.
- `code_values` is the whole list as `CodeValue` rows, so **the export file imports again** with the same importer (a round trip test keeps this true).
- `needs_crosswalk` lists the codes the elements use that are project values without a crosswalk (`ARC` in the default: Throughline's sample company list has no
  architectural discipline). A closed company list (`value_list_policy: closed`) takes company codes only: load the real list, or add the crosswalk, before you
  load the results into Throughline.

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

## Review walk

The **Review walk** (drawer section **Review**, the command palette entry "Classify: review walk", key **Shift+R**) visits the
classified elements one work item at a time, shows what the classifier proposes and why, and records your answer as a
**committed change**. Classify first (rules only is enough): the walk visits elements that have a result.

### Order and filters

| Order | Items | Sequence |
| --- | --- | --- |
| **By type, then location** (default) | One item per kind of element: same classification signature and same codes, confirmed once for all N | Storey (lowest first), system, discipline (schema order), position (serpentine sweep). Elements in no storey or no system come last. Inside an item the elements are in sweep order and you can step through them with `[` and `]` |
| **Along systems** | One per element | Per distribution system (by name, "no system" last) the run is walked from one end: the end is found by two sweeps (farthest from the centroid, then farthest from that one), then each step goes to the nearest element left (gap between bounds, then centre distance) |
| **By location** | One per element | Storey by storey, a serpentine sweep (rows along Z, X up then down) |
| **Needs review first** | Like by type | Lowest overall confidence first, then the smallest discipline margin |

Every order is deterministic. Filters: **Only needs review**, **Only unconfirmed** (leaves out kinds that are committed already; a commit flagged unsure does not count as settled),
**Only unsure** (committed as a guess), **Only skipped** (revisit what you skipped in this session) and a discipline list. The header counts the elements in scope: *confirmed, corrected, remaining* (pending changes count).

### At each item

The camera frames the element (or all N elements of the type) with the existing fly-to, the elements are the selection, and the
x-ray machinery ghosts the context. **Esc** ends the walk and restores the camera and the selection you had. The panel shows
class, name, tag, storey and system; the proposed discipline, sub-discipline and division, each with its confidence and its
source (rule, model id, cached model, manual, or "confirmed by ..."); the rule rationale; the **runner-up** (the second choice
for the part with the narrowest margin, checked against the schema); "needs review"; and "The model now disagrees" when a later
run says something else than the committed value.

| Action | Key | Button |
| --- | --- | --- |
| Confirm | Enter or Y | **Confirm** |
| Take the runner-up | 2 | **Use XYZ** |
| Correct (pickers for the three codes, sub-discipline restricted to the chosen discipline, schema values only) | E, then Enter to apply | **Correct...**, **Apply correction** |
| Skip (see below) | N or right arrow; Shift+N for the other skip in a type | **Skip**, or **Skip this one** and **Skip all N** in a type |
| Back | left arrow | **Back** |
| Flag the next action as a guess | `?` (Shift+/) | checkbox **Unsure (a guess)** |
| All N of this type or this element only | A | radio buttons |
| Undo the last pending item | U | **Undo last** |
| Previous / next element of the type | `[` / `]` | **‹**, **›** |

An optional comment goes into the change. On a phone the panel is a bottom sheet with large buttons; no key is needed. The decision
buttons and the Unsure box sit in a fixed strip under the scrolling part, so **Skip** and **Unsure** are on screen without scrolling.

### Skip

Skip is available in every state: at an item, with the correction form open, after **Back**, and at an element of a type that you step
through with `[` and `]`. **Skip leaves the element as it is.** It is not a change: nothing goes into the pending set, nothing is committed
and nothing enters the review log.

- In a type of N elements, **Skip this one** skips the element in view and steps to the next element of the type (to the next item after
  the last); **Skip all N** skips every element of the type and goes to the next item. The key **N** (and the right arrow) does the one
  that matches the scope radio (**All N of this type** skips all N, **This element only** skips this one); **Shift+N** does the other.
  Both buttons are always there, with their keys on them.
- With the correction form open, **Skip** (or N, or the right arrow, when a picker does not have the focus) drops the unsaved correction
  and moves on. **Cancel** (Esc) closes the form and stays.
- The header shows **Skipped (n)**: the elements skipped in this session. Click it, or tick **Only skipped**, to walk only those (a type
  shows only its skipped elements); click it again to go back. Deciding an element (confirm, runner-up, correct) takes it off the list.
- The list lives in memory for the session and for the model on screen. It is not stored, exported or committed.
  `window.__xrayClassify.review.skipped()` returns it.

### Unsure (a guess)

Optional, off by default: tick **Unsure (a guess)** or press `?` (it also shows in the correction form) before **Confirm**, **Use XYZ**
or **Apply correction**. The flag applies to that one action and clears after it (and when you move to another element). `?` was chosen
because it asks a question; the walk takes it while its panel is open (the keyboard cheat sheet is still on F1).

An unsure change still sets the codes, but it is a guess:

| | Sure (default) | Unsure |
| --- | --- | --- |
| Log change | no `unsure` field | `"unsure": true` |
| Source | `confirmed` or `corrected` | `confirmed` or `corrected`, with an unsure marker (`unsure: true` on the result, `?` after the source in the table) |
| Confidence | 1 | `UNSURE_CONFIDENCE` = **0.75** (`classify/reviewLog.ts`); the change's `after.confidence` records it |
| `needsReview` | false | **true**: it comes back in "Needs review first" and "Only needs review" |
| Calibrate on confirmed | counts as truth | left out |

The **Pending** and **History** tabs show an `unsure` tag on each such change. A later change of the same element wins, so a sure
confirmation of an element that was committed as unsure replaces the guess (the same codes are not left out as "already committed" when
the sureness differs), and an unsure flag on a sure element is recorded too. A revert of a commit brings back the earlier sureness.

### Pending changes, commits, history

A confirmation or correction first goes into the **pending** set (tab **Pending**: one row per item, each with **Undo**). **Commit N
changes** writes one immutable commit:

```json
{ "id": "cmwc5i5o0f74o", "author": "RF", "time": "2026-11-11T13:20:01.000Z", "note": "first pass",
  "modelName": "process-plant", "modelFingerprint": "9f3c...16 hex", "schemaEdition": "1.0.0",
  "changes": [ { "globalId": "...", "before": { "discipline": "PIP", "subDiscipline": "UTL", "division": "40", "source": "rules", "confidence": 0.92 },
                  "after":  { "discipline": "MEC", "subDiscipline": null, "division": "40", "source": "corrected", "confidence": 1 },
                  "action": "correct", "comment": "walked on site" } ] }
```

A change that was flagged unsure has one more field, `"unsure": true` (with `after.confidence` 0.75). It is additive: **absent means false**,
so logs written before the flag and imports of them stay valid under the same format id. The validator accepts `true`, `false` or no
field, and refuses anything else.

`modelFingerprint` is a hash of the sorted element GlobalIds and the schema hash, so a log never applies to another model or schema.
`reverts` is added to a commit that reverses another. Commits are **append only** and frozen in memory. **Revert** (tab
**History**) appends a new commit that puts the state before the old commit back for every element that no later commit
changed again; the old commit stays. The **History** tab lists who, when, note and count, and opens a commit to show its changes.

The reviewer's name or initials are asked once, at the first commit, and kept in this browser (`localStorage`,
`xray.classify.reviewer.v1`). **A name is personal data**: it is never in the params, a share link, a saved view, a preset, a packed page
or the model properties. It is in the review log (and so in its export and in the exports of results), which are files you choose to make.

### Where the log lives

Per model fingerprint, in IndexedDB (database `xray-classification-review`, store `logs`), with `localStorage`
(`xray.classify.review.v1.<fingerprint>`) as the fallback when IndexedDB is missing, blocked or fails. Every call is wrapped: if both
fail, the walk still works for the session and the History tab says "Not saved on this device". A load merges both places by
commit id.

### Effect on results, and re-runs

The effective state of the log (the latest change per element, in time order) becomes the result of the element: source
`confirmed` or `corrected`, confidence 1, `needsReview` false, with `confirmedBy`, `confirmedAt` and `commitId` (a change flagged unsure gives
confidence 0.75, `needsReview` true and `unsure: true`, see [Unsure](#unsure-a-guess)). This wins over
rules, cache, model and a manual override, and **a re-run never overwrites it**: the run still computes the element, and where it
differs from the committed codes the walk and the table (a `!` after the source) say **the model now disagrees**
(`window.__xrayClassify.review.disagreements()`). **Clear results** keeps committed results, like manual ones. A revert brings back the latest
computed result (or the manual one). The written property `Source` says `confirmed` or `corrected`; the name is not written.

### Exports

The JSON, CSV (`ConfirmedBy`, `ConfirmedAt`, `CommitId`, `Unsure`, the last column, `true` or `false`) and Throughline exports
(`confirmed_by`, `confirmed_at`, `commit_id` and `unsure` in the attributes of a committed element only) carry the confirmation. **Export review log** saves `xray-classification-review/1`:

```json
{ "schema": "xray-classification-review/1", "modelName": "...", "modelFingerprint": "...", "schemaEdition": "...", "exportedAt": "...", "commits": [ ... ] }
```

**Import review log** replays a file: commits whose id is in the log already are skipped (importing twice changes nothing), and a file
with another fingerprint is refused with a message that names both fingerprints. Commits replay in time order.

### Calibrate on confirmed

Next to **Calibrate on rules**: the committed labels count as truth (one label per signature, the most frequent codes when
elements of a signature were labelled differently) and the same fit runs (the model scores the committed kinds of element, a held-out share is
reported, at least 8 kinds and 4 answers per question). Use it when the rules are not a good proxy for your standard.
**Changes flagged unsure are left out** (they are guesses, not truth). The result message says so: "N confirmed used, M unsure left out"
(committed elements). If every commit is unsure the button explains that and does nothing.

Smoke test: `SMOKE_PORT=5699 node bench/smoke-review.mjs` (screenshots `bench/review-walk-*.png`). Unit tests: `tests/classify-review.test.ts`;
the leak test (`tests/classify-settings.test.ts`) also checks that the reviewer's name is in no params, link, view, preset or packed page.

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
| `export('json' \| 'csv' \| 'throughline')` | The export text. `throughline` is the Throughline shape, see [Throughline alignment](#throughline-alignment) |
| extras | `estimate`, `configure`, `settings`, `setKey`, `keyState`, `testConnection`, `selectNeedsReview`, `colourByDiscipline`, `state` |
| decision model | `testModel()` (load, one tiny choice, load time, device, data type, size), `setHfToken(token, remember?)`, `hfTokenState()`, `modelCache()`, `clearModelCache()`, `decisionStats()` (requests, pairs, passes), `webllmStats()` |
| Throughline | `importThroughline(json)` returns `{ errors, warnings }` |
| calibration | `calibration()` (mode, what is in use, the numbers of the last fit), `calibrate({ maxSignatures?, heldOut? })` (**Calibrate on rules**), `calibrateConfirmed(...)` (**Calibrate on confirmed**), `forgetFit()` |
| review walk | `walk.open({ order? })`, `walk.close()`, `walk.state()`, `walk.items()`, `walk.goto(i)`; `review.ready()`, `reviewer()`, `setReviewer(name)`, `fingerprint()`, `pending()`, `propose(ids, { action, codes?, item?, comment?, unsure? })`, `undoPending(item)`, `commit(note?)`, `revert(id, note?)`, `history()`, `exportLog()`, `importLog(text)`, `disagreements()`, `storage()`, `skipped()` |
| d3 and pictures | `setD3Key(key, remember?)`, `d3KeyState()`, `confirmD3Download()`, `thumbnails(id)` (the data URLs the model would get) |

Types (`src/classify/types.ts`): `ClassifyInput { id, ifcClass, name, psets, quantities?, type?, hierarchy?: { path, parents? },
systems?, material? }` and `ClassifyResult { id, discipline: { code, label, confidence, probabilities }, subDiscipline | null,
masterformat: { division, title, confidence, probabilities } | null, buildingElement, source: 'rules' | 'cache' | 'model' |
'manual' | 'confirmed' | 'corrected', model?, needsReview, rationale?, confirmedBy?, confirmedAt?, commitId? }`. Providers implement `DecisionModel { decide(state, questions, signal) }` and return
the Jev response shape.

In Node:

```ts
import { classifyInputs, defaultSchema, createJevProvider } from './src/classify';
const provider = createJevProvider({ endpoint: '/api/jev', model: 'jev-1.13.0', apiKey: () => null, timeoutMs: 30000 });
const { results, stats } = await classifyInputs(inputs, { schema: defaultSchema(), provider });
```

Commands (palette): `classify.selection`, `classify.all`, `classify.review`, `classify.walk` (key Shift+R), `classify.stop`, `classify.colour`.

## Key security

- The API key, the **d3 endpoint key** (its own entry, `xray.classify.d3Key`: a Jev key never goes to a d3 server and the other way round), the **Hugging Face token** (decision provider and d3 in the browser)
  and the **pictures** of elements (data URLs) are **never** in the params document, the share link (`#p=`), the exported params JSON, saved views, presets or packed
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

The WebLLM model list and `vram_required_MB` were read from the `@mlc-ai/web-llm@0.2.87` package, and the download sizes from the model
repositories on huggingface.co; the WebLLM load from the CDN was not run in this environment (no WebGPU, no model download), only a fake engine in the
tests. The decision provider was run for real on the WASM and CPU paths (see below); its WebGPU path was not run.
