// Shared by the classify tests: the sidecar JSON of a shipped model as a SceneModel, and a stub fetch.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { normaliseRecord, normaliseRelations } from '../src/model/loader';
import type { SceneModel } from '../src/types';

const cache = new Map<string, SceneModel>();

/** The sidecar of public/models/<name>.json as a SceneModel (no geometry). A fresh copy: tests may write properties. */
export function sidecarModel(name: string): SceneModel {
  const text = readFileSync(fileURLToPath(new URL(`../public/models/${name}.json`, import.meta.url)), 'utf8');
  const j = JSON.parse(text) as Record<string, unknown>;
  const elements = (j['elements'] as Array<Record<string, unknown>>).map((r, i) => normaliseRecord(r as never, i));
  const m: SceneModel = {
    schema: 'xray-model/1',
    units: 'm',
    originShift: (j['originShift'] as [number, number, number]) ?? [0, 0, 0],
    storeys: (j['storeys'] as SceneModel['storeys']) ?? [],
    elements,
    relations: normaliseRelations(j['relations'] as never),
    byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])),
  };
  cache.set(name, m);
  return m;
}

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } });
}
