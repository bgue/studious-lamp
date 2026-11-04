// The navigation cube: an SVG drawn from the camera orientation. 6 faces of 9 cells each (face centre, edge strips,
// corner squares), persistent elements whose points are rewritten when the camera turns. A cell carries its region
// ("x,y,z" signs) so a click asks for that view.

import { svgEl } from '../ui/overlay';
import { FACE_NAMES, allRegions, cubeCells, faceLabelAxes, regionKind, regionName, viewBasis } from './maths';
import type { Region, V3, View } from './maths';

export const CUBE_PX = 120;
const HALF = CUBE_PX / 2;
/** Screen pixels of the cube half size. */
const S = 31;

export interface CubeView {
  svg: SVGSVGElement;
  /** Redraw for a camera view; `current` is the region the camera looks from (highlighted), or null. */
  draw(v: View, current: Region | null): void;
  /** The region under an element of the cube, or null. */
  regionOf(target: EventTarget | null): Region | null;
  hover(r: Region | null): void;
}

const key = (r: Region): string => `${r[0]},${r[1]},${r[2]}`;
const parse = (k: string): Region => k.split(',').map(Number) as unknown as Region;

export function createCubeView(): CubeView {
  const svg = svgEl('svg', { viewBox: `${-HALF} ${-HALF} ${CUBE_PX} ${CUBE_PX}`, width: CUBE_PX, height: CUBE_PX, class: 'xg-cube' });
  svg.setAttribute('role', 'group');
  svg.setAttribute('aria-label', 'View cube. Click a face, an edge or a corner to look from there. Drag to orbit.');
  const shadow = svgEl('ellipse', { cx: 0, cy: S * 1.55, rx: S * 1.25, ry: S * 0.28, fill: '#000', 'fill-opacity': 0.12 });
  svg.appendChild(shadow);
  const cellsG = svgEl('g', {});
  const labelsG = svgEl('g', { 'pointer-events': 'none' });
  svg.append(cellsG, labelsG);

  // One polygon per (face, cell). The face centre cell is focusable and acts like a button for the keyboard.
  const polys = new Map<string, SVGPolygonElement>();
  const byRegion = new Map<string, SVGPolygonElement[]>();
  for (const face of allRegions().filter((r) => regionKind(r) === 'face')) {
    for (const r of allRegions()) {
      const a = face.findIndex((x) => x !== 0);
      if (r[a] !== face[a]) continue;
      const k = `${key(face)}|${key(r)}`;
      const p = svgEl('polygon', { class: `xg-cell xg-${regionKind(r)}`, 'data-region': key(r) });
      p.setAttribute('role', 'button');
      p.setAttribute('aria-label', `${regionName(r)} view`);
      if (regionKind(r) === 'face') p.setAttribute('tabindex', '0');
      p.style.display = 'none';
      polys.set(k, p);
      const list = byRegion.get(key(r)) ?? [];
      list.push(p);
      byRegion.set(key(r), list);
      cellsG.appendChild(p);
    }
  }
  const labels = new Map<string, SVGTextElement>();
  for (const [k, name] of Object.entries(FACE_NAMES)) {
    const t = svgEl('text', { class: 'xg-label', 'text-anchor': 'middle', 'dominant-baseline': 'central', 'font-size': 0.44 });
    t.textContent = name;
    labels.set(k, t);
    labelsG.appendChild(t);
  }

  let hovered: string | null = null;
  let currentKey: string | null = null;

  const paintState = (): void => {
    for (const [k, list] of byRegion) {
      for (const p of list) {
        p.classList.toggle('hover', k === hovered);
        p.classList.toggle('current', k === currentKey);
      }
    }
  };

  return {
    svg,
    draw(v, current) {
      const b = viewBasis(v);
      for (const p of polys.values()) p.style.display = 'none';
      const cells = cubeCells(b.right, b.up, b.back);
      for (const c of cells) {
        const p = polys.get(`${key(c.face)}|${key(c.region)}`);
        if (!p) continue;
        p.setAttribute('points', c.points.map(([x, y]) => `${(x * S).toFixed(2)},${(y * S).toFixed(2)}`).join(' '));
        p.style.display = '';
        // Light from the viewer: faces square to the view are brighter.
        const n: V3 = [c.face[0], c.face[1], c.face[2]];
        const lit = n[0] * b.back[0] + n[1] * b.back[1] + n[2] * b.back[2];
        p.style.setProperty('--lit', String(Math.round(62 + 30 * lit)));
        cellsG.appendChild(p); // keep painter's order: far to near
      }
      for (const [k, t] of labels) {
        const face = parse(k);
        const n = [face[0], face[1], face[2]];
        const facing = n[0]! * b.back[0] + n[1]! * b.back[1] + n[2]! * b.back[2];
        if (facing <= 0.08) {
          t.style.display = 'none';
          continue;
        }
        const { u, v: vv } = faceLabelAxes(face);
        const sx = (w: readonly number[]): [number, number] => [(w[0]! * b.right[0] + w[1]! * b.right[1] + w[2]! * b.right[2]) * S, -(w[0]! * b.up[0] + w[1]! * b.up[1] + w[2]! * b.up[2]) * S];
        const [ux, uy] = sx(u);
        const [vx, vy] = sx(vv);
        const [cx, cy] = sx(n);
        t.setAttribute('transform', `matrix(${ux.toFixed(3)} ${uy.toFixed(3)} ${(-vx).toFixed(3)} ${(-vy).toFixed(3)} ${cx.toFixed(2)} ${cy.toFixed(2)})`);
        t.style.display = '';
        t.style.opacity = String(Math.min(1, (facing - 0.08) * 3));
      }
      currentKey = current ? key(current) : null;
      paintState();
    },
    regionOf(target) {
      const el = target instanceof Element ? target.closest('[data-region]') : null;
      const k = el?.getAttribute('data-region');
      return k ? parse(k) : null;
    },
    hover(r) {
      const k = r ? key(r) : null;
      if (k === hovered) return;
      hovered = k;
      paintState();
    },
  };
}
