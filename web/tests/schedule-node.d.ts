// The project has no @types/node. The schedule and xray-4d tests use a few node modules, and __dirname, which vitest
// provides at run time; these declarations cover exactly those (other node modules are declared in the *-node.d.ts files).
declare const __dirname: string;
declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'latin1'): string;
}
declare module 'node:crypto' {
  interface Hash {
    update(data: Uint8Array | string): Hash;
    digest(encoding: 'hex'): string;
  }
  export function createHash(algorithm: string): Hash;
  export function randomBytes(size: number): Uint8Array;
}
declare module 'node:child_process' {
  export function spawnSync(
    command: string,
    args: string[],
    options?: { cwd?: string; encoding?: 'utf8'; timeout?: number },
  ): { status: number | null; stdout: string; stderr: string };
}
