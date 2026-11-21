// The camera director of the 4D film is written apart (src/schedule/director.ts, `directFourD(plan, model) -> Cue[]`). The schedule
// workflow must compile and run without it, so it is reached in two optional ways: a registry (`registerDirector`, for a plugin or a test)
// and a glob import that finds the file when it exists and gives nothing when it does not. No import of the file is written by name.

import type { Cue } from '../anim/score';
import type { FourDModel } from '../schedule/model';
import type { FourDPlan } from '../schedule/types';

export type DirectFn = (plan: FourDPlan, model: FourDModel) => Cue[];

let registered: DirectFn | null = null;
let probed: Promise<DirectFn | null> | null = null;

/** Make a director available (replaces the one found by the glob). Null removes it. */
export function registerDirector(fn: DirectFn | null): void {
  registered = fn;
}

// An empty object when src/schedule/director.ts does not exist; the file is then not part of the build.
const FOUND = import.meta.glob<{ directFourD?: DirectFn }>('../schedule/director.ts');

/** The director function, or null when there is none. Looks once. */
export function loadDirector(): Promise<DirectFn | null> {
  if (registered) return Promise.resolve(registered);
  probed ??= (async () => {
    const load = Object.values(FOUND)[0];
    if (!load) return null;
    try {
      const m = await load();
      return typeof m.directFourD === 'function' ? m.directFourD : null;
    } catch {
      return null;
    }
  })();
  return probed.then((fn) => registered ?? fn);
}

export const NO_DIRECTOR_NOTE = 'The camera director is not part of this build, so the film keeps the current camera.';

export interface DirectResult { cues: Cue[]; note: string }

/** Cues of the director for a plan. Without a director, or when it fails, no cues and a note that says why. */
export async function direct(plan: FourDPlan, model: FourDModel): Promise<DirectResult> {
  const fn = await loadDirector();
  if (!fn) return { cues: [], note: NO_DIRECTOR_NOTE };
  try {
    const cues = fn(plan, model);
    return { cues: Array.isArray(cues) ? cues : [], note: '' };
  } catch (e) {
    return { cues: [], note: `The camera director failed (${e instanceof Error ? e.message : String(e)}), so the film keeps the current camera.` };
  }
}
