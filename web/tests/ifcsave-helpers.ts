// Shared by the ifcsave tests: fixtures, synthetic results and a plan builder.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { IfcAPI } from 'web-ifc';
import { defaultSchema } from '../src/classify/schema';
import type { ClassificationSchema, ClassifyResult } from '../src/classify/types';
import { scanStep } from '../src/ifcsave/stepScan';
import type { IfcSourceInfo } from '../src/ifcsave/plan';

const here = dirname(fileURLToPath(import.meta.url));
export const web = resolve(here, '..');
export const wasmPath = resolve(web, 'node_modules/web-ifc/web-ifc-node.wasm');
export const fxIfc = (n: string): string => resolve(here, 'fixtures/ifc', n);
export const modelIfc = (n: string): string => resolve(web, '..', 'models', n);

export interface Case {
  name: string;
  path: string;
  schema: string;
}
export const CASES: Case[] = [
  { name: 'AC20-FZK-Haus.ifc', path: modelIfc('AC20-FZK-Haus.ifc'), schema: 'IFC4' },
  { name: 'ports-ifc2x3.ifc', path: fxIfc('ports-ifc2x3.ifc'), schema: 'IFC2X3' },
  { name: 'mini-ifc4x3.ifc', path: fxIfc('mini-ifc4x3.ifc'), schema: 'IFC4X3_ADD2' },
  { name: 'Process-Plant.ifc', path: modelIfc('Process-Plant.ifc'), schema: 'IFC4' },
].filter((c) => existsSync(c.path));

export const bytesOf = async (b: Blob): Promise<Uint8Array> => new Uint8Array(await b.arrayBuffer());
export const latin1 = (b: Uint8Array): string => new TextDecoder('latin1').decode(b);
export const textOf = async (b: Blob): Promise<string> => latin1(await bytesOf(b));
export const sameBytes = (a: Uint8Array, b: Uint8Array): boolean => a.length === b.length && a.every((x, i) => x === b[i]);
export const fileBytes = (path: string): Uint8Array => new Uint8Array(readFileSync(path));
export const blobOf = (path: string): Blob => new Blob([new Uint8Array(readFileSync(path))]);

export async function sourceInfo(name: string, blob: Blob): Promise<IfcSourceInfo> {
  const s = await scanStep(blob);
  return { fileName: name, schema: s.schema, maxExpressId: s.maxExpressId, ownerHistoryId: s.ownerHistoryId, classifications: s.classifications, blockBase: s.block?.base ?? null };
}

export interface ElementLine {
  expressId: number;
  globalId: string;
}
/** All IfcElement lines of a model opened in web-ifc. */
export function elementsOf(api: IfcAPI, modelId: number): ElementLine[] {
  const all = api.GetAllLines(modelId);
  const out: ElementLine[] = [];
  for (let i = 0; i < all.size(); i++) {
    const id = all.get(i);
    if (!api.IsIfcElement(api.GetLineType(modelId, id))) continue;
    const l = api.GetLine(modelId, id);
    const g = l?.GlobalId?.value;
    if (typeof g === 'string') out.push({ expressId: id, globalId: g });
  }
  return out.sort((a, b) => a.expressId - b.expressId);
}

export const SCHEMA: ClassificationSchema = defaultSchema();

/** A result that varies with the index so groups of different sizes appear. */
export function syntheticResult(globalId: string, i: number, schema: ClassificationSchema = SCHEMA): ClassifyResult {
  const d = schema.disciplines[i % schema.disciplines.length]!;
  const sub = d.subDisciplines.length && i % 2 === 0 ? d.subDisciplines[i % d.subDisciplines.length]! : null;
  const div = schema.masterformat.divisions[i % schema.masterformat.divisions.length]!;
  const reviewed = i % 5 === 0;
  return {
    id: globalId,
    discipline: { code: d.code, label: d.label, confidence: 0.9 - (i % 3) * 0.1, probabilities: {} },
    subDiscipline: sub ? { code: sub.code, label: sub.label, confidence: 0.8, probabilities: {} } : null,
    masterformat: { division: div.division, title: div.title, confidence: 0.85, probabilities: {}, ...(i % 7 === 0 ? { section: `${div.division} 31 13` } : {}) },
    buildingElement: 0.97,
    source: reviewed ? 'confirmed' : i % 4 === 1 ? 'model' : 'rules',
    ...(i % 4 === 1 ? { model: 'test-model-1' } : {}),
    needsReview: i % 3 === 0,
    ...(i % 4 !== 1 && !reviewed ? { rationale: 'class IfcWall; name has "Brick" ä中' } : {}),
    ...(reviewed ? { confirmedBy: 'Alice Reviewer', confirmedAt: '2026-03-04T10:11:12.345Z', commitId: `c${i}` } : {}),
  };
}
