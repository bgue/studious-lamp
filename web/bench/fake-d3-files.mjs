// A FAKE export of d3-edge-web for the local smoke test: tiny text files with a correct manifest (size and sha256 of every file), so that
// the real loader (inspect, download, Cache API, integrity check) runs end to end against bench/fake-ort.mjs and the fake tokenizer.
// The torso is padded to `torsoBytes` so that the drawer shows a size. Plain JavaScript; Node only (it uses node:crypto).
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(readFileSync(resolve(here, '..', 'tests', 'fixtures', 'd3-decision-config-codes.json'), 'utf8'));
const enc = (s) => new TextEncoder().encode(s);
const sha = (b) => createHash('sha256').update(b).digest('hex');

export function makeFakeD3Export({ torsoBytes = 6_000_000, vision = false } = {}) {
  const torso = new Uint8Array(torsoBytes);
  torso.set(enc(vision ? 'TORSOMM fake multimodal torso graph' : 'TORSO fake torso graph'));
  const files = {
    'tokenizer.json': enc('{"fake":"tokenizer"}'),
    'tokenizer_config.json': enc('{"fake":"config"}'),
    'onnx/readout.onnx': enc('READOUT fake readout graph'),
    [vision ? 'onnx/torso_mm.onnx' : 'onnx/torso_fp16.onnx']: torso,
    ...(vision ? { 'onnx/vision_encoder.onnx': enc('VISION fake vision graph') } : {}),
    'decision_config.json': enc(JSON.stringify({ format_id: config.format_id, codes: config.codes })),
  };
  const manifest = {
    model: 'd3-edge-web', scope: vision ? 'text and images' : 'text-only v1; images/videos are not part of the browser export yet',
    graphs: vision
      ? { torso: 'onnx/torso_mm.onnx (fake)', vision: 'onnx/vision_encoder.onnx (fake)', readout: 'onnx/readout.onnx (fake)' }
      : { torso: 'onnx/torso_fp16.onnx', readout: 'onnx/readout.onnx' },
    ...(vision ? { mm: { image_token_id: 248056, patch_size: 16, merge_size: 2, pos_grid: 48 } } : {}),
    files: Object.fromEntries(Object.entries(files).map(([k, v]) => [k, { bytes: v.byteLength, sha256: sha(v) }])),
  };
  files['MANIFEST.json'] = enc(JSON.stringify(manifest));
  return { files, manifest };
}
