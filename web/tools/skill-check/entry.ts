// Bundle entry of the ifc-4d-schedule skill's script checker (skills/ifc-4d-schedule/scripts/xrayanim_check.mjs):
// the viewer's own animation-script compiler, run from the command line with plain node. Rebuild with
//   node tools/skill-check/build.mjs
import { compileScript } from '../../src/anim/script/compiler';
import type { FourDPlan } from '../../src/schedule/types';

export function check(text: string, plans: Record<string, FourDPlan> = {}, extra: { params?: Record<string, string>; library?(name: string): string | null; libraryNames?(): string[] } = {}): unknown {
  const r = compileScript(text, { plans: (name: string) => plans[name] ?? null, ...extra } as never);
  return {
    ok: r.errors.filter((e) => (e as { severity?: string }).severity !== 'warning').length === 0,
    errors: r.errors.map((e) => ({ line: e.line, col: (e as { col?: number }).col, message: e.message, hint: (e as { hint?: string }).hint, severity: (e as { severity?: string }).severity ?? 'error' })),
    params: r.params.map((p) => ({ name: p.name, kind: p.kind, default: p.default, value: p.value })),
    cues: r.score?.cues.length ?? 0,
    duration: r.score?.duration ?? 0,
    kinds: r.score ? [...new Set(r.score.cues.map((c) => c.kind))] : [],
  };
}
