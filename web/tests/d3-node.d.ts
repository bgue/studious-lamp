// The part of node:crypto that the d3 tests use (the project has no @types/node).
declare module 'node:crypto' {
  export function createHash(algorithm: string): { update(data: Uint8Array | string): { digest(encoding: 'hex'): string } };
}
