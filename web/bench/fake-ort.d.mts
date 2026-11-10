// Types of bench/fake-ort.mjs (the fake onnxruntime-web used by the tests and the local smoke).
export const env: { wasm: Record<string, unknown> };
export const __log: { sessions: Array<{ bytes: number; options: Record<string, unknown> }>; runs: Array<{ tokens: number; options: number }> };
export function __reset(): void;
export class Tensor {
  constructor(type: string, data: unknown, dims: readonly number[]);
  type: string;
  data: any;
  dims: readonly number[];
}
export const InferenceSession: { create(model: Uint8Array | string, options?: Record<string, unknown>): Promise<any> };
