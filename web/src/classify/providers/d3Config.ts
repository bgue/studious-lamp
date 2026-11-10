// Constants and plain checks of the d3 provider ("Decision 3.0 d3-edge"). No DOM, no imports of heavy modules: the settings use it.

/** The only browser export of d3-edge. It is third party (not from vllm-sr), 29 downloads when pinned, with no README. */
export const D3_REPO_DEFAULT = 'warsang/d3-edge-web';
/** Pinned commit of that repository. */
export const D3_REVISION_DEFAULT = '117fb255e630667ae1736666497e8a1c69c7a066';
export const D3_HF_ENDPOINT_DEFAULT = 'https://huggingface.co';
/** What `vllm-sr serve -e vllm-sr/d3-edge` exposes (model card of vllm-sr/d3-edge). */
export const D3_ENDPOINT_DEFAULT = 'http://localhost:8899/v1/systemone';
export const D3_MODEL_DEFAULT = 'vllm-sr/d3-edge';
/** The official (PyTorch) model that the endpoint serves, pinned. Apache-2.0. */
export const D3_OFFICIAL_REVISION = 'bee5e872f75b9c5d1405767bf244a6948b95c0af';

/** onnxruntime-web, exact version, from jsDelivr. The WebGPU build (it also holds the WASM backend). It is never bundled. */
export const ORT_VERSION = '1.30.0';
export const ORT_CDN_URL = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/ort.webgpu.min.mjs`;
export const ORT_WASM_BASE = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;

/** Cache API entry of the downloaded d3 files. */
export const D3_CACHE_NAME = 'xray-d3-cache';

export const D3_BACKENDS = ['browser', 'endpoint'] as const;
export type D3Backend = (typeof D3_BACKENDS)[number];
export const D3_DEVICES = ['auto', 'webgpu', 'wasm'] as const;
export type D3Device = (typeof D3_DEVICES)[number];

export const IMAGE_MODES = ['off', 'isolated', 'context', 'both'] as const;
export type ImageMode = (typeof IMAGE_MODES)[number];
/** `render` is shaded, `vector` is a simplified line drawing (silhouette and feature edges, black on white). */
export const IMAGE_STYLES = ['render', 'vector'] as const;
export type ImageStyle = (typeof IMAGE_STYLES)[number];
export const IMAGE_SIZE_MIN = 256;
export const IMAGE_SIZE_MAX = 512;
export const IMAGE_SIZE_DEFAULT = 384;
/** The vision encoder reads blocks of 32 pixels (patch 16, merge 2), so a size that is a multiple of 32 needs no resize. */
export const IMAGE_SIZE_STEP = 32;
/** Margin of the context box, in percent of the largest side of the element (and never under 0.5 m). */
export const IMAGE_MARGIN_MIN = 0;
export const IMAGE_MARGIN_MAX = 200;
export const IMAGE_MARGIN_DEFAULT = 25;
/** Settings values of the first picture design, and the new value that is nearest to each. */
export const IMAGE_MODE_MIGRATION: Readonly<Record<string, ImageMode>> = { element: 'isolated', 'element+neighbours': 'context' };
/** Native vector geometry (SVG markup) in the state text: independent of the pictures, works with any model that reads text. */
export const GEOMETRY_TEXT_MODES = ['off', 'svg'] as const;
export type GeometryText = (typeof GEOMETRY_TEXT_MODES)[number];
/** The d3 state is smaller by default than the Jev one: every token costs time on a small device. */
export const D3_STATE_BYTES_DEFAULT = 2000;

/** The files of the browser export, in the order they are read. The torso is by far the largest (1,043,107,948 bytes in the pinned revision). */
export const D3_FILES = {
  manifest: 'MANIFEST.json',
  config: 'decision_config.json',
  tokenizer: 'tokenizer.json',
  tokenizerConfig: 'tokenizer_config.json',
  readout: 'onnx/readout.onnx',
  torso: 'onnx/torso_fp16.onnx',
} as const;

/** A base URL instead of a Hugging Face repository id: the export folder served over http(s), for example http://localhost:8123/d3-mm. */
export const isBaseUrl = (id: string): boolean => /^https?:\/\//i.test(id.trim());

/** Problem with a Hugging Face repository id or a base URL, or null. */
export function d3RepoProblem(id: unknown): string | null {
  if (typeof id !== 'string' || !id.trim()) return 'The d3 repository id is empty. Write it as owner/name, for example warsang/d3-edge-web, or as the web address of a folder.';
  const t = id.trim();
  if (isBaseUrl(t)) {
    let u: URL;
    try {
      u = new URL(t);
    } catch {
      return `"${t}" is not a web address.`;
    }
    if (u.username || u.password) return 'The web address must not contain a user name or password.';
    if (u.search || u.hash) return 'The web address of the folder must have no query and no fragment.';
    return null;
  }
  if (t.length > 200 || !/^[A-Za-z0-9][A-Za-z0-9._-]*\/[A-Za-z0-9][A-Za-z0-9._-]*$/.test(t) || t.includes('..')) {
    return `"${t}" is not a repository id. Use owner/name with letters, digits, dots, dashes and underscores, for example warsang/d3-edge-web.`;
  }
  return null;
}

export const isCommitHash = (r: string): boolean => /^[0-9a-f]{40}$/.test(r);

/** Problem with a revision (a commit hash, a tag or a branch), or null. */
export function d3RevisionProblem(r: unknown): string | null {
  if (typeof r !== 'string' || !r.trim()) return 'The revision is empty. Use a commit hash of 40 characters.';
  const t = r.trim();
  if (t.length > 100 || !/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(t) || t.includes('..')) return `"${t}" is not a revision. Use a commit hash, a tag or a branch name.`;
  return null;
}
