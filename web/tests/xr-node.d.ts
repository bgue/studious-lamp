// More of node's API for tests/xr-iwer.test.ts (the project has no @types/node; merges with the other *-node.d.ts files).
declare module 'node:fs' {
  export function readdirSync(path: string): string[];
  export function statSync(path: string): { isDirectory(): boolean };
}
declare module 'node:child_process' {
  export function spawnSync(
    cmd: string,
    args: string[],
    opts?: { cwd?: string; env?: Record<string, string | undefined>; encoding?: 'utf8'; timeout?: number },
  ): { status: number | null; stdout: string; stderr: string };
}
