// Standalone render demo (not wired into index.html).
//   /demo.html?model=procedural   in-memory slab + duct + beam
//   /demo.html?model=building     /models/building.glb + building.json
// Sets window.__xrayReady = true after the first frame, and window.__xrayInfo with stats.

import { loadModel, parseModel } from '../model/loader';
import type { LoadedModel } from '../model/loader';
import { buildProceduralGlb } from '../model/procedural';
import { XrayRenderer } from './renderer';

declare global {
  interface Window {
    __xrayReady?: boolean;
    __xrayError?: string;
    __xrayInfo?: Record<string, unknown>;
    __xrayDemoRenderer?: XrayRenderer;
  }
}

async function main(): Promise<void> {
  const params = new URLSearchParams(location.search);
  const name = params.get('model') ?? 'procedural';

  const canvas = document.getElementById('c') as HTMLCanvasElement | null ?? document.createElement('canvas');
  if (!canvas.parentElement) {
    canvas.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;display:block';
    document.body.appendChild(canvas);
  }
  const xr = new XrayRenderer(canvas);
  window.__xrayDemoRenderer = xr;
  window.addEventListener('resize', () => xr.resize());

  const t0 = performance.now();
  let loaded: LoadedModel;
  if (name === 'procedural') {
    loaded = await parseModel(buildProceduralGlb());
  } else {
    loaded = await loadModel(`/models/${name}.glb`, `/models/${name}.json`);
  }
  const tLoad = performance.now() - t0;

  xr.setModel(loaded); // all alpha 1, no flags

  // ?state=xray: first focus-class element is focus, context classes ghosted (exercises all passes).
  if (params.get('state') === 'xray') {
    const els = loaded.model.elements;
    const focusCls = /Duct|Pipe|CableCarrier|Flow/;
    const ctxCls = /Slab|Wall|Beam|Column/;
    let focused = 0;
    els.forEach((e, i) => {
      if (focusCls.test(e.ifcClass) && focused < 200) {
        xr.state.flags[i] = (xr.state.flags[i] ?? 0) | 1;
        focused++;
      } else if (ctxCls.test(e.ifcClass)) {
        xr.state.alpha[i] = 0.25;
      }
    });
    xr.markDirty();
  }
  xr.resize();
  xr.frameAll();
  const cam = params.get('cam');
  if (cam) {
    const [x, y, z] = cam.split(',').map(Number) as [number, number, number];
    xr.camera.position.set(x, y, z);
    xr.controls.update();
  }
  xr.render();
  const gl = xr.renderer.getContext();
  gl.finish();

  window.__xrayInfo = {
    model: name,
    elements: loaded.model.elements.length,
    classes: loaded.model.elements.map((e) => e.ifcClass),
    triangles: loaded.geometry.geometry.getIndex()!.count / 3,
    edgeVertices: loaded.geometry.edges.getAttribute('position').count,
    loadMs: Math.round(tLoad),
    drawCalls: xr.renderer.info.render.calls,
  };
  window.__xrayReady = true;

  const loop = (): void => {
    xr.render();
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

main().catch((e: unknown) => {
  window.__xrayError = String(e instanceof Error ? e.stack ?? e.message : e);
  console.error(window.__xrayError);
});
