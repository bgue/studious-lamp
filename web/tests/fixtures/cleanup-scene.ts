// Synthetic scene for the cleanup tests: a main structure plus every kind of debris, with known ids.

import type { Bounds6, CleanupElement, CleanupGeometry } from '../../src/cleanup/analysis';

export interface CleanupScene {
  elements: CleanupElement[];
  ids: {
    main: number[];
    loneSmall: number[];
    cluster: number[];
    largeFloating: number;
    stray: number;
    duplicateOriginal: number;
    duplicate: number;
    degenerate: number;
    diagonal: number;
    tinyTouching: number;
    proxy: number;
    furniture: number;
    fastener: number;
  };
  /** Mesh stand-in: triangle counts, plus the diagonal element is 0.3 m away in the mesh although its bounds touch. */
  geometry: CleanupGeometry;
}

function box(x: number, y: number, z: number, sx: number, sy: number, sz: number): Bounds6 {
  return [x, y, z, x + sx, y + sy, z + sz];
}

export function makeCleanupScene(): CleanupScene {
  const els: CleanupElement[] = [];
  const add = (ifcClass: string, b: Bounds6): number => {
    els.push({ id: els.length, ifcClass, bounds: b });
    return els.length - 1;
  };

  // Main structure: 4 x 4 slab tiles (2 x 0.3 x 2), touching their neighbours, and four walls on top.
  const main: number[] = [];
  for (let i = 0; i < 4; i++) for (let k = 0; k < 4; k++) main.push(add('IfcSlab', box(i * 2, 0, k * 2, 2, 0.3, 2)));
  for (let i = 0; i < 4; i++) main.push(add('IfcWall', box(i * 2, 0.3, 0, 2, 3, 0.2)));

  // Lone small boxes (0.3 m), well apart from everything.
  const loneSmall = [
    add('IfcBeam', box(1, 5, 1, 0.3, 0.3, 0.3)),
    add('IfcColumn', box(4, 6, 2, 0.3, 0.3, 0.3)),
    add('IfcBeam', box(6, 4, 5, 0.3, 0.3, 0.3)),
  ];
  // Floating cluster of three touching 0.1 m cubes (union 0.3 m).
  const cluster = [
    add('IfcMember', box(-3, 2, -3, 0.1, 0.1, 0.1)),
    add('IfcMember', box(-2.9, 2, -3, 0.1, 0.1, 0.1)),
    add('IfcMember', box(-2.8, 2, -3, 0.1, 0.1, 0.1)),
  ];
  // Large floating element, above the threshold: must never match the floating rule.
  const largeFloating = add('IfcSlab', box(9, 2, 9, 1.5, 1.5, 1.5));
  // Far stray, 0.8 m, 600 m away.
  const stray = add('IfcBuildingElementProxy', box(600, 0, 0, 0.8, 0.8, 0.8));
  // Duplicates: a wall copy within 1 mm of wall #16 (lowest id is kept).
  const dupOrig = main[16]!;
  const duplicate = add('IfcWall', [0.001, 0.3005, 0, 2.0005, 3.3, 0.2]);
  // Degenerate: a flat zero-thickness sheet touching the structure.
  const degenerate = add('IfcPlate', box(0, 3.3, 0, 1, 0, 1));
  // Diagonal: bounds touch slab #15 at its top corner, meshes do not (0.3 m apart).
  const diagonal = add('IfcMember', box(8, 0.3, 8, 0.4, 0.4, 0.4));
  // Tiny element (0.03 m) welded onto the structure: tiny but not floating.
  const tinyTouching = add('IfcDiscreteAccessory', box(2, 3.3, 0.05, 0.03, 0.03, 0.03));
  const proxy = add('IfcBuildingElementProxy', box(1, 3.3, 0.5, 0.6, 0.6, 0.6));
  const furniture = add('IfcFurniture', box(3, 0.3, 1, 0.8, 0.8, 0.8));
  const fastener = add('IfcFastener', box(0.5, 0.3, 0.5, 0.1, 0.1, 0.1));

  const geometry: CleanupGeometry = {
    triangleCount: () => 12,
    meshVolume: (id) => {
      const b = els[id]!.bounds;
      return (b[3] - b[0]) * (b[4] - b[1]) * (b[5] - b[2]);
    },
    surfaceDistance: (a, b, max) => {
      const pair = a === diagonal || b === diagonal;
      const other = a === diagonal ? b : a;
      if (pair && main.includes(other) && other === main[15]) return Math.max(0.3, max + 1e-6);
      const A = els[a]!.bounds;
      const B = els[b]!.bounds;
      const dx = Math.max(0, A[0] - B[3], B[0] - A[3]);
      const dy = Math.max(0, A[1] - B[4], B[1] - A[4]);
      const dz = Math.max(0, A[2] - B[5], B[2] - A[5]);
      return Math.hypot(dx, dy, dz);
    },
  };
  return {
    elements: els,
    ids: { main, loneSmall, cluster, largeFloating, stray, duplicateOriginal: dupOrig, duplicate, degenerate, diagonal, tinyTouching, proxy, furniture, fastener },
    geometry,
  };
}
