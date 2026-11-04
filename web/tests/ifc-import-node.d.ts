// The project has no @types/node; these are the few node modules the IFC import tests use.
declare module 'node:fs' {
  export function readFileSync(path: string): Uint8Array;
  export function readFileSync(path: string, encoding: 'utf8'): string;
  export function existsSync(path: string): boolean;
}
declare module 'node:path' {
  export function resolve(...parts: string[]): string;
  export function dirname(p: string): string;
}
declare module 'node:url' {
  export function fileURLToPath(u: string | URL): string;
}
declare module 'node:zlib' {
  export function deflateRawSync(data: Uint8Array): Uint8Array;
}
declare module 'node:child_process' {
  export function execFileSync(cmd: string, args: string[], opts?: { maxBuffer?: number }): Uint8Array;
}
