// The HudSource of the viewer: element data from the loaded model, the camera and the north of the project.

import type { ViewerApp } from '../../app';
import { cardRows, parsePatterns, subtitleOf } from '../../ui/hoverCard';
import type { CardContent } from '../../ui/hoverCard';
import { hoverInfoSettings } from '../../plugins/hoverInfo';
import type { ElementRef } from '../score';
import type { HudSource } from './layer';

/** The card of an element as the hover card shows it, without the live x-ray line (a video must not depend on it). */
export function hoverCardContent(app: ViewerApp, id: number): CardContent | null {
  const m = app.controller.model;
  const e = m.elements[id];
  if (!e) return null;
  const storey = e.storey === null ? undefined : m.storeys.find((s) => s.id === e.storey)?.name;
  return {
    title: e.name && e.name.trim() !== '' ? e.name : e.ifcClass,
    subtitle: subtitleOf(e.ifcClass, storey, e.material),
    rows: cardRows(e.props, parsePatterns(hoverInfoSettings.propertyFilter), Math.max(0, Math.floor(hoverInfoSettings.maxRows))),
    footer: '',
  };
}

/** North as degrees counter-clockwise from project +Y: the map's place when it has one, else IfcSite TrueNorth, else 0 (project +Y is north). */
export function northOf(app: ViewerApp): number {
  const g = (window as unknown as { __xrayMap?: { georef(): { rotation: number } | null } }).__xrayMap?.georef?.();
  if (g && Number.isFinite(g.rotation)) return g.rotation;
  const tn = app.controller.model.siteGeo?.trueNorth;
  return typeof tn === 'number' && Number.isFinite(tn) ? tn : 0;
}

export function appHudSource(app: ViewerApp, resolve: (ref: ElementRef, key: string) => number[]): HudSource {
  return {
    elementIds: resolve,
    element: (id) => {
      const m = app.controller.model;
      const e = m.elements[id];
      if (!e) return null;
      const storey = e.storey === null ? undefined : m.storeys.find((s) => s.id === e.storey)?.name;
      return { ...(e.name !== undefined ? { name: e.name } : {}), ifcClass: e.ifcClass, ...(storey !== undefined ? { storey } : {}), ...(e.material !== undefined ? { material: e.material } : {}), globalId: e.globalId, ...(e.props ? { props: e.props } : {}) };
    },
    bounds: (id) => app.controller.model.elements[id]?.bounds ?? null,
    card: (id) => hoverCardContent(app, id),
    camera: () => {
      const { camera, controls } = app.renderer;
      camera.updateMatrixWorld();
      const right = camera.matrixWorld.elements;
      const fx = controls.target.x - camera.position.x;
      const fy = controls.target.y - camera.position.y;
      const fz = controls.target.z - camera.position.z;
      return { focus: [controls.target.x, controls.target.y, controls.target.z], right: [right[0]!, right[1]!, right[2]!], distance: Math.hypot(fx, fy, fz) || 1 };
    },
    northDeg: () => northOf(app),
  };
}
