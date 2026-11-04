import { writeZip } from '../src/bcf/zip';
import type { ZipInput } from '../src/bcf/zip';

// The project has no @types/node, so node modules come from process.getBuiltinModule (node 22) untyped.
/* eslint-disable @typescript-eslint/no-explicit-any */
export const nodeMod = (name: string): any => (globalThis as any).process.getBuiltinModule(name);

const fs = nodeMod('node:fs');
const path = nodeMod('node:path');

export const FIXTURES: string = decodeURIComponent(new URL('./fixtures/bcf', import.meta.url).pathname);

function walk(dir: string, out: string[] = []): string[] {
  for (const n of (fs.readdirSync(dir) as string[]).sort()) {
    const p = path.join(dir, n);
    if (fs.statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

/** Zip an unpacked fixture folder (bcf21 / bcf30) into archive bytes. */
export async function fixtureZip(name: string, opts: { compress?: boolean } = {}): Promise<Uint8Array> {
  const base = path.join(FIXTURES, name);
  const files: ZipInput[] = walk(base).map((p) => ({ name: (path.relative(base, p) as string).split(path.sep).join('/'), data: new Uint8Array(fs.readFileSync(p)) }));
  return writeZip(files, opts);
}

export function fixtureText(rel: string): string {
  return fs.readFileSync(path.join(FIXTURES, rel), 'utf8') as string;
}

export const G1 = '2XPyKWY018sA1ygZKgQPtU';
export const G2 = '3PfS__Y_DBAfq5naM6zD2Z';
