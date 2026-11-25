// The 4D film as an editable animation script ("Open as script" of the film bar). Pure: the plan, what the camera director made of it
// and the plan's name go in, the script text comes out. The same call the CLI makes (`xray-4d script`, tools/xray-4d/script.mjs):
// `scriptFromPlan` with a header; without a director the script holds the plan's `schedule` statement and a note line.

import type { Cue } from '../anim/score';
import { scriptFromPlan } from '../schedule/directorScript';
import type { FourDPlan } from '../schedule/types';

export interface FilmDirected {
  cues: Cue[];
  notes: string[];
  noteTimes: number[];
}

/** The name of the plan and of the script: the schedule's project name, then its short name, then the file name. */
export function filmName(projectName: string | undefined, shortName: string | undefined, fileName = ''): string {
  const raw = projectName || shortName || fileName.replace(/\.[^.]+$/, '') || '4D film';
  return raw.replace(/\s+/g, ' ').trim().slice(0, 60) || '4D film';
}

/**
 * The script text for a plan. `directed` is the director's result, or null when the camera stays put; `why` then says why
 * (no director in this build, the style asks for no director, or the director failed).
 */
export function filmScript(plan: FourDPlan, name: string, directed: FilmDirected | null, why = ''): { text: string; lines: number } {
  const header = [`made from the 4D film of ${name}; edit freely. Press Run to play it.`];
  if (directed) header.push('The notes before each block say why the camera does it.');
  else header.push(`The camera stays put${why ? `: ${why}` : '.'}`);
  const text = scriptFromPlan(plan, directed ?? { cues: [], notes: [], noteTimes: [] }, { planName: name, header });
  return { text, lines: text.replace(/\n+$/, '').split('\n').length };
}
