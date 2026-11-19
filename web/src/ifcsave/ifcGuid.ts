// Deterministic IFC GlobalIds: a 128-bit hash of a text key, written in the 22-character IFC base-64 alphabet.

const ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$';

/** 128-bit hash (four independent 32-bit murmur3-style lanes over the UTF-16 code units). */
export function hash128(text: string): [number, number, number, number] {
  const seeds = [0x9e3779b9, 0x85ebca6b, 0xc2b2ae35, 0x27d4eb2f];
  const out: number[] = [];
  for (const seed of seeds) {
    let h = seed ^ text.length;
    for (let i = 0; i < text.length; i++) {
      let k = Math.imul(text.charCodeAt(i) + 1, 0xcc9e2d51);
      k = (k << 15) | (k >>> 17);
      k = Math.imul(k, 0x1b873593);
      h ^= k;
      h = (h << 13) | (h >>> 19);
      h = (Math.imul(h, 5) + 0xe6546b64) | 0;
    }
    h ^= h >>> 16;
    h = Math.imul(h, 0x85ebca6b);
    h ^= h >>> 13;
    h = Math.imul(h, 0xc2b2ae35);
    h ^= h >>> 16;
    out.push(h >>> 0);
  }
  return out as [number, number, number, number];
}

/** Encode 128 bits (four uint32, most significant first) as 22 IFC base-64 characters; the first is 0 to 3. */
export function encodeGuid(w: readonly [number, number, number, number]): string {
  let big = 0n;
  for (const x of w) big = (big << 32n) | BigInt(x >>> 0);
  let out = '';
  for (let i = 0; i < 22; i++) {
    out = ALPHABET[Number(big & 63n)]! + out;
    big >>= 6n;
  }
  return out;
}

export function decodeGuid(g: string): [number, number, number, number] | null {
  if (!isIfcGuid(g)) return null;
  let big = 0n;
  for (const ch of g) big = (big << 6n) | BigInt(ALPHABET.indexOf(ch));
  return [Number((big >> 96n) & 0xffffffffn), Number((big >> 64n) & 0xffffffffn), Number((big >> 32n) & 0xffffffffn), Number(big & 0xffffffffn)];
}

export const isIfcGuid = (g: string): boolean => g.length === 22 && /^[0-3][0-9A-Za-z_$]{21}$/.test(g);

/** The GlobalId for a rooted line that Xray writes: same kind and key, same GUID. */
export function xrayGuid(kind: string, key: string): string {
  return encodeGuid(hash128(`xray|${kind}|${key}`));
}
