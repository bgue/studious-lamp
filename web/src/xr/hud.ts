// A text panel in the scene for headsets without a DOM overlay (Quest Browser, Vision Pro): a canvas texture on a plane that
// floats below the line of sight and turns with the head about the vertical. Redrawn only when the text changes.

import { CanvasTexture, Mesh, MeshBasicMaterial, PlaneGeometry, SRGBColorSpace } from 'three';
import type { Object3D } from 'three';
import type { Q4, V3 } from './maths';
import { yawOfDirection, quatRotate } from './maths';

const W = 1024;
const H = 512;

export class TextHud {
  readonly mesh: Mesh;
  private readonly canvas: HTMLCanvasElement;
  private readonly tex: CanvasTexture;
  private text = '';

  constructor(parent: Object3D, widthMetres = 0.56) {
    this.canvas = document.createElement('canvas');
    this.canvas.width = W;
    this.canvas.height = H;
    this.tex = new CanvasTexture(this.canvas);
    this.tex.colorSpace = SRGBColorSpace;
    const geo = new PlaneGeometry(widthMetres, (widthMetres * H) / W);
    const mat = new MeshBasicMaterial({ map: this.tex, transparent: true, depthTest: false, depthWrite: false });
    this.mesh = new Mesh(geo, mat);
    this.mesh.name = 'xray-xr-hud';
    this.mesh.renderOrder = 30;
    this.mesh.frustumCulled = false;
    this.mesh.visible = false;
    parent.add(this.mesh);
  }

  /** Lines of text; the first is drawn bold. */
  set(lines: string[]): void {
    const t = lines.join('\n');
    if (t === this.text) return;
    this.text = t;
    const g = this.canvas.getContext('2d');
    if (!g) return;
    g.clearRect(0, 0, W, H);
    g.fillStyle = 'rgba(14,20,28,0.78)';
    g.beginPath();
    g.roundRect?.(0, 0, W, H, 28);
    if (!g.roundRect) g.rect(0, 0, W, H);
    g.fill();
    let y = 56;
    lines.slice(0, 11).forEach((l, i) => {
      g.font = `${i === 0 ? '600 ' : ''}36px system-ui, sans-serif`;
      g.fillStyle = i === 0 ? '#ffd24a' : '#eef3f8';
      g.fillText(l.length > 52 ? `${l.slice(0, 51)}…` : l, 28, y);
      y += 44;
    });
    this.tex.needsUpdate = true;
  }

  /** Place 0.9 m ahead and 0.35 m below the eyes, facing the head (XR reference space, the rig's local frame). */
  follow(head: V3, headQuat: Q4, visible: boolean): void {
    this.mesh.visible = visible;
    if (!visible) return;
    const f = quatRotate(headQuat, [0, 0, -1]);
    const yaw = yawOfDirection(f);
    const fx = -Math.sin(yaw);
    const fz = -Math.cos(yaw);
    this.mesh.position.set(head[0] + fx * 0.9, head[1] - 0.35, head[2] + fz * 0.9);
    this.mesh.rotation.set(-0.35, yaw, 0, 'YXZ');
  }

  dispose(): void {
    this.mesh.removeFromParent();
    this.mesh.geometry.dispose();
    (this.mesh.material as MeshBasicMaterial).dispose();
    this.tex.dispose();
  }
}
