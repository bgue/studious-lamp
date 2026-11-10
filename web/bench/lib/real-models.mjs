// The models of the real classification benches as SceneModels, for Node: the sidecars of public/models and the IFC files of ../models
// read with web-ifc (the same reader as the browser, run in Node). Pass a vite SSR server.
import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
export const SIDECARS = ['fzk-haus', 'synth5k', 'building', 'plumbing', 'debris-demo'];
export const IFC_FILES = ['AC20-FZK-Haus', 'Building-Architecture', 'Building-Hvac', 'Building-Structural', 'Infra-Electrical', 'Infra-Plumbing'];

export async function loadModels(server, names = [...SIDECARS, ...IFC_FILES]) {
  const H = await server.ssrLoadModule('/tests/classify-helpers.ts');
  const L = await server.ssrLoadModule('/src/model/loader.ts');
  const out = [];
  let api = null;
  for (const name of names) {
    if (SIDECARS.includes(name)) { out.push({ name, model: H.sidecarModel(name) }); continue; }
    const file = resolve(root, '..', 'models', `${name}.ifc`);
    if (!existsSync(file)) continue;
    const Raw = await server.ssrLoadModule('/src/model/ifcRaw.ts');
    const Imp = await server.ssrLoadModule('/src/model/ifcImport.ts');
    api ??= await Raw.createIfcApi({ url: resolve(root, 'node_modules/web-ifc/web-ifc-node.wasm') });
    const raw = await Raw.extractIfc(api, new Uint8Array(readFileSync(file)), `${name}.ifc`);
    const { sidecar } = Imp.buildModelData([raw]);
    const elements = sidecar.elements.map((r, i) => L.normaliseRecord(r, i));
    out.push({
      name,
      model: { schema: 'xray-model/1', units: 'm', originShift: sidecar.originShift ?? [0, 0, 0], storeys: sidecar.storeys ?? [], elements, relations: L.normaliseRelations(sidecar.relations), byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])) },
    });
  }
  return out;
}
