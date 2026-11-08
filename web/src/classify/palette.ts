// A colour for each discipline code (colour by discipline). RGB 0 to 1. Codes that the palette does not know get a hue from a hash.

const FIXED: Record<string, [number, number, number]> = {
  ARC: [0.93, 0.78, 0.35],
  STR: [0.86, 0.33, 0.3],
  MEC: [0.3, 0.65, 0.95],
  PLB: [0.25, 0.8, 0.55],
  FPR: [0.96, 0.45, 0.15],
  ELE: [0.96, 0.88, 0.25],
  TEL: [0.65, 0.45, 0.95],
  CIV: [0.6, 0.48, 0.32],
  PIP: [0.2, 0.75, 0.8],
  INS: [0.95, 0.5, 0.75],
  GEN: [0.62, 0.62, 0.62],
};

function hsl(h: number, s: number, l: number): [number, number, number] {
  const a = s * Math.min(l, 1 - l);
  const f = (n: number): number => {
    const k = (n + h * 12) % 12;
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  return [f(0), f(8), f(4)];
}

export function disciplineRgb(code: string): [number, number, number] {
  const f = FIXED[code];
  if (f) return f;
  let h = 7;
  for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) >>> 0;
  return hsl((h % 360) / 360, 0.6, 0.58);
}

export const rgbCss = (c: readonly number[]): string => `rgb(${Math.round(c[0]! * 255)},${Math.round(c[1]! * 255)},${Math.round(c[2]! * 255)})`;
