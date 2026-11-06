// Pure helpers of tools/xray-pack.mjs: argument parsing, select-list parsing, boot document, template injection,
// base64. No file system access here, so vitest can exercise all of it (tests/pack-*.test.ts).

export const EXIT_OK = 0;
export const EXIT_USAGE = 1;
export const EXIT_INPUT = 2;

/** Error with the process exit code the CLI should use. The message is one line. */
export class PackError extends Error {
  constructor(message, code = EXIT_USAGE) {
    super(message);
    this.name = 'PackError';
    this.code = code;
  }
}

/** Tool ids reserved by src/tools/registry.ts. Other ids are accepted with a warning (a plugin may add its own). */
export const KNOWN_TOOLS = [
  'open', 'presets', 'xray', 'viewModes', 'imaging', 'section', 'measure', 'clearance', 'penetrations', 'bcf',
  'pointcloud', 'xr', 'cleanup', 'largeModel',
];

export const INJECT_BEGIN = '/* XRAY-PACK:INJECT-BEGIN */';
export const INJECT_END = '/* XRAY-PACK:INJECT-END */';

export const HELP = `xray-pack: wrap a model in a self-contained X-ray viewer (one .html file, no server, no network)

Usage:
  xray-pack <inputs...> -o <out.html> [options]

Inputs (one kind per run):
  a.ifc [b.ifc ...]     IFC or .ifczip files, federated into one model (same rules as the viewer)
  model.glb             one glb; model.json next to it (same basename) is used as the sidecar when present

Options:
  -o, --out <file>        output .html file (required)
  --params <file.json>    xray-params/1 document (partial allowed), e.g. from the viewer's Export / import folder
  --preset <name>         preset applied before the params (needs the presets plugin in the viewer)
  --select <list>         comma-separated GlobalIds and/or class:IfcDuctSegment entries, selected at start
  --title <text>          page title (default: the model name)
  --name <name>           model name (default: basename of the first input)
  --tools <ids>           comma-separated action-panel tool ids to show (default: all)
  --open-tool <id>        tool drawer to open at start
  --kiosk                 start with both side panels collapsed
  --camera px,py,pz:tx,ty,tz   camera position and target in the viewer frame (Y up, origin-shifted)
  --views <file.json>     saved views (xray-views/1, from the viewer's Views tab > Export) shown in the Views tab
  --open-view <name>      saved view (name, id or 1-based number) opened at start; needs --views
  --ifc-reader            also embed the in-browser IFC reader (adds about 1.2 MB)
  --samples               also embed the sample models (building, fzk-haus, plumbing)
  --force                 overwrite an existing output file
  --quiet                 print nothing except errors
  -h, --help              show this text

Exit codes: 0 ok, 1 usage error, 2 input error.
`;

const VALUE_OPTIONS = {
  '-o': 'out', '--out': 'out', '--params': 'params', '--preset': 'preset', '--select': 'select', '--title': 'title',
  '--name': 'name', '--tools': 'tools', '--open-tool': 'openTool', '--camera': 'camera', '--views': 'views',
  '--open-view': 'openView',
};
const FLAG_OPTIONS = {
  '--kiosk': 'kiosk', '--ifc-reader': 'ifcReader', '--samples': 'samples', '--force': 'force', '--quiet': 'quiet',
  '-h': 'help', '--help': 'help',
};

/** "a, b,,c" -> ['a','b','c'] (trimmed, empty entries dropped, duplicates removed in order). */
export function parseList(text) {
  const out = [];
  for (const part of String(text).split(',')) {
    const t = part.trim();
    if (t && !out.includes(t)) out.push(t);
  }
  return out;
}

/**
 * A select list: GlobalIds and `class:IfcX` entries. Returns { gids, classes, entries } where entries keeps the order.
 * Throws PackError on an empty list, an empty class name, or a class that does not start with Ifc.
 */
export function parseSelect(text) {
  const entries = parseList(text);
  if (entries.length === 0) throw new PackError('--select needs at least one GlobalId or class:IfcClass entry');
  const gids = [];
  const classes = [];
  for (const e of entries) {
    if (/^class:/i.test(e)) {
      const cls = e.slice(e.indexOf(':') + 1).trim();
      if (!/^Ifc[A-Za-z0-9]+$/i.test(cls)) throw new PackError(`--select: "${e}" is not class:IfcSomething`);
      classes.push(cls);
    } else {
      if (/\s/.test(e)) throw new PackError(`--select: "${e}" is not a GlobalId`);
      gids.push(e);
    }
  }
  return { gids, classes, entries };
}

/** "px,py,pz:tx,ty,tz" -> { position, target } (six finite numbers). */
export function parseCamera(text) {
  const m = String(text).split(':');
  const bad = () => new PackError(`--camera: expected px,py,pz:tx,ty,tz (six numbers), got "${text}"`);
  if (m.length !== 2) throw bad();
  const vec = (s) => {
    const parts = s.split(',').map((x) => x.trim());
    if (parts.length !== 3 || parts.some((x) => x === '' || !Number.isFinite(Number(x)))) throw bad();
    return parts.map(Number);
  };
  return { position: vec(m[0]), target: vec(m[1]) };
}

/**
 * Parse the command line (without node and script). Returns { help, inputs, options } where options has:
 * out, params, preset, select(string[]), title, name, tools(string[]), openTool, camera, views (file), openView, kiosk,
 * ifcReader, samples, force, quiet. Throws PackError (exit code 1) on any problem.
 */
export function parseArgs(argv) {
  const options = {
    out: undefined, params: undefined, preset: undefined, select: undefined, title: undefined, name: undefined,
    tools: undefined, openTool: undefined, camera: undefined, views: undefined, openView: undefined,
    kiosk: false, ifcReader: false, samples: false, force: false, quiet: false,
  };
  const inputs = [];
  let help = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    let flag = a;
    let inline;
    if (a.startsWith('--') && a.includes('=')) {
      flag = a.slice(0, a.indexOf('='));
      inline = a.slice(a.indexOf('=') + 1);
    }
    if (flag in FLAG_OPTIONS) {
      if (inline !== undefined) throw new PackError(`${flag} does not take a value`);
      if (FLAG_OPTIONS[flag] === 'help') help = true;
      else options[FLAG_OPTIONS[flag]] = true;
    } else if (flag in VALUE_OPTIONS) {
      let v = inline;
      if (v === undefined) {
        v = argv[++i];
        if (v === undefined || (v.startsWith('-') && v.length > 1 && !/^-?\d/.test(v))) throw new PackError(`${flag} needs a value`);
      }
      const key = VALUE_OPTIONS[flag];
      if (options[key] !== undefined) throw new PackError(`${flag} given twice`);
      options[key] = v;
    } else if (a.startsWith('-') && a.length > 1) {
      throw new PackError(`unknown option ${a} (see --help)`);
    } else {
      inputs.push(a);
    }
  }
  if (help) return { help: true, inputs, options };
  if (inputs.length === 0) throw new PackError('no input files (see --help)');
  if (!options.out) throw new PackError('missing -o <out.html>');
  if (!/\.html?$/i.test(options.out)) throw new PackError(`output "${options.out}" must end in .html`);

  const exts = inputs.map((f) => (/\.(ifczip|ifc|glb)$/i.exec(f)?.[1] ?? '').toLowerCase());
  const bad = inputs.find((_, i) => !exts[i]);
  if (bad) throw new PackError(`unsupported input "${bad}" (expected .ifc, .ifczip or .glb)`);
  const glbs = exts.filter((e) => e === 'glb').length;
  if (glbs > 0 && glbs !== inputs.length) throw new PackError('cannot mix .glb and .ifc inputs');
  if (glbs > 1) throw new PackError('only one .glb can be packed (glb files are not federated)');

  if (options.select !== undefined) options.select = parseSelect(options.select).entries;
  if (options.tools !== undefined) {
    options.tools = parseList(options.tools);
    if (options.tools.length === 0) throw new PackError('--tools needs at least one tool id');
  }
  if (options.openTool !== undefined) {
    if (!/^[A-Za-z][\w.-]*$/.test(options.openTool)) throw new PackError(`--open-tool: "${options.openTool}" is not a tool id`);
    if (options.tools && !options.tools.includes(options.openTool)) {
      throw new PackError(`--open-tool ${options.openTool} is not in --tools (${options.tools.join(',')})`);
    }
  }
  if (options.camera !== undefined) options.camera = parseCamera(options.camera);
  if (options.name !== undefined && options.name.trim() === '') throw new PackError('--name must not be empty');
  if (options.preset !== undefined && options.preset.trim() === '') throw new PackError('--preset must not be empty');
  if (options.openView !== undefined) {
    if (options.openView.trim() === '') throw new PackError('--open-view must not be empty');
    if (options.views === undefined) throw new PackError('--open-view needs --views <file.json>');
  }
  return { help: false, inputs, options };
}

/** Tool ids that are neither reserved nor plausible custom ids; used for a warning only. */
export function unknownTools(tools) {
  return (tools ?? []).filter((t) => !KNOWN_TOOLS.includes(t));
}

/** Default model name: the basename of the first input without its extension(s). */
export function defaultModelName(inputPath) {
  const base = String(inputPath).split(/[\\/]/).pop() ?? '';
  return base.replace(/\.(ifczip|ifc|glb)$/i, '') || 'model';
}

/**
 * Check a --views document (parsed JSON): an `xray-views/1` document, a bare list of views, or one shared view
 * (`xray-view/1`). Returns { views, warnings } with the usable views (each needs a name and a camera with position and
 * target; the viewer sanitises the rest); throws PackError(2) for a document that is not a views document, has no
 * usable view, or lacks the --open-view entry (matched like the viewer: id, name, name ignoring case, 1-based number).
 */
export function checkViews(doc, openView, modelName) {
  const isObj = (v) => !!v && typeof v === 'object' && !Array.isArray(v);
  let list;
  let docModel;
  if (Array.isArray(doc)) list = doc;
  else if (isObj(doc) && doc.schema === 'xray-view/1') {
    list = [doc.view];
    docModel = doc.model;
  } else if (isObj(doc) && (doc.schema === 'xray-views/1' || (doc.schema === undefined && Array.isArray(doc.views)))) {
    if (!Array.isArray(doc.views)) throw new PackError('--views: the document has no "views" list', EXIT_INPUT);
    list = doc.views;
    docModel = doc.model;
  } else {
    const schema = isObj(doc) ? doc.schema : undefined;
    throw new PackError(`--views: not a saved views document (schema ${schema ?? 'missing'}; expected xray-views/1)`, EXIT_INPUT);
  }
  const warnings = [];
  const vec = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === 'number' && Number.isFinite(x));
  const views = [];
  list.forEach((v, i) => {
    if (!isObj(v) || typeof v.name !== 'string' || !v.name.trim()) warnings.push(`view #${i + 1} has no name (skipped)`);
    else if (!isObj(v.camera) || !vec(v.camera.position) || !vec(v.camera.target)) warnings.push(`view "${v.name}" has no camera position and target (skipped)`);
    else views.push(v);
  });
  if (views.length === 0) throw new PackError('--views: the document has no usable view', EXIT_INPUT);
  if (typeof docModel === 'string' && modelName && docModel !== modelName) {
    warnings.push(`the views were saved on model "${docModel}", the page shows "${modelName}" (GlobalIds and cameras may not match)`);
  }
  if (openView !== undefined) {
    const key = openView.trim();
    const n = /^\d+$/.test(key) ? Number(key) - 1 : -1;
    const found = views.some((v) => v.id === openView || v.name === openView || v.name.toLowerCase() === key.toLowerCase()) || (n >= 0 && n < views.length);
    if (!found) throw new PackError(`--open-view "${openView}" is not in the views file (${views.map((v) => v.name).slice(0, 8).join(', ')})`, EXIT_INPUT);
  }
  return { views, warnings };
}

/**
 * The window.__xrayBoot object. `params` is the parsed --params document (or undefined), `views` the checked views
 * list (or undefined). Keys that were not requested are left out, so a plain pack gives { model } only.
 */
export function buildBoot(model, options = {}, params, views) {
  const boot = { model };
  if (options.title) boot.title = options.title;
  if (params !== undefined) boot.params = params;
  if (options.preset) boot.preset = options.preset;
  if (options.camera) boot.camera = options.camera;
  if (options.select && options.select.length) boot.select = options.select;
  if (options.tools) boot.tools = options.tools;
  if (options.openTool) boot.openTool = options.openTool;
  if (options.kiosk) boot.kiosk = true;
  if (views !== undefined) boot.views = { schema: 'xray-views/1', model, views };
  if (options.openView && views !== undefined) boot.openView = options.openView;
  return boot;
}

export function toBase64(bytes) {
  return Buffer.from(bytes.buffer ? new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength) : bytes).toString('base64');
}

export function fromBase64(text) {
  return new Uint8Array(Buffer.from(text, 'base64'));
}

/** Make text safe inside an inline <script>: no closing tag or comment opener can end the element early. */
export function scriptSafe(s) {
  return s
    .replace(/<\/(script)/gi, '<\\/$1')
    .replace(/<!--/g, '<\\!--')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

export function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * The text that goes between the INJECT markers: embedded models and the boot object.
 * models: { name: { glb: base64 string, json: sidecar object | undefined } }
 */
export function injectionScript(models, boot) {
  return scriptSafe(`\nwindow.__xrayEmbeddedModels = ${JSON.stringify(models)};\nwindow.__xrayBoot = ${JSON.stringify(boot)};\n`);
}

/** Fill a template page (from build-single-file.mjs --template). Throws PackError(2) when the markers are missing. */
export function injectTemplate(html, { models, boot, title }) {
  const b = html.indexOf(INJECT_BEGIN);
  const e = html.indexOf(INJECT_END);
  if (b < 0 || e < b) throw new PackError('the template has no injection markers (rebuild it: node tools/build-single-file.mjs --template)', EXIT_INPUT);
  let out = html.slice(0, b + INJECT_BEGIN.length) + injectionScript(models, boot) + html.slice(e);
  const titled = out.replace(/<title>[^<]*<\/title>/, () => `<title>${escapeHtml(title)}</title>`);
  if (titled === out) throw new PackError('the template has no <title>', EXIT_INPUT);
  out = titled;
  return out;
}
