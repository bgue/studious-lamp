// The schedule that plays right now, for the HUD: label fields `activity`, `percent` and `finish` read the activity an element is
// in at the current plan time. The viewer host sets it while a schedule4d cue runs and clears it at the end.

export interface LiveSchedule {
  taskInfo(modelId: number): { code: string; name: string; percent: number; finish: number } | null;
}

let live: LiveSchedule | null = null;
export function setLiveSchedule(s: LiveSchedule | null): void {
  live = s;
}
export function getLiveSchedule(): LiveSchedule | null {
  return live;
}
