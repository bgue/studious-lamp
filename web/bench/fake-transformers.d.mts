// Types of bench/fake-transformers.mjs (the fake transformers.js used by the tests and the local smoke).
export const env: Record<string, unknown>;
export const __log: { pipelines: Array<{ task: string; model: string; device?: string; dtype?: string }>; batches: Array<{ size: number; premise: string; hyps: string[] }>; loads: number };
export function __reset(): void;
export function entailLogit(premise: string, hypothesis: string): number;
export function pipeline(task: string, model: string, opts?: Record<string, unknown>): Promise<any>;
export class PreTrainedTokenizer {
  constructor(tokenizerJson: unknown, tokenizerConfig: unknown);
  encode(text: string): number[];
}
