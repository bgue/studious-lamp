// The 4D tab's director hook finds the real director (src/schedule/director.ts) and returns its moves for the FZK sample plan.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { direct, registerDirector } from '../src/map4d/directorHook';
import { parseXer } from '../src/schedule/xer';
import { fromSidecar } from '../src/schedule/model';
import { linkSchedule } from '../src/schedule/link';
import { buildPlan } from '../src/schedule/plan';
import type { FourDConfig } from '../src/schedule/types';

const f = (p: string): string => fileURLToPath(new URL(p, import.meta.url));
const schedule = parseXer(readFileSync(f('../public/samples/fzk-haus.xer')));
const config = JSON.parse(readFileSync(f('../public/samples/fzk-haus.4d.json'), 'utf8')) as FourDConfig;
const model = fromSidecar(JSON.parse(readFileSync(f('../public/models/fzk-haus.json'), 'utf8')), { identityKey: 'fzk' });
const plan = buildPlan(schedule, linkSchedule(schedule, model, config, []), model, config.style);

describe('4D tab director hook', () => {
  it('uses the real director: camera, section box and beat cues, with a note', async () => {
    registerDirector(null);
    const r = await direct(plan, model);
    const kinds = new Set(r.cues.map((c) => c.kind));
    expect(r.cues.length).toBeGreaterThan(10);
    expect(kinds.has('camera')).toBe(true);
    expect(kinds.has('explode')).toBe(true);
    expect(r.note).toMatch(/camera director made \d+ moves/);
    expect(r.notes?.length).toBeGreaterThan(5);
  });
  it('still accepts a registered director that returns a bare cue list', async () => {
    registerDirector(() => [{ kind: 'collapse', at: 1, dur: 1 }]);
    expect((await direct(plan, model)).cues).toHaveLength(1);
    registerDirector(null);
  });
});
