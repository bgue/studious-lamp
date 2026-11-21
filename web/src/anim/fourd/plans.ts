// The registry of named 4D plans: a `schedule4d` cue holds a plan inline or by name (`{ name }`), and the name is looked up here.
// The 4D loader of the viewer (or a smoke test) registers a plan once; every score that names it plays it. Pure.

import type { FourDPlan } from '../../schedule/types';

const plans = new Map<string, FourDPlan>();

export function registerPlan(name: string, plan: FourDPlan): void {
  plans.set(name, plan);
}

export function unregisterPlan(name: string): void {
  plans.delete(name);
}

export function getPlan(name: string): FourDPlan | null {
  return plans.get(name) ?? null;
}

export function planNames(): string[] {
  return [...plans.keys()];
}

export function clearPlans(): void {
  plans.clear();
}

/** The plan a cue refers to: the inline plan, or the registered one by name; null when the name is unknown. */
export function resolvePlan(ref: FourDPlan | { name: string }): FourDPlan | null {
  if ('schema' in ref) return ref;
  return getPlan(ref.name);
}
