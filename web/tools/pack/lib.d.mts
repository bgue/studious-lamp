export const EXIT_OK: 0;
export const EXIT_USAGE: 1;
export const EXIT_INPUT: 2;
export class PackError extends Error {
  constructor(message: string, code?: number);
  code: number;
}
export const KNOWN_TOOLS: string[];
export const INJECT_BEGIN: string;
export const INJECT_END: string;
export const HELP: string;
export interface PackCamera { position: [number, number, number]; target: [number, number, number] }
export interface PackOptions {
  out: string | undefined;
  params: string | undefined;
  preset: string | undefined;
  select: string[] | undefined;
  title: string | undefined;
  name: string | undefined;
  tools: string[] | undefined;
  openTool: string | undefined;
  camera: PackCamera | undefined;
  views: string | undefined;
  openView: string | undefined;
  kiosk: boolean;
  noTopBar: boolean;
  ifcReader: boolean;
  samples: boolean;
  force: boolean;
  quiet: boolean;
}
export function parseList(text: string): string[];
export function parseSelect(text: string): { gids: string[]; classes: string[]; entries: string[] };
export function parseCamera(text: string): PackCamera;
export function parseArgs(argv: string[]): { help: boolean; inputs: string[]; options: PackOptions };
export function unknownTools(tools: string[] | undefined): string[];
export function defaultModelName(inputPath: string): string;
export function checkViews(doc: unknown, openView?: string, modelName?: string): { views: Array<Record<string, unknown>>; warnings: string[] };
export function buildBoot(model: string, options?: Partial<PackOptions>, params?: unknown, views?: unknown[]): Record<string, unknown>;
export function toBase64(bytes: Uint8Array | ArrayBuffer): string;
export function fromBase64(text: string): Uint8Array;
export function scriptSafe(s: string): string;
export function escapeHtml(s: string): string;
export function injectionScript(models: Record<string, { glb: string; json?: unknown }>, boot: unknown): string;
export function injectTemplate(html: string, parts: { models: Record<string, { glb: string; json?: unknown }>; boot: unknown; title: string }): string;
