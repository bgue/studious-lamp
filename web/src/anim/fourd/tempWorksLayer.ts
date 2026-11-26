// The temporary works layer of the 4D film: scaffold, falsework and formwork as instanced boxes (one InstancedMesh per kind), drawn beside the
// IFC model, not part of it. Each piece has an alpha from its group's progress (src/schedule/tempworks.ts) and follows the explode offset of
// the storey it serves. The meshes are not raycast by the viewer's picking (that runs on the model's BVH), so they never block a pick.
// A few thousand pieces are three draw calls and a per-group alpha rewrite when the progress changes.

import { BoxGeometry, Color, Group, InstancedBufferAttribute, InstancedMesh, Matrix4, Raycaster, ShaderMaterial, Vector2, DynamicDrawUsage, DoubleSide } from 'three';
import type { ViewerApp } from '../../app';
import { fromSceneModel } from '../../schedule/model';
import type { SceneLike } from '../../schedule/model';
import { TEMP_COLOURS, TEMP_OPACITY, fadeShare, generatePieces, groupPhase, groupProgress, pieceAlpha } from '../../schedule/tempworks';
import type { TempPieces } from '../../schedule/tempworks';
import type { FourDPlan, TempWorksGroup, TempWorksKind } from '../../schedule/types';

const VERT = `
attribute float aAlpha;
attribute vec3 aOff;
varying float vA;
varying vec3 vN;
void main() {
  vA = aAlpha;
  vN = normalize(mat3(modelMatrix) * mat3(instanceMatrix) * normal);
  vec4 p = modelMatrix * instanceMatrix * vec4(position, 1.0);
  p.xyz += aOff;
  gl_Position = projectionMatrix * viewMatrix * p;
}`;
const FRAG = `
uniform vec3 uColor;
uniform float uOpacity;
varying float vA;
varying vec3 vN;
void main() {
  float a = vA * uOpacity;
  if (a < 0.01) discard;
  float l = 0.62 + 0.38 * abs(dot(normalize(vN), normalize(vec3(0.4, 0.8, 0.45))));
  gl_FragColor = vec4(uColor * l, a);
}`;

const KINDS: readonly TempWorksKind[] = ['scaffold', 'falsework', 'formwork'];

export interface TempWorksGroupState { id: string; kind: TempWorksKind; label: string; phase: string; progress: number; pieces: number; visible: number }

/** What the film runner drives: plan time in, pictures out. */
export interface TempWorksTarget {
  update(planMs: number): void;
  reset(): void;
}

interface Built {
  plan: FourDPlan;
  groups: TempWorksGroup[];
  pieces: TempPieces;
  /** Mesh and first instance of each group. */
  place: Array<{ mesh: InstancedMesh; base: number }>;
  alpha: Float32Array[];
  off: Float32Array[];
  lastP: Float64Array;
  /** Model element id of the first served element, for the explode offset (-1: none). */
  anchor: Int32Array;
}

export class TempWorksLayer {
  readonly group = new Group();
  private built: Built | null = null;
  private attached = false;
  private on = true;
  private offVersion = -1;
  private planMs = NaN;
  private readonly cache = new WeakMap<FourDPlan, Built>();

  constructor(private readonly app: Pick<ViewerApp, 'renderer' | 'controller'>) {
    this.group.name = 'temporary-works';
  }

  get visible(): boolean { return this.on; }

  /** The layer's own toggle: hides every piece without touching the plan. */
  setVisible(v: boolean): void {
    this.on = v;
    this.group.visible = v;
    this.app.renderer.markDirty();
  }

  /** The pieces of a plan (built once per plan); a plan without temporary works gives null. */
  prepare(plan: FourDPlan): Built | null {
    const groups = plan.temporaryWorks?.groups ?? [];
    if (!groups.length) return null;
    let b = this.cache.get(plan);
    if (!b) { b = this.build(plan, groups); this.cache.set(plan, b); }
    return b;
  }

  /** Make the layer show `plan` (the film starts); returns the target the runner drives, or null without temporary works. */
  bind(plan: FourDPlan): TempWorksTarget | null {
    const b = this.prepare(plan);
    if (!b) return null;
    this.show(b);
    return { update: (t) => this.update(t), reset: () => this.reset() };
  }

  private build(plan: FourDPlan, groups: TempWorksGroup[]): Built {
    const model = fromSceneModel(this.app.controller.model as unknown as SceneLike, { name: plan.model.name });
    const pieces = generatePieces(groups, model);
    const meshes = new Map<TempWorksKind, { mesh: InstancedMesh; used: number; alpha: Float32Array; off: Float32Array }>();
    const perKind = new Map<TempWorksKind, number>();
    groups.forEach((g, i) => perKind.set(g.kind, (perKind.get(g.kind) ?? 0) + (pieces.range[i]![1] - pieces.range[i]![0])));
    for (const k of KINDS) {
      const n = perKind.get(k) ?? 0;
      if (!n) continue;
      const mat = new ShaderMaterial({
        vertexShader: VERT,
        fragmentShader: FRAG,
        uniforms: { uColor: { value: new Color(TEMP_COLOURS[k]) }, uOpacity: { value: TEMP_OPACITY[k] } },
        transparent: true,
        depthWrite: false,
        side: DoubleSide,
      });
      const alpha = new Float32Array(n);
      const off = new Float32Array(n * 3);
      const geo = new BoxGeometry(1, 1, 1);
      geo.setAttribute('aAlpha', new InstancedBufferAttribute(alpha, 1).setUsage(DynamicDrawUsage));
      geo.setAttribute('aOff', new InstancedBufferAttribute(off, 3).setUsage(DynamicDrawUsage));
      const mesh = new InstancedMesh(geo, mat, n);
      mesh.name = `temporary-works-${k}`;
      mesh.frustumCulled = false;
      mesh.renderOrder = 6;
      meshes.set(k, { mesh, used: 0, alpha, off });
    }
    const mx = new Matrix4();
    const place: Built['place'] = [];
    const alphaArr: Float32Array[] = [];
    const offArr: Float32Array[] = [];
    groups.forEach((g, gi) => {
      const m = meshes.get(g.kind)!;
      const [s, e] = pieces.range[gi]!;
      const base = m.used;
      for (let i = s; i < e; i++) {
        const o = i * 6;
        const b = pieces.box;
        // IFC (x, y, z) -> viewer (x, z, -y); sizes (sx, sz, sy)
        mx.makeScale(b[o + 3]!, b[o + 5]!, b[o + 4]!).setPosition(b[o]!, b[o + 2]!, -b[o + 1]!);
        m.mesh.setMatrixAt(base + (i - s), mx);
      }
      m.used += e - s;
      place.push({ mesh: m.mesh, base });
      alphaArr.push(m.alpha);
      offArr.push(m.off);
    });
    for (const m of meshes.values()) m.mesh.instanceMatrix.needsUpdate = true;
    const byGid = this.app.controller.model.byGlobalId;
    const anchor = new Int32Array(groups.length).fill(-1);
    groups.forEach((g, i) => { for (const id of g.elements) { const e = byGid.get(id); if (e !== undefined) { anchor[i] = e; break; } } });
    return { plan, groups, pieces, place, alpha: alphaArr, off: offArr, lastP: new Float64Array(groups.length).fill(-1), anchor };
  }

  private show(b: Built): void {
    if (this.built !== b) {
      this.detach();
      this.built = b;
      this.group.clear();
      const seen = new Set<InstancedMesh>();
      for (const p of b.place) if (!seen.has(p.mesh)) { seen.add(p.mesh); this.group.add(p.mesh); }
    }
    b.lastP.fill(-1);
    this.offVersion = -1;
    this.group.visible = this.on;
    if (!this.attached) { this.app.renderer.scene.add(this.group); this.attached = true; }
    this.planMs = NaN;
    this.zero(b);
  }

  private zero(b: Built): void {
    for (const a of new Set(b.alpha)) a.fill(0);
    for (const p of b.place) (p.mesh.geometry.getAttribute('aAlpha') as InstancedBufferAttribute).needsUpdate = true;
    this.app.renderer.markDirty();
  }

  private detach(): void {
    if (!this.attached) return;
    this.app.renderer.scene.remove(this.group);
    this.attached = false;
  }

  /** Set every group's progress for plan time `t` and write the alphas that changed. */
  update(t: number): void {
    const b = this.built;
    if (!b) return;
    this.planMs = t;
    const w = fadeShare(b.plan.style.fadeIn);
    let dirty = false;
    const touched = new Set<InstancedMesh>();
    b.groups.forEach((g, gi) => {
      const p = groupProgress(g, t);
      if (Math.abs(p - b.lastP[gi]!) < 1e-4) return;
      b.lastP[gi] = p;
      const [s, e] = b.pieces.range[gi]!;
      const { mesh, base } = b.place[gi]!;
      const arr = b.alpha[gi]!;
      for (let i = s; i < e; i++) arr[base + (i - s)] = pieceAlpha(p, b.pieces.order[i]!, w);
      touched.add(mesh);
      dirty = true;
    });
    for (const m of touched) (m.geometry.getAttribute('aAlpha') as InstancedBufferAttribute).needsUpdate = true;
    this.sync();
    if (dirty) this.app.renderer.markDirty();
  }

  /** Follow the explode offsets of the served storeys (cheap when nothing moved). */
  sync(): void {
    const b = this.built;
    if (!b) return;
    const r = this.app.renderer;
    if (r.offsetsVersion === this.offVersion) return;
    this.offVersion = r.offsetsVersion;
    const touched = new Set<InstancedMesh>();
    b.groups.forEach((_g, gi) => {
      const id = b.anchor[gi]!;
      const [ox, oy, oz] = id >= 0 ? r.elementOffset(id) : [0, 0, 0];
      const [s, e] = b.pieces.range[gi]!;
      const { mesh, base } = b.place[gi]!;
      const arr = b.off[gi]!;
      for (let i = 0; i < e - s; i++) { const k = (base + i) * 3; arr[k] = ox; arr[k + 1] = oy; arr[k + 2] = oz; }
      touched.add(mesh);
    });
    for (const m of touched) (m.geometry.getAttribute('aOff') as InstancedBufferAttribute).needsUpdate = true;
    r.markDirty();
  }

  /** The film ended or stopped: nothing is drawn. */
  reset(): void {
    this.detach();
    this.planMs = NaN;
    if (this.built) this.built.lastP.fill(-1);
    this.app.renderer.markDirty();
  }

  /** The state of every group now (smoke checks, the panel): phase, progress and how many pieces are at least half visible. */
  state(): TempWorksGroupState[] {
    const b = this.built;
    if (!b) return [];
    return b.groups.map((g, gi) => {
      const [s, e] = b.pieces.range[gi]!;
      const { base } = b.place[gi]!;
      const arr = b.alpha[gi]!;
      let vis = 0;
      for (let i = 0; i < e - s; i++) if (arr[base + i]! >= 0.5) vis++;
      return { id: g.id, kind: g.kind, label: g.label, phase: Number.isFinite(this.planMs) ? groupPhase(g, this.planMs) : 'before', progress: Number.isFinite(this.planMs) ? groupProgress(g, this.planMs) : 0, pieces: e - s, visible: vis };
    });
  }

  /** The label of the temporary-works piece under a normalised device point, or null (it never takes the pick from the model). */
  describeAt(ndcX: number, ndcY: number): string | null {
    const b = this.built;
    if (!b || !this.attached || !this.on) return null;
    const rc = new Raycaster();
    rc.setFromCamera(new Vector2(ndcX, ndcY), this.app.renderer.camera);
    let best: { d: number; text: string } | null = null;
    for (const m of new Set(b.place.map((p) => p.mesh))) {
      m.computeBoundingSphere();
      const hits = rc.intersectObject(m, false);
      for (const h of hits) {
        if (h.instanceId === undefined) continue;
        const gi = b.place.findIndex((p, i) => p.mesh === m && h.instanceId! >= p.base && h.instanceId! < p.base + (b.pieces.range[i]![1] - b.pieces.range[i]![0]));
        if (gi < 0) continue;
        const local = h.instanceId - b.place[gi]!.base;
        const piece = b.pieces.range[gi]![0] + local;
        if (b.alpha[gi]![b.place[gi]!.base + local]! < 0.5) continue;
        if (!best || h.distance < best.d) best = { d: h.distance, text: b.pieces.describe(piece) };
      }
    }
    return best?.text ?? null;
  }

  dispose(): void {
    this.reset();
    this.built = null;
  }
}

const layers = new WeakMap<object, TempWorksLayer>();

/** The one layer of a viewer (created on first use). */
export function getTempWorksLayer(app: Pick<ViewerApp, 'renderer' | 'controller'>): TempWorksLayer {
  let l = layers.get(app.renderer);
  if (!l) { l = new TempWorksLayer(app); layers.set(app.renderer, l); }
  return l;
}
