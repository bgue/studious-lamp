// More of node's API for the ifcsave tests (the project has no @types/node; merges with the other *-node.d.ts files).
declare module 'node:child_process' {
  export function execFileSync(cmd: string, args: string[], opts?: { maxBuffer?: number; timeout?: number; stdio?: 'ignore' | 'pipe' }): Uint8Array;
}
