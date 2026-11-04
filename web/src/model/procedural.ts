// A tiny in-memory glb used by the demo and tests: a slab, a duct piercing it and a beam below.
// Built by hand (no GLTFExporter) so it works in node and in the browser.

import type { ElementRecord } from '../types';

interface BoxSpec {
  name: string;
  ifcClass: string;
  center: [number, number, number];
  size: [number, number, number];
  color: [number, number, number, number];
}

export const PROCEDURAL_BOXES: BoxSpec[] = [
  { name: 'slab-0001', ifcClass: 'IfcSlab', center: [0, 0, 0], size: [10, 0.3, 8], color: [0.78, 0.78, 0.76, 1] },
  { name: 'duct-0001', ifcClass: 'IfcDuctSegment', center: [1, 0.5, 0.5], size: [0.5, 3, 0.5], color: [0.2, 0.55, 0.85, 1] },
  { name: 'beam-0001', ifcClass: 'IfcBeam', center: [0, -0.5, 2], size: [8, 0.3, 0.4], color: [0.6, 0.45, 0.35, 1] },
];

// Unit box (24 vertices, per-face normals, 12 triangles), scaled by node scale + translation.
function unitBox(): { pos: number[]; nor: number[]; idx: number[] } {
  const faces: Array<{ n: [number, number, number]; u: [number, number, number]; v: [number, number, number] }> = [
    { n: [1, 0, 0], u: [0, 1, 0], v: [0, 0, 1] },
    { n: [-1, 0, 0], u: [0, 0, 1], v: [0, 1, 0] },
    { n: [0, 1, 0], u: [0, 0, 1], v: [1, 0, 0] },
    { n: [0, -1, 0], u: [1, 0, 0], v: [0, 0, 1] },
    { n: [0, 0, 1], u: [1, 0, 0], v: [0, 1, 0] },
    { n: [0, 0, -1], u: [0, 1, 0], v: [1, 0, 0] },
  ];
  const pos: number[] = [];
  const nor: number[] = [];
  const idx: number[] = [];
  for (const f of faces) {
    const base = pos.length / 3;
    for (const [su, sv] of [[-1, -1], [1, -1], [1, 1], [-1, 1]] as const) {
      for (let k = 0; k < 3; k++) pos.push(0.5 * (f.n[k]! + su * f.u[k]! + sv * f.v[k]!));
      nor.push(...f.n);
    }
    // Faces are built so (u x v) = n, giving counter-clockwise winding seen from outside.
    idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }
  return { pos, nor, idx };
}

export function buildProceduralGlb(): ArrayBuffer {
  const { pos, nor, idx } = unitBox();
  const posBytes = new Float32Array(pos).buffer;
  const norBytes = new Float32Array(nor).buffer;
  const idxBytes = new Uint32Array(idx).buffer;
  const bin = new Uint8Array(posBytes.byteLength + norBytes.byteLength + idxBytes.byteLength);
  bin.set(new Uint8Array(posBytes), 0);
  bin.set(new Uint8Array(norBytes), posBytes.byteLength);
  bin.set(new Uint8Array(idxBytes), posBytes.byteLength + norBytes.byteLength);

  const json = {
    asset: { version: '2.0', generator: 'xray-ref procedural' },
    scene: 0,
    scenes: [{ nodes: PROCEDURAL_BOXES.map((_, i) => i) }],
    nodes: PROCEDURAL_BOXES.map((b, i) => ({
      name: b.name,
      mesh: i,
      translation: b.center,
      scale: b.size,
      extras: { id: i, ifcClass: b.ifcClass },
    })),
    meshes: PROCEDURAL_BOXES.map((_, i) => ({
      primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, indices: 2, mode: 4, material: i }],
    })),
    materials: PROCEDURAL_BOXES.map((b) => ({
      pbrMetallicRoughness: { baseColorFactor: b.color, metallicFactor: 0, roughnessFactor: 1 },
    })),
    accessors: [
      { bufferView: 0, componentType: 5126, count: 24, type: 'VEC3', min: [-0.5, -0.5, -0.5], max: [0.5, 0.5, 0.5] },
      { bufferView: 1, componentType: 5126, count: 24, type: 'VEC3' },
      { bufferView: 2, componentType: 5125, count: 36, type: 'SCALAR' },
    ],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: posBytes.byteLength, target: 34962 },
      { buffer: 0, byteOffset: posBytes.byteLength, byteLength: norBytes.byteLength, target: 34962 },
      { buffer: 0, byteOffset: posBytes.byteLength + norBytes.byteLength, byteLength: idxBytes.byteLength, target: 34963 },
    ],
    buffers: [{ byteLength: bin.byteLength }],
  };

  const enc = new TextEncoder();
  let jsonBytes = enc.encode(JSON.stringify(json));
  const jsonPad = (4 - (jsonBytes.length % 4)) % 4;
  if (jsonPad) {
    const padded = new Uint8Array(jsonBytes.length + jsonPad).fill(0x20);
    padded.set(jsonBytes);
    jsonBytes = padded;
  }
  const total = 12 + 8 + jsonBytes.length + 8 + bin.length;
  const out = new ArrayBuffer(total);
  const dv = new DataView(out);
  const u8 = new Uint8Array(out);
  dv.setUint32(0, 0x46546c67, true); // 'glTF'
  dv.setUint32(4, 2, true);
  dv.setUint32(8, total, true);
  dv.setUint32(12, jsonBytes.length, true);
  dv.setUint32(16, 0x4e4f534a, true); // 'JSON'
  u8.set(jsonBytes, 20);
  const o = 20 + jsonBytes.length;
  dv.setUint32(o, bin.length, true);
  dv.setUint32(o + 4, 0x004e4942, true); // 'BIN\0'
  u8.set(bin, o + 8);
  return out;
}

/** Matching sidecar (bounds in glb frame), for exercising the sidecar path. */
export function proceduralSidecar(): { schema: string; originShift: number[]; storeys: unknown[]; elements: ElementRecord[]; relations: unknown } {
  return {
    schema: 'xray-model/1',
    originShift: [0, 0, 0],
    storeys: [{ id: 0, name: 'Level 1', elevation: 0 }],
    elements: PROCEDURAL_BOXES.map((b, i) => ({
      id: i,
      globalId: b.name,
      ifcClass: b.ifcClass,
      name: b.name,
      storey: 0,
      color: b.color,
      bounds: [
        b.center[0] - b.size[0] / 2, b.center[1] - b.size[1] / 2, b.center[2] - b.size[2] / 2,
        b.center[0] + b.size[0] / 2, b.center[1] + b.size[1] / 2, b.center[2] + b.size[2] / 2,
      ] as ElementRecord['bounds'],
    })),
    relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] },
  };
}
