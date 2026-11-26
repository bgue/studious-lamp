# Offline classification and interactive confirmation

Status: spec, 2026-11-26. **Not to be implemented before the next release.** Builds on
`docs/design/classification-facets.md` (facets, `XR_` namespace, batch mode, models) and
`docs/design/concrete-classification.md` (concrete facets).

## 1. Goal

Classify a model without the viewer (a command line, a server, a nightly job), then let people confirm the doubtful results
interactively: in the viewer, in a single offline HTML file, or in a terminal. Decisions flow back into the results, into the
IFC, and into the next run, so confirmed items are never asked again.

Non-goals: a hosted service, user accounts, real-time multi-user editing.

## 2. Parts

| Part | What it is |
| --- | --- |
| Headless core | The classify pipeline, facets and concrete engines running in Node: IFC reading, geometry, rules, providers, cache, batch |
| `xray-classify` | The command line: `run`, `review`, `apply`, `inspect`, `stats` |
| Review package `.xrc.json` | The machine's results for one model, versioned, self-describing |
| Decisions file `.xrd.json` | What people decided, small, one per reviewer session, mergeable |
| Viewer review | "Open review package", the review walk driven by a package, decisions export |
| Packed review page | `xray-pack --classification`: model + viewer + package in one HTML file, no server |
| Terminal review | `xray-classify review`: a text walk for quick decisions |

## 3. Headless core

- The pipeline modules under `web/src/classify/` (rules, facets engine, concrete engine, questions, calibration, cache,
  batch) must import nothing from the DOM, three.js renderer or the app. Browser-only pieces sit behind interfaces:
  - `ModelSource`: elements, properties, materials, hierarchy, storeys (viewer: the loaded model; Node: web-ifc, reusing the
    reader of `web/tools/xray-4d`).
  - `GeometrySource`: world-space triangles per element and a ray caster (viewer: the renderer's BVH; Node: web-ifc meshes and
    three-mesh-bvh, which already run under the 4D CLI).
  - `CacheStore`: viewer `localStorage`; Node a JSON file next to the package (`<model>.xrc-cache.json`) or `--cache DIR`.
  - `Provider`: `rules` (no model), `decision` (transformers.js under Node with onnxruntime-node or its wasm backend; same
    model ids as the viewer), `embed` (transformers.js feature extraction), `jev` and `d3` (HTTP, as today). `webllm` is
    browser-only and is refused by the CLI with a clear message.
- Batch mode (facets design, section 8) is built here, once, as part of the core: signature grouping, measured and rule facets
  first, batched model calls, learn-as-you-review from decisions, resume. The viewer's **Classify all** calls the same code.
- Determinism: for a given model file, schema, provider, model id, calibration and prior decisions, the results are identical
  (sorted outputs, seeded tie-breaks), so packages diff cleanly.

## 4. `xray-classify` command line

Installed with the other tools in `web/tools/` (`node web/tools/xray-classify.mjs` or the `xray-classify` bin).

```
xray-classify run <model.ifc> [more.ifc ...]
    [--schema schema.json]                 default: the shipped schema
    [--facets all | discipline,trade,placement,material,phase,orientation,classrepair,concrete]
    [--scope all | unreviewed | needs-review]
    [--provider rules | decision | embed | jev | d3]  [--model <id>]  [--endpoint <url>]
    [--prior decisions.xrd.json ...]       confirmed items are kept as decided and not asked again
    [--calibration auto | fitted | off]
    [--workers N] [--batch-size N] [--max-calls N] [--resume]
    [--cache DIR]
    [--write-ifc out.ifc]                  the IFC save of the viewer (XR_ sets, classification references), headless
    -o results.xrc.json

xray-classify review <results.xrc.json> [--facet trade] [--only needs-review] [--decisions out.xrd.json] [--reviewer NAME]
xray-classify apply <decisions.xrd.json ...> --to <results.xrc.json> [-o merged.xrc.json] [--write-ifc out.ifc] [--model model.ifc]
xray-classify inspect <results.xrc.json>   counts by facet and code, needs-review share, sources, provider, model hash
xray-classify stats <results.xrc.json> --truth truth.json   accuracy per facet against a truth file (benchmarks)
```

- Exit codes: 0 done; 1 bad input; 2 provider unavailable; 3 interrupted (resumable with `--resume`).
- Progress on stderr (signatures done, calls, estimated time); a JSON summary on stdout (like the 4D CLI).
- Secrets: endpoint keys only from environment variables (`XRAY_JEV_KEY`, `XRAY_D3_KEY`) or the proxy; never from flags, never
  written to any output.
- `--write-ifc` writes a new file and never overwrites the input (the save code of `web/src/ifcsave`, unchanged).

## 5. Review package `.xrc.json`

Schema id `xray-classify-results/1`. One file per run; several models of a federation in one package, keyed by file.

```jsonc
{
  "schema": "xray-classify-results/1",
  "created": "2026-12-01T09:00:00Z",           // no user names
  "tool": "xray-classify 32",
  "models": [{ "file": "AC20-FZK-Haus.ifc", "sha256": "...", "ifcSchema": "IFC4", "elements": 82 }],
  "classificationSchema": { "title": "...", "version": "...", "hash": "..." },
  "facets": ["Discipline", "Trade", "Placement", "Material", "Phase", "Orientation", "ClassRepair", "ConcreteElement", "..."],
  "provider": { "kind": "decision", "model": "MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33", "calibration": "auto" },
  "prior": [{ "file": "decisions-2026-11-30.xrd.json", "sha256": "..." }],
  "signatures": [{ "id": "s17", "class": "IfcWallStandardCase", "label": "Wand-Ext-ERDG-* (Leichtbeton)", "elements": 8 }],
  "elements": [
    {
      "file": "AC20-FZK-Haus.ifc", "globalId": "2XQ$n5SLP5MBLyL442paFx", "signature": "s17",
      "facets": {
        "Trade": { "code": "CONC", "confidence": 0.81, "source": "rule", "needsReview": false,
                   "alternatives": [["MASON", 0.12], ["FACADE", 0.04]], "rationale": "a wall of concrete", "fields": {} },
        "Orientation": { "code": "VERTICAL", "confidence": 1, "source": "geometry", "fields": { "Tilt": 90, "Azimuth": 0, "Plausible": true } }
      }
    }
  ],
  "stats": { "calls": 31, "signatures": 44, "needsReview": 12, "seconds": 48.2 }
}
```

- `alternatives`: the top 3 with probabilities when the source is a model; empty for measured values.
- Fields of each facet are exactly the `XR_<Facet>` fields of the facets design, so applying a package writes the same
  properties the viewer writes.
- Large models: the file may be gzipped (`.xrc.json.gz`); readers accept both.
- A JSON Schema is generated for it (LinkML source in `schema/linkml/xray_classify.yaml`, like the 4D schema), with SQL DDL for
  phase 5.

## 6. Decisions file `.xrd.json`

Schema id `xray-classify-decisions/1`. Append-only within a session; one file per reviewer session; many files merge.

```jsonc
{
  "schema": "xray-classify-decisions/1",
  "package": { "sha256": "...", "models": [{ "file": "AC20-FZK-Haus.ifc", "sha256": "..." }] },
  "session": { "started": "...", "tool": "viewer 32", "reviewer": null },   // reviewer only with explicit opt-in
  "decisions": [
    { "at": "...", "file": "AC20-FZK-Haus.ifc", "globalId": "...", "facet": "Trade",
      "action": "accept" | "change" | "unsure" | "reject",
      "code": "MASON", "fields": {}, "scope": "element" | "signature", "note": null }
  ]
}
```

- `scope: "signature"` records "accept all like this": it applies to every element of that signature in the package.
- Merge rules (`apply`): the latest decision per (element, facet) wins within one file; across files, equal decisions merge,
  different decisions on the same item are a **conflict**, listed and left undecided unless `--prefer <file>` is given.
- Applying sets `Source = manual`, `Confidence = 1`, `NeedsReview = false` for accepted and changed items; `unsure` keeps the
  machine value with `NeedsReview = true` and a flag.

## 7. Interactive confirmation

### 7.1 In the viewer

- **Open review package** (Classification tab, also drop the file): checks the model hash; on a mismatch shows which file and
  offers "apply by GlobalId anyway" (elements not found are counted and listed).
- The review walk (`Shift+R`, existing keys) takes its queue from the package: needs-review first, ordered by uncertainty
  (lowest confidence, then smallest margin to the second alternative), filter by facet and by code, and shows the
  alternatives with their probabilities as one-key choices (`1`, `2`, `3`).
- **Accept all like this** (`A`): accepts the value for the whole signature, after showing how many elements it covers.
- Every decision is written to an in-memory decisions file; **Export decisions** saves `.xrd.json`; **Apply and save IFC**
  applies them and opens the IFC save with facets ticked.
- Works on a phone (bottom sheet) as the review walk does today.

### 7.2 Packed review page

- `xray-pack model.ifc --classification results.xrc.json [--facet trade] -o review.html` builds a single offline HTML file with
  the model, the viewer and the package, opening straight into the review walk.
- The reviewer's decisions stay in that browser (local storage, per package hash) and are exported with **Export decisions**;
  nothing is sent anywhere. The page shows a reminder to export before closing.
- Size: as other packed pages; the package is embedded gzipped.

### 7.3 Terminal review

- `xray-classify review results.xrc.json`: one item per screen: element name, class, storey, the signature size, the facet, the
  machine's choice and alternatives with probabilities, the rationale; keys `y` accept, `1-3` choose an alternative, `e` type a
  code, `u` unsure, `a` accept all like this, `s` skip, `b` back, `q` save and quit. Writes `.xrd.json` continuously (safe to
  quit at any time).
- No 3D: `o` prints a viewer link (a share link with the element selected) for items that need a look.
- Plain text, no colours required; works over SSH.

## 8. The loop

1. `xray-classify run model.ifc -o r1.xrc.json` (overnight, or in CI when a new model revision arrives).
2. Reviewers confirm in the viewer, the packed page or the terminal → `d1.xrd.json`, `d2.xrd.json`.
3. `xray-classify apply d1.xrd.json d2.xrd.json --to r1.xrc.json -o r1b.xrc.json --write-ifc model.classified.ifc`.
4. Next revision: `xray-classify run model-v2.ifc --prior d1.xrd.json d2.xrd.json -o r2.xrc.json`: confirmed elements (matched by
   GlobalId, and by signature for new elements of a confirmed signature with `--prior-signatures`) keep their decisions; the
   batch learner and the calibration refit use all decisions so far.

## 9. Phase 5 (later): teams and agents

- LinkML `schema/linkml/xray_classify.yaml` → JSON Schema and SQL tables (`results`, `facet_values`, `alternatives`,
  `decisions`, `conflicts`), so several reviewers or an MCP agent can work in a database; `xray-classify export-sql` and
  `import-sql`.
- An agent skill (like `ifc-4d-schedule`) that runs `xray-classify`, summarises what needs a person, and drafts decisions for
  review (never accepted without a person).

## 10. Privacy and safety

- No user names in packages; reviewer names in decisions only with explicit opt-in, never in IFC unless the save's reviewer box
  is ticked (as today).
- Packages and decisions carry hashes of the files they refer to; applying to a different model is refused unless forced.
- Model downloads (transformers.js weights) go to Hugging Face or a configured mirror; nothing about the model is sent there.
- Jev/d3 requests carry the same compact element state as the viewer sends (classify.md, "What is sent to Jev").

## 11. Tests and acceptance

- Unit: the headless core gives the same results in Node and in the viewer for FZK-Haus with the `rules` provider
  (byte-identical facet values), package and decisions schema validation, merge and conflict rules, resume after interruption.
- CLI: `run` on FZK-Haus and the process plant with `rules` and the mock provider; `apply` round trip into IFC and read back;
  `--prior` skips confirmed items (call count drops to zero for a fully confirmed model).
- Viewer smoke: open a package, walk 5 items with keys, accept a signature, export decisions, apply and save IFC.
- Packed page smoke: open `review.html` from disk with no network requests, decide, export.
- Terminal: a scripted session through a pseudo-terminal (keys in, decisions file out).

## 12. Order of work (after the next release)

1. Headless core + batch mode + `xray-classify run` + `.xrc.json` (one or two agents).
2. `.xrd.json` + viewer review package support + `apply` (one agent).
3. Packed review page (small, reuses xray-pack).
4. Terminal review (small).
5. Phase 5 when a team workflow needs it.
