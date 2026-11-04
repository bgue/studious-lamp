// Node entry of the IFC reader, bundled by tools/pack/convert.mjs into tools/pack/reader.mjs (vite ssr build; web-ifc
// stays external). It runs the SAME extract (ifcRaw.ts) and build (ifcImport.ts) code as the browser, so pack-time and
// in-browser conversion cannot drift apart.
import { createIfcApi, extractIfc } from '../../src/model/ifcRaw';
import { buildModelData, isZip, unzipIfc } from '../../src/model/ifcImport';
import type { BuildReport, Sidecar } from '../../src/model/ifcImport';

export interface ConvertInput {
  name: string;
  bytes: Uint8Array;
}

export interface ConvertResult {
  glb: Uint8Array;
  sidecar: Sidecar;
  report: BuildReport;
  files: Array<{ fileName: string; schema: string; elements: number }>;
  extractMs: number;
  buildMs: number;
}

/** IFC / IFCZIP bytes -> glb + sidecar, files federated in the order given. `wasmPath` is web-ifc-node.wasm. */
export async function convertIfc(inputs: ConvertInput[], wasmPath: string): Promise<ConvertResult> {
  const t0 = performance.now();
  const api = await createIfcApi({ url: wasmPath });
  const raws = [];
  try {
    for (const inp of inputs) {
      let bytes = inp.bytes;
      let name = inp.name;
      if (isZip(bytes)) {
        const z = await unzipIfc(bytes);
        bytes = z.bytes;
        name = z.name.split('/').pop() ?? inp.name;
      }
      raws.push(await extractIfc(api, bytes, name));
    }
  } finally {
    try { api.Dispose(); } catch { /* ignore */ }
  }
  const t1 = performance.now();
  const data = buildModelData(raws);
  const t2 = performance.now();
  return {
    glb: new Uint8Array(data.glb),
    sidecar: data.sidecar,
    report: data.report,
    files: raws.map((r) => ({ fileName: r.fileName, schema: r.schema, elements: r.elements.length })),
    extractMs: t1 - t0,
    buildMs: t2 - t1,
  };
}
