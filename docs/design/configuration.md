# Configuration: one namespace, JSON or YAML, load and save, reproducible

Status: spec, 2026-11-26. To be implemented with the offline classification work (after the next release), because distributed
checking needs both. Related: `docs/design/classification-offline.md`, `docs/design/classification-facets.md`,
`docs/design/concrete-classification.md`, `web/docs-features/4d-schedule.md`, `docs/SETTINGS.md`.

## 1. Why

Settings live in many places today: the served `xray.config.json` (`xray-config/1`: class styles, material aliases), the params
document (Export / import, sections listed in `docs/SETTINGS.md`), the classification schema (`xray-classification-schema/1`),
the 4D configuration (`xray-4d-config/1`, `.4d.json`), cleanup rules (`xray-cleanup/1`), presets, the keymap
(`xray-keymap/1`), views and fly-throughs, the classifier's provider settings (browser storage), the concrete cover table and the
UniFormat mapping (JSON files next to the schema). For distributed checking, several machines and reviewers must run with
exactly the same settings and prove it. So: one configuration format with named sections, loadable and savable as a whole or in
part, in JSON or YAML, layered, validated, hashed.

## 2. The file

Format id **`xray-config/2`**. File names: `*.xray.yaml`, `*.xray.yml`, `*.xray.json` (any name works with an explicit
`--config` or "Load configuration"). YAML 1.2 and JSON carry the same data; JSON is the canonical form for hashing.

```yaml
schema: xray-config/2
meta:
  name: Process plant checks, phase 2
  version: 3
  description: Classifier, facets and 4D settings for the phase-2 review round
extends:
  - ../org/base.xray.yaml          # relative to this file; https URLs only in the viewer and only same-origin
classify:
  schema: { ref: ./classification-schema.json, sha256: 9f2c... }
  provider: decision
  models:
    decision: { id: MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33, revision: 3c1a2b0 }   # HF commit pin
    embed:    { id: onnx-community/embeddinggemma-300m-ONNX, revision: 77e0f1d }
    jev:      { id: jev-1.13.0, endpoint: https://jev.example.org/v1, auth: { env: XRAY_JEV_KEY } }
    d3:       { id: vllm-sr/d3-edge, endpoint: http://localhost:8899/v1/systemone }
  hfEndpoint: https://huggingface.co
  calibration: { mode: manual, temperatures: { discipline: 1.4, trade: 1.1 } }
  rulesMode: final
  minConfidence: 0.6
  writePset: true
  facets:
    Trade:       { on: true,  reviewBelow: 0.7 }
    Placement:   { on: true,  reviewBelow: 0.7 }
    Material:    { on: true }
    Phase:       { on: true }
    Orientation: { on: true }
    ClassRepair: { on: true, suggestOnly: true }
  batch: { batchSize: 32, workers: 4, maxCalls: 5000, learn: { on: true, agreeAbove: 0.9 } }
  seed: 1
concrete:
  standard: EN206
  coverTable: { ref: ./concrete-cover.json }
  ratioEstimates: { SUSPENDED_SLAB: 110, BEAM: 175, COLUMN: 210 }
review:
  order: uncertainty
  acceptSignature: true
  reviewerNames: false            # decisions carry no reviewer name unless true (still opt-in per session)
ifcSave:
  includeFacets: true
  includeFourD: false
  includeCleanupMarks: true
fourd:
  config: { ref: ./plant.4d.json }  # or inline: the xray-4d-config/1 content
cleanup:
  rules: { ref: ./cleanup.json }    # xray-cleanup/1
viewer:
  classStyles: { Steel: { alphaMax: 0.8 } }       # what xray-config/1 held
  materialAliases: { Steel: [IfcMember, IfcPlate] }
  params: { ref: ./look.params.json }             # the params document, any of its sections
  presets: { ref: ./presets.json }
  keymap: { ref: ./keys.json }                    # xray-keymap/1
```

### 2.1 Sections

| Section | Holds | Today in |
| --- | --- | --- |
| `meta` | name, version, description (no personal names or e-mail) | new |
| `extends` | parent files, applied first | new |
| `classify` | schema reference, provider, model ids with pinned revisions, endpoints, calibration, rules mode, thresholds, facets on/off and review thresholds, batch, seed | classifier settings in browser storage, schema file |
| `concrete` | standard, cover table, ratio estimates, strength parsing preferences | concrete design tables |
| `review` | queue order, signature accept, reviewer-name default | review walk settings |
| `ifcSave` | defaults of the save dialog boxes (never `includeReviewers`: that stays a per-save choice) | save dialog |
| `fourd` | the 4D configuration (inline or reference) | `.4d.json` (`xray-4d-config/1`) |
| `cleanup` | cleanup rules | `xray-cleanup/1` |
| `viewer` | class styles, material aliases, the params document (sections of `docs/SETTINGS.md`), presets, keymap | `xray-config/1`, params export, presets file, keymap export |

Every section has its own JSON Schema; unknown sections are kept on save and reported as warnings (a newer tool may know them);
unknown keys inside a known section are errors with their path (`classify.facets.Trde: unknown facet, did you mean Trade?`).

### 2.2 References

`{ ref: <path>, sha256?: <hex> }` stands for the content of another file, resolved relative to the file that names it. With
`sha256`, loading fails if the file differs (pinning). The viewer resolves refs only to files the user picks together (a folder
or several files) or same-origin URLs; the CLI resolves any local path. A saved configuration can **inline** all refs
(`--inline` / "Save as one file") so a single file travels.

### 2.3 Secrets

Configurations never contain keys, tokens or passwords. `auth: { env: NAME }` names an environment variable for the CLI; in the
viewer, `auth` is ignored and the key comes from the existing key store (as today). Saving a configuration never writes a key;
loading one with a literal key-like value (`key`, `token`, `password`, `secret` fields) refuses it with a message.

## 3. Layering and precedence

From lowest to highest:

1. Built-in defaults of each section.
2. `extends` parents, in order (each parent's own `extends` first).
3. The file itself.
4. Command-line flags (`--provider jev`) or, in the viewer, changes made after loading.

Merging: objects merge deeply; arrays and scalars replace; `null` removes a key (falls back to the layer below). The **resolved**
configuration is what runs and what is hashed.

## 4. Reproducibility and distributed checking

- **Config hash**: sha256 of the canonical JSON of the resolved configuration (keys sorted, refs inlined, `meta` excluded,
  environment-only values like `auth` excluded). Every output records it: review packages (`.xrc.json` header `config`),
  decisions files, the IFC save block comment, 4D plans, storyboard title blocks, `xray-classify inspect`.
- **Model pins**: `revision` (a Hugging Face commit) for in-browser and Node models; the tools fetch that revision and refuse a
  different one when `--strict` (default in CI), warn otherwise.
- **Check profile**: a configuration plus its pinned refs is a check profile. Two runs with the same profile hash, the same model
  file hash and the same prior decisions give identical results (offline spec, section 3, determinism).
- Mismatch handling: applying decisions or merging packages made with different config hashes warns and lists the differing
  keys (`xray-config diff a b`).

## 5. In the viewer

- **Settings → Configuration**: **Load configuration…** (file picker or drop; several files or a folder to resolve refs),
  **Save configuration…** (choose sections; "as one file" inlines refs; JSON or YAML), **Reset to defaults**, and a status line:
  the loaded name, version, hash (short), and "modified" when anything changed since loading.
- Loading applies every section the viewer knows (classifier, facets, concrete, review, save defaults, 4D, cleanup, viewer
  look) and lists what it skipped.
- A packed page (`xray-pack --config`) embeds the resolved configuration; share links never carry it (they stay small and carry
  no settings beyond the view, as today).
- Browser storage keeps the last loaded configuration per viewer for convenience; it is not the source of truth.

## 6. Command line

- `--config <file>` on `xray-classify`, `xray-4d`, `xray-pack`, and the skill's scripts (the skill's `map.4d.json` stays valid:
  a bare `xray-4d-config/1` file is read as the `fourd` section).
- `xray-config validate <file>`: errors and warnings with paths, exit 1 on errors.
- `xray-config resolve <file> [--inline] [--format json|yaml] [-o out]`: the effective configuration.
- `xray-config hash <file>`: the config hash.
- `xray-config diff <a> <b>`: differing keys after resolving.
- `xray-config migrate <old files...> -o project.xray.yaml`: wraps old files into one (`xray-config/1`, `xray-4d-config/1`,
  `xray-cleanup/1`, `xray-keymap/1`, a params export, a classification schema) as sections or refs.

## 7. Compatibility

- `xray-config/1` (the served `xray.config.json`) keeps working: read as `viewer.classStyles` and `viewer.materialAliases`.
- Every existing standalone format keeps its id and can still be loaded alone; inside a v2 file it is a section's content.
- Readers accept JSON and YAML everywhere a configuration is read (the 4D CLI's "YAML is not supported" note goes away). YAML
  parsing uses the `yaml` package (pinned exact version; loaded lazily in the viewer, bundled in the CLI); YAML anchors and
  merge keys are allowed, custom tags are rejected.

## 8. Implementation notes

- A `web/src/config/` module: section registry (each feature registers its section: name, JSON Schema, defaults, apply, collect),
  resolver (extends, refs, merge, null removal), canonical JSON and hash, YAML/JSON read/write, secret guard, migrator.
- Schemas: LinkML source `schema/linkml/xray_config.yaml` generating JSON Schema (like the 4D schema), or TypeScript-first with
  a generated schema; one of the two, chosen at implementation.
- Each existing feature gets a small adapter (collect current settings into its section; apply a section) rather than a rewrite.

## 9. Tests and acceptance

- Resolver: extends chains, refs with sha256 pins, merge and `null`, cycles refused.
- Canonical hash stable across JSON and YAML forms of the same configuration and across key order.
- Secret guard: a key-like literal is refused; saving never writes keys.
- Round trip: viewer load → save → load gives the same hash; CLI `resolve` of the viewer's saved file gives the same hash.
- Migration: `xray-config/1`, `.4d.json`, cleanup and keymap files wrap and resolve to the same behaviour.
- Distributed: two `xray-classify run` processes with the same profile on FZK-Haus write identical packages (same config hash,
  same results).

## 10. Order of work (after the next release, with the offline classification)

1. `web/src/config/` core (resolver, YAML/JSON, hash, secret guard) and `xray-config validate|resolve|hash|diff`.
2. Section adapters: classify (incl. facets, models, batch), concrete, review, ifcSave; then fourd, cleanup, viewer.
3. Viewer Load/Save configuration UI and packed-page embedding.
4. `--config` on the CLIs and config hashes in every output; `migrate`.
