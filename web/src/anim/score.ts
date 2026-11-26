// The score: the one timeline format that every animation compiles to and one player plays (camera, settings, visibility,
// selection, captions). The keyframe editor (fly-through timeline in the Views tab) compiles its keyframes into a score; the
// animation script language (src/anim/script) compiles a script into one. Recording, restore-after-play and the HUD work on
// scores, so they work the same for both.
//
// Contract between the fly-through work and the script work. Change it ADDITIVELY only (new optional fields, new cue kinds);
// a player that meets an unknown cue kind skips it.
//
// Times are seconds from the start of the score. A cue runs from `at` to `at + dur` (dur 0 = instant). Numbers blend over the
// cue with its ease; booleans, strings and enums switch at `switchAt` of the cue (default 'end' for a param cue, so a setting
// that the move leads to arrives with the camera). Element references are resolved when playback starts (a query runs once).

export const SCORE_SCHEMA = 'xray-score/1';

export type V3 = [number, number, number];

/** linear; in / out / inOut are cubic. */
export type Ease = 'linear' | 'in' | 'out' | 'inOut';

/** Where in a cue a discrete change (boolean, string, selection, hide without fade) happens. */
export type SwitchAt = 'start' | 'mid' | 'end';

/** Elements: by GlobalId, by a criteria query (src/query, e.g. `class = IfcPump and storey = "Level 2"`), by a stored
 *  selection set name, the selection at that moment, or everything. */
export type ElementRef =
  | { globalIds: string[] }
  | { query: string }
  | { set: string }
  | { selection: true }
  | { all: true }
  /** 4D (additive): elements in a state of the running `schedule4d` cue at this moment; resolved each time the cue runs, not at
   *  play start. Without a running schedule they are empty. */
  | { schedule: 'active' | 'completed' | 'critical' | 'future' };

export interface CameraPose {
  position: V3;
  target: V3;
  up?: V3;
  fovDeg?: number;
  /** The pseudo-orthographic view of the navigation code. */
  ortho?: boolean;
}

/** What a camera cue moves to. `frame` uses the fly-to framing (margin and closest distance) unless given. */
export type CameraTo =
  | { pose: CameraPose }
  | { frame: ElementRef; margin?: number; minDistance?: number }
  | { view: string }
  | { orbitDeg: number; about?: ElementRef };

/** The state a saved view holds (src/views/capture.ts captureView) as far as a score needs it; `params` is the saved view's
 *  params snapshot (x-ray, view modes, imaging, sightlines, display, cinematic, ...). Blended between two view cues: numbers
 *  in params blend, the rest switch at `switchAt`. */
export interface ViewState {
  camera: CameraPose;
  params?: Record<string, unknown>;
  presetId?: string | null;
  selection?: string[];
  /** Hidden elements (GlobalIds). With `isolate`, everything else is hidden. */
  hidden?: string[];
  isolate?: string[] | null;
  section?: unknown;
  explode?: unknown;
}

interface CueBase {
  at: number;
  dur: number;
  ease?: Ease;
  switchAt?: SwitchAt;
  /** Shown in the timeline and in errors: the keyframe name or the script line. */
  label?: string;
  /** Script line (1-based) the cue came from, for highlighting while it plays. */
  line?: number;
}

export type Cue =
  /** A smooth camera path through poses (the keyframe editor): centripetal Catmull-Rom, `times` are absolute seconds per pose
   *  (constant speed or per segment is decided by the compiler), pauses are repeated times. */
  | (CueBase & {
      kind: 'cameraPath';
      poses: CameraPose[];
      times: number[];
      /** Additive: per pose, false switches the ease off at that stop (a hold, the first or the last pose). Default: eases. */
      easeAt?: boolean[];
    })
  /** One camera move (scripts: fly to, orbit, view). */
  | (CueBase & { kind: 'camera'; to: CameraTo })
  /** One setting by its params path (the paths of docs/SETTINGS.md, e.g. `sightlines.alphaMax`, `cinematic.glowStrength`). */
  | (CueBase & { kind: 'param'; path: string; to: number | boolean | string | number[] })
  /** Apply a preset or a top-bar mode by id (switches at `switchAt`). */
  | (CueBase & { kind: 'preset'; id: string })
  /** A whole saved-view state (the keyframe editor): blends from the state before it to this one over the cue. */
  | (CueBase & { kind: 'view'; state: ViewState })
  /** Show, hide or isolate elements; with dur > 0 they fade (alpha) over the cue, else switch at `switchAt`. */
  | (CueBase & { kind: 'visibility'; show?: ElementRef; hide?: ElementRef; isolate?: ElementRef; showAll?: boolean })
  | (CueBase & { kind: 'select'; elements: ElementRef | null })
  | (CueBase & { kind: 'caption'; title?: string; text?: string })
  /** HUD labels pinned to elements (phase 2 draws them; a player without a HUD skips the cue). */
  | (CueBase & { kind: 'label'; elements: ElementRef; fields: string[] })
  | (CueBase & { kind: 'hover'; elements: ElementRef })
  // ---- 4D (additive; docs/design/4d-xer-animation.md, types in src/schedule/types.ts)
  /** Play a 4D plan over the cue: plan time maps to the cue through plan.timeMap (scaled to the cue's dur). Each frame the player
   *  sets every planned element's visibility, alpha (fades), tint (trade colour while active) and glow from its state at that
   *  plan time; the HUD reads the date and progress. `plan` inline, or by name from the 4D store. */
  | (CueBase & {
      kind: 'schedule4d';
      plan: import('../schedule/types').FourDPlan | { name: string };
      /** Additive (script statement `schedule "plan" view .. from .. to ..`): a view and a window (ISO dates) for the host to rebuild the
       *  plan with, when it can; a player that does not rebuild plays the plan as it is. */
      view?: 'planned' | 'actual' | 'variance';
      from?: string;
      to?: string;
      /** Additive: how long a newly built element fades in (and a removed one fades out), in seconds of the cue. Absent: the
       *  plan's style (`style.fadeIn`), else the default (10 % of the activity interval or 0.6 s, the shorter). 0 = at once. */
      fadeIn?: number;
    })
  /** Tint elements with a colour (#rrggbb), fading over the cue; null removes the tint. */
  | (CueBase & { kind: 'tint'; elements: ElementRef; colour: string | null })
  /** Explode by storey or radially (the cinematic explode), eased over the cue; factor default 1. */
  | (CueBase & { kind: 'explode'; mode: 'storeys' | 'radial'; factor?: number })
  | (CueBase & { kind: 'collapse' })
  /** The x-ray focus set: these elements (occluders in front of them ghost); null gives the focus back to the selection. */
  | (CueBase & { kind: 'focus'; elements: ElementRef | null })
  /** A section box around elements or a storey (margin in metres), or off (null), eased over the cue. */
  | (CueBase & { kind: 'sectionBox'; around: ElementRef | { storey: string } | null; margin?: number })
  /** Additive: show or hide the issue pins and the drawings (markup overlays) while the score plays. A player hides both when
   *  playback starts (unless PlayOptions.overlays says otherwise) and puts them back as they were when playback ends. */
  | (CueBase & { kind: 'overlays'; issues?: boolean; drawings?: boolean })
  /** Additive: the default fade for elements that appear or disappear from here on (show/hide without an explicit fade, schedule
   *  activities), in seconds. 0 = at once. */
  | (CueBase & { kind: 'fadeDefault'; seconds: number });

export type CueKind = Cue['kind'];

export interface Score {
  schema: typeof SCORE_SCHEMA;
  /** Seconds; at least the end of the last cue. */
  duration: number;
  cues: Cue[];
  /** Where it came from: the timeline editor or a script (with its text, for the line highlight). */
  source?: { kind: 'keyframes' | 'script'; name?: string; text?: string };
  /** Loop at the end (kiosk). */
  loop?: boolean;
}

export interface PlayOptions {
  /** Put the camera, selection, visibility and settings back as they were when playback ends or is stopped (default true). */
  restore?: boolean;
  /** Start at this time (seconds). */
  from?: number;
  onEnd?(): void;
  /** Called as cues start (for the line highlight and the timeline cursor). */
  onCue?(cue: Cue, index: number): void;
  /** Issue pins and drawings while playing; default both false (hidden). An `overlays` cue changes them during playback. */
  overlays?: { issues?: boolean; drawings?: boolean };
}

/** What the player offers; the fly-through work implements it (src/anim/player.ts) and registers it with `setScorePlayer`. */
export interface ScorePlayerApi {
  play(score: Score, opts?: PlayOptions): boolean;
  stop(): void;
  pause(): void;
  resume(): void;
  seek(t: number): void;
  readonly playing: boolean;
  readonly paused: boolean;
  /** Seconds into the score. */
  readonly time: number;
}

let player: ScorePlayerApi | null = null;
export function setScorePlayer(p: ScorePlayerApi | null): void {
  player = p;
}
export function getScorePlayer(): ScorePlayerApi | null {
  return player;
}

/** The end of the last cue (a score's minimum duration). */
export function scoreEnd(cues: readonly Cue[]): number {
  let end = 0;
  for (const c of cues) end = Math.max(end, c.at + Math.max(0, c.dur));
  return end;
}
