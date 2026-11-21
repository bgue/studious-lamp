// The frame schedule of a video export: a fixed step of 1 / fps, independent of the wall clock. Pure.

export const FPS_CHOICES = [24, 30, 60] as const;
export type Fps = (typeof FPS_CHOICES)[number];

/** Frames in a video of `duration` seconds at `fps`: duration * fps rounded, at least 1. */
export function frameCount(duration: number, fps: number): number {
  if (!(duration > 0) || !(fps > 0)) return 1;
  return Math.max(1, Math.round(duration * fps));
}

/** Score time of frame `index`, seconds. Frame 0 is the start; the last frame is one step before the end. */
export function frameTime(index: number, fps: number): number {
  return index / fps;
}

/** Every frame time (for tests and tools; the exporter computes them one by one). */
export function frameTimes(duration: number, fps: number): number[] {
  const n = frameCount(duration, fps);
  const out: number[] = [];
  for (let i = 0; i < n; i++) out.push(frameTime(i, fps));
  return out;
}

/** Milliseconds left, from the mean time of the frames done so far; null before the first frame. */
export function etaMs(done: number, total: number, elapsedMs: number): number | null {
  if (done <= 0 || elapsedMs <= 0) return null;
  return Math.max(0, ((total - done) * elapsedMs) / done);
}

/** "42 s", "3 min 05 s", "1 h 02 min". */
export function formatDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(s % 60).padStart(2, '0')} s`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}
